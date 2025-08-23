#!/usr/bin/python
'''

code for manipulating pinkdexen stored in postgres databases

'''


import functools
import logging
import os
import re

import psycopg2
import psycopg2.extensions


__all__ = [
    'Database', 'Field', 'ReadField', 'StaticField', 'ReadFieldUncached',
    'Entry', 'cached', 'coerce_datetime', 'EntryDeletable',
    ]


class EasyCursor(psycopg2.extensions.cursor):
    def hid(self):
        i = id(self)
        if i < 0:
            return '%x' % (2**32 - i)
        else:
            return '%x' % i

    def execute(self, sql, args=None):
        log = logging.getLogger('mitsfs.sql')
        log.debug('%s', self.mogrify(sql, args))
        try:
            psycopg2.extensions.cursor.execute(self, sql, args)
        except Exception as exc:
            try:
                self.connection.rollback()
            except:
                pass
            log.exception('%s: %s: %s', self.hid(), exc.__class__.__name__, exc)
            raise
        log.debug('%s: %s rows: %d', self.hid(), self.statusmessage, self.rowcount)
        return self

    def selectvalue(self, sql, args=None):
        self.execute(sql, args)
        if self.rowcount == 0:
            return None
        return self.fetchone()[0]
        
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

    def lastseq(self, c=None):
        if c is None:
            c = self.cursor
        (seq_id,) = list(c.execute('select last_value from id_seq'))
        return seq_id


class ValidationError(Exception):
    pass


class ReadFieldUncached(property):
    def __init__(self, fieldname, coercer=None):
        self.field = fieldname
        self.coercer = coercer
        super(ReadFieldUncached, self).__init__(self.get, self.set)

    def get(self, obj):
        command = 'select %s from %s where %s = %%s' \
            % (self.field, obj.table, obj.idfield)
        
        c = obj.cursor.execute(command, (obj.id,))
        if c.rowcount == 0:
            return None
        
        val = c.fetchone()[0]      
        if self.coercer is not None:
            val = self.coercer(obj.db, val)
        return val

    def set(self, obj, val):
        raise AssertionError('Readonly property %s:%s' % (
            repr(obj), self.field))


class StaticField(ReadFieldUncached):
    def get(self, obj):
        if self.field in obj.cache:
            return obj.cache[self.field]
        command = 'select %s from %s where %s = %%s' \
            % (self.field, obj.table, obj.idfield)
        c = obj.cursor.execute(command, (obj.id,))
        if c.rowcount == 0:
            return None
        
        val = c.fetchone()[0]      
        
        if self.coercer is not None:
            val = self.coercer(obj.db, val)
        obj.cache[self.field] = val
        return val


class ReadField(ReadFieldUncached):
    def get(self, obj):
        if self.field in obj.cache:
            return obj.cache[self.field]
        c = obj.cursor.execute(
            'select "%s" from %s where %s = %%s' %
            (self.field, obj.table, obj.idfield),
            (obj.id,))
        
        if c.rowcount == 0:
            return None
        
        val = c.fetchone()[0]      
        
        if self.coercer is not None:
            val = self.coercer(obj.db, val)
        obj.cache[self.field] = val
        return val


def cached(f):
    @functools.wraps(f)
    def wrapper(self, *args, **kw):
        if f.__name__ in self.cache:
            return self.cache[f.__name__]
        val = f(self, *args, **kw)
        self.cache[f.__name__] = val
        return val
    return wrapper


class Field(ReadField):
    def __init__(
            self, fieldname, coercer=None, validator=None,
            filter=lambda d, s: s.strip() if hasattr(s, 'strip') else s
            ):
        self.filter = filter
        self.validator = validator
        super(Field, self).__init__(fieldname, coercer=coercer)

    def set(self, obj, val):
        if self.filter:
            val = self.filter(obj.db, val)
        if self.validator and not self.validator(obj, val):
            raise ValidationError(
                'Validation failed for %s.%s: %s' % (
                    obj.table, self.field, repr(val)))
        if self.coercer is not None:
            obj.cache[self.field] = self.coercer(obj.db, val)
        else:
            obj.cache[self.field] = val
        if not obj.new:
            obj.cursor.execute(
                'update %s set %s = %%s where %s = %%s' %
                (obj.table, self.field, obj.idfield),
                (val, obj.id))
        if obj.docommit:
            obj.db.db.commit()


class Entry(object):
    def __init__(self, table, idfield, db, id_=None, **kw):
        self.db = db
        self.table = table
        self.idfield = idfield
        self.cache_reset()
        self.id = id_
        self.cursor = None
        self.docommit = True
        self._fields = dict(
            (pf, df)
            for (pf, df)
            in ((i, getattr(getattr(self.__class__, i), 'field', None))
                for i in dir(self.__class__))
            if df is not None)
        for (k, v) in kw.items():
            if k not in self._fields:
                raise AssertionError(
                    '%s is not a field of %s' % (k, self.__class__.__name__))
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
            c = self.cursor.execute(
                'insert into %s (%s) values (%s) returning %s' %
                (self.table,
                 ', '.join(list(self.cache.keys())),
                 ', '.join(['%s'] * len(self.cache)),
                 self.idfield),
                list(self.cache.values()))
            result = c.fetchone()
            self.id = result[0] 
        else:
            c = self.cursor.execute(
                'insert into %s default values returning %s' %
                (self.table, self.idfield))
            result = c.fetchone()
            self.id = result[0]
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


def coerce_datetime(_, stamp):
    if stamp is None:
        return stamp
    return stamp.replace(tzinfo=None)
