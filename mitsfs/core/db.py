#!/usr/bin/python
'''

code for manipulating pinkdexen stored in postgres databases

'''


import functools
import logging
import os
import re

import psycopg2

__all__ = [
    'Database', 'Field', 'ReadField', 'ReadFieldUncached',
    'Entry', 'cached', 'EntryDeletable',
    # 'StaticField',
    ]


class Database(object):
    def getcursor(self):
        return self.db.cursor(cursor_factory=EasyCursor)

    def __init__(self, client='mitsfs.dexdb', dsn='dbname=mitsfs'):
        self.dsn = dsn
        try:
            self.db = psycopg2.connect(dsn)
        except psycopg2.OperationalError as e:
            # these error messages are terrible, here's a common one
            if re.match(r'FATAL:  role "[^"]*" does not exist\n', e.message):
                raise Exception(
                    'Unknown user.  You likely have not been granted access.')
            elif (
                e.message.startswith('FATAL:  GSSAPI authentication failed')
                    or e.message.startswith('GSSAPI continuation error:')):
                raise Exception(
                    'Authentication failure.  '
                    'Try renewing your Kerberos tickets?')
            else:
                raise

        self.cursor = self.getcursor()
        self.client = client
        self.cursor.execute('select set_client(%s)', (client,))
        self.wizard = None
        if os.environ.get('SPEAKER_TO_POSTGRES'):
            self.cursor.execute('set role "speaker-to-postgres"')
            print('Wizard mode enabled')
            self.wizard = 'badger'
        self.db.commit()  # Just makin' sure, and folks he was

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()
      


class EasyCursor(psycopg2.extensions.cursor):
    '''
    @return id of the object in hexadecimal. Useful for logging
    '''

    def cursor_id(self):
        i = id(self)
        return f'{2**32 - i:x}' if i < 0 else f'C: {i:x}'

    '''
    The core function that handles all the querying to the database

    @param sql: the parameterized sql statement
    @param args: args to be passed into the parameterized sql

    @return: the cursor object
    '''

    def execute(self, sql, args=None):
        log = logging.getLogger('mitsfs.sql')
 
        log.debug('%s', self.mogrify(sql, args))
        try:
            psycopg2.extensions.cursor.execute(self, sql, args)
        except Exception as exc:
            log.exception('%s: %s: %s',
                          self.cursor_id(), exc.__class__.__name__, exc)
            try:
                self.connection.rollback()
            except Exception as err:
                log.exception('%s: %s: %s',
                              self.cursor_id(), err.__class__.__name__, err)
                pass
            raise
        log.debug('%s: %s rows: %d',
                  self.cursor_id(), self.statusmessage, self.rowcount)
        return self

    '''
    Pass in a query and args that result in a single value

    @param query: the sql query
    @param args: the args to be passed into the query

    @return: a single string value corresponding to the result of the query.
    '''

    def selectvalue(self, sql, args=None):
        '''
        For a query that wants a single result, return it.

        Parameters
        ----------
        sql : str
            SQL string.
        args : tuple, optional
            list of the values to flow into the SQL statement

        Returns
        -------
        value from the statement
        '''
        self.execute(sql, args)
        if self.rowcount == 0:
            return None
        return self.fetchone()[0]

    def fetchlist(self, sql, args=None):
        '''
        For a query that provides a single value in the select statement, 
        returns the multiple single values as a list. 

        Parameters
        ----------
        sql : str
            SQL string.
        args : tuple, optional
            list of the values to flow into the SQL statement

        Returns
        -------
        list
            list of the results from the sql statement.

        '''
        self.execute(sql, args)
        if self.rowcount == 0:
            return []
        return [x[0] for x in self.fetchall()]
        
    '''
    Pass in a query and a list of args tuples, and executes the sql repeatedly
    for each tuple provided

    @param query: the sql query
    @param args: a list of args tuples, each to be executed against the sql

    @return: the cursor object
    '''

    def executemany(self, sql, argsiter):
        for args in argsiter:
            self.execute(sql, args)
        return self

    def __nonzero__(self):
        return self.rowcount != 0

    def next(self):
        row = psycopg2.extensions.cursor.next(self)
        if len(row) == 1:
            return row[0]
        else:
            return row

    def __enter__(self):
        self.connection.rollback()
        self.isolation_level = self.connection.isolation_level
        self.connection.set_isolation_level(
            psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE)
        return self

    def __exit__(self, type, value, tb):
        if tb is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.set_isolation_level(self.isolation_level)


