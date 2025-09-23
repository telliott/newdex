#!/usr/bin/python

import re

from mitsfs.core import db

'''

A shelfcode is a short string of characters that lets you know what section
of the library you can find a book in.

It is usually identified by that short string, but also has an underlying
integer id in the db for joining with other tables.

'''


# Cant' put this into the coercers because it creates a circular dependency
# with the coercer library needing access to shelfcodes
def coerce_boolean(field, db=None):
    if field == 'f':
        return False
    return bool(field)


class Shelfcode(db.Entry):
    def __init__(self, db, shelfcode_id=None, **kw):
        super().__init__('shelfcode', 'shelfcode_id',
                         db, shelfcode_id, **kw)

    shelfcode_id = db.InfoField('shelfcode_id')

    code = db.InfoField('shelfcode')
    description = db.InfoField('shelfcode_description')
    code_type = db.InfoField('shelfcode_type')
    code_class = db.InfoField('shelfcode_class')
    replacement_cost = db.InfoField('replacement_cost')
    is_double = db.InfoField('shelfcode_doublecode', coercer=coerce_boolean)

    def __str__(self):
        return "%s (%s)" % (self.code, self.description)

    '''
    Coercing to an int simply returns the shelfcode ID
    '''

    def __int__(self):
        return self.shelfcode_id

    '''
    deprecates this shelfcode so that it won't show up in the lists any more
    '''

    def deprecate(self, db):
        db.getcursor().execute("update shelfcode"
                               " set shelfcode_type = 'D'"
                               " where shelfcode_id = %s", (self.id))
        db.commit

    '''
    add a shelfcode to the db

    @return: the shelfcode with db id now included
    '''

    def commit(self, db):
        c = db.getcursor()
        # this won't put the id in because it's a named tuple. Need to reload
        # shelfcodes after a commit

        c.selectvalue("insert into shelfcode values"
                      " (%s, %s, %s, %s, %, %s)"
                      " returning shelfcode_id",
                      (self.shelfcode, self.description,
                       self.code_type, self.cost,
                       self.code_class, self.is_double))
        db.commit
        return


'''

A dictionary of shelfcode objects, keyed by shelfcode

Loaded from the db on initialization

'''
parse_shelfcodes = None


class Shelfcodes(dict):

    def __init__(self, db):
        super().__init__()

        self.db = db
        self.load_from_db()
    '''
    Making a separate db load method for easier mocking
    '''

    def load_from_db(self):
        c = self.db.getcursor()
        c.execute("select shelfcode_id, shelfcode, shelfcode_description,"
                  " shelfcode_type, replacement_cost, shelfcode_class,"
                  " shelfcode_doublecode"
                  " from shelfcode where shelfcode_type != 'D'")
        # keep track of these two lists to build the matching regex
        double = []
        normal = []
        for row in c.fetchall():
            (s_id, shelfcode, description, ctype,
             cost, code_class, is_double) = row
            s = Shelfcode(db, s_id, code=shelfcode, description=description,
                          code_type=ctype, replacement_cost=cost,
                          code_class=code_class, is_double=is_double)
            super().__setitem__(s.code, s)
            if is_double:
                double.append(shelfcode)
            else:
                normal.append(shelfcode)
        Shelfcodes.generate_shelfcode_regex(normal, double, True)

    '''
    Generates the correct regex to evaluate shelfcodes. Static method so that
    non-db contexts can set it if they need to (testing)
    '''

    @staticmethod
    def generate_shelfcode_regex(normal, double, force=False):
        global parse_shelfcodes
        if parse_shelfcodes is not None and not force:
            return
        parse_shelfcodes = re.compile(
            '^(@?)' +
            '(?:' +
            '(' + '|'.join(normal) + ')' +
            '|' +
            '(' + '|'.join(double) + r')([-A-Z]?[\d.]+)' +
            ')$'
        )

    def __repr__(self):
        return "\n".join(["%s => %s (%s)" %
                          (key,
                           super().__getitem__(key).description,
                           super().__getitem__(key).shelfcode_id)
                          for key in self.keys()])