class ValidationError(Exception):
    pass


'''Raised when we are unable to locate an item in the database'''


class NotFoundException(Exception):
    pass


'''
These  classes allow reading a single field from the db in a generic
fashion. They are used in the membership section of the code.

Field enables full getting and setting of the field.
ReadFieldUncached is currently unused (used to be for checkout_lost, not
                                       sure why)
ReadField is the most common. Does a read (no write) but wraps it in a cache.

'''


class Field(property):
    '''
    Create a field object. Enables just-in-time retrieveal of field values

    @param fieldname: the name of the field
    @param coercer: a function to take the field data extracted from the
        database and turn it into another object
    @param validator: a function to check against before writing to the db.

    All the above functions passed in must take a value, and an optional
    database object
    '''

    def __init__(
            self, fieldname, coercer=None, validator=None,
            prep_for_write=None
            ):
        self.field = fieldname
        self.prep_for_write = prep_for_write
        self.validator = validator
        self.coercer = coercer
        super().__init__(self.get, self.set)

    '''
    Pretty standard getter. Coerces the value into whatever the coerce function
    returns.

    @param obj: This confuses the heck out of me and there's no documentation
        about it. As far as I can tell, obj is class this field is a member of.
        So if you set x=Field(foo) and then make this a class variable, calls
        to get are transformed into __get__(self, class)

        This lets you define Entry objects below that contain Fields, and
        those have access to the params in the entry object. Python can
        be really cryptic sometimes.
    @return: the value in the database in this field for the ID of the caller
    '''

    def get(self, obj):
        if self.field in obj.cache:
            return obj.cache[self.field]

        command = 'select %s from %s where %s = %%s' \
            % (self.field, obj.table, obj.idfield)
        val = obj.cursor.selectvalue(command, (obj.id,))

        if self.coercer is not None:
            val = self.coercer(val, obj.db)
        return val

    '''
    Set variables.

    This does a fair amount before it writes.
    1) If there's a prep_for_write defined, applies it to the value. Usually
        done to turn a coerced object back into a string.
    2) apply strip() to it if you can
    3) validate that the value is correct if a validator was provided
    4) coerce the data into the right form. Does not do this if
        prep_for_write is defined, because that'll turn it back into an object

    @param obj: See above

    '''

    def set(self, obj, val):
        if self.prep_for_write:
            val = self.prep_for_write(val, obj.db)
        if hasattr(val, 'strip'):
            val = val.strip()
        if self.validator and not self.validator(obj, val):
            raise ValidationError(
                'Validation failed for %s.%s: %s' % (
                    obj.table, self.field, repr(val)))
        if self.prep_for_write is None and self.coercer is not None:
            val = self.coercer(val, obj.db)

        obj.cache[self.field] = val
        if not obj.new:
            obj.cursor.execute(
                'update %s set %s = %%s where %s = %%s' %
                (obj.table, self.field, obj.idfield),
                (val, obj.id))
        if obj.docommit:
            obj.db.db.commit()


class ReadFieldUncached(Field):
    def set(self, obj, val):
        raise AssertionError('Readonly property %s:%s' % (
            repr(obj), self.field))


class ReadField(ReadFieldUncached):
    def get(self, obj):
        if self.field in obj.cache:
            return obj.cache[self.field]
        val = super().get(obj)
        obj.cache[self.field] = val
        return val


class InfoField(ReadField):
    '''
    ReadField that can also take pregenerated values and not write them back
    to the db. Useful for bulk load of foundational information such as
    shelfcodes and memberships
    '''

    def set(self, obj, val):
        obj.cache[self.field] = val


def get_field_name_if_has_field_attribute(obj, attribute_name):
    '''
    This is pulled out for readability and to be clear what it is.

    Given an object and an attribute in the object, figure out if it has a
    field attribute in it (which defines the db column) and return the value.
    Lets you define the fields of a class by the objects above


    Parameters
    ----------
    obj : object
        the object being examined
    attribute_name : str
        The name of the attribute we are checking to see if it has a field
        property.

    Returns
    -------
    str
        The name of the column in the database contained in this attribute

    '''
    attr = getattr(obj, attribute_name)
    return getattr(attr, 'field', None)


class Entry(object):

    def __init__(self, table, idfield, db, id_=None, **kw):
        self.db = db
        self.table = table
        self.idfield = idfield
        self.cache_reset()
        self.id = id_
        self.cursor = None
        self.docommit = True

        # this is at the heart of the whole thing.
        # each subclass of this method has attributes
        # that are objects with a set field attribute (presumably Field/
        # ReadField/ReadFieldUncached). So it loops through all the attributes
        # of the object to grab them and put them in a field array with the
        # name and the field value, which represents the column name in the
        # table.
        me = self.__class__

        self._fields = dict(
            (attribute_name, column_name)
            for (attribute_name, column_name)
            in ((attribute_name,
                 get_field_name_if_has_field_attribute(me, attribute_name))
                for attribute_name in dir(me))
            if column_name is not None)

        # This allows us to pre-seed data into the attributes by passing them
        # in as keyword arguments. You can only pass in fields this way to the
        # base class or it will complain.
        for (k, v) in kw.items():
            if k not in self._fields:
                raise AssertionError(
                    '%s is not a field of %s' % (k, me.__name__))
            setattr(self, k, v)

    def cache_reset(self):
        self.cache_date = None
        self.cache = {}

    def getcursor(self):
        if not self.__cursor:
            return self.db.getcursor()
        else:
            return self.__cursor

    def setcursor(self, val):
        self.__cursor = val

    cursor = property(getcursor, setcursor)
    new = property(lambda self: not bool(self.id))

    def __repr__(self):
        self.cursor = self.db.getcursor()
        try:

            def rfilter(x, y):
                if isinstance(y, x.__class__):
                    return str(x)
                else:
                    return x

            if self.new:
                return '<%s NEW: %s>' % (
                    self.__class__.__name__,
                    ', '.join(
                        '%s=%s' % (k, repr(v))
                        for (k, v)
                        in self.cache.items()))
            else:
                return '<%s #%d: %s>' % (
                    self.__class__.__name__, self.id,
                    ', '.join(
                        '%s=%s' % (field, repr(
                            rfilter(getattr(self, field), self)))
                        for field in self._fields))
        finally:
            self.cursor = None

    def create(self, commit=True):
        if self.id is not None:
            raise AssertionError('object is already created')
        if self.cache:
            self.id = self.cursor.selectvalue(
                'insert into %s (%s) values (%s) returning %s' %
                (self.table,
                 ', '.join(list(self.cache.keys())),
                 ', '.join(['%s'] * len(self.cache)),
                 self.idfield),
                list(self.cache.values()))
        else:
            self.id = self.cursor.selectvalue(
                'insert into %s default values returning %s' %
                (self.table, self.idfield))
        if commit:
            self.db.db.commit()
        else:
            self.docommit = False

    def commit(self):
        self.docommit = True
        self.db.db.commit()

    def __int__(self):
        return self.id


class EntryDeletable(Entry):
    def delete(self, commit=True):
        'delete a record'

        if self.id is None:
            raise AssertionError('object does not actually exist')

        self.cursor.execute(
            'delete from "%s" where "%s"=%%s' %
            (self.table, self.idfield),
            (self.id,))

        self.id = None

        if commit:
            self.db.commit()


def cached(f):
    @functools.wraps(f)
    def wrapper(self, *args, **kw):
        if f.__name__ in self.cache:
            return self.cache[f.__name__]
        val = f(self, *args, **kw)
        self.cache[f.__name__] = val
        return val
    return wrapper
