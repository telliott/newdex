#!/usr/bin/python

import re
from collections import namedtuple


'''
add a shelfcode to the database

@return: the shelfcode with database id now included
'''
def commit(shelfcode, database):
    c = database.getcursor()
    shelfcode.id = c.selectvalue("insert into shelfcode values"
                      " (%s, %s, %s, %s, %, %s)"
                      " returning shelfcode_id", 
                  (shelfcode.shelfcode, shelfcode.description, 
                   shelfcode.code_type, shelfcode.cost, 
                   shelfcode.code_class, shelfcode.is_double))
    database.commit 
    return shelfcode

'''
deprecates this shelfcode so that it won't show up in the lists any more
'''
def deprecate(shelfcode, database):
    database.getcursor().execute("update shelfcode"
                    " set shelfcode_type = 'D'"
                    " where shelfcode_id = %s", (shelfcode.id))
    database.commit 


'''

A shelfcode is a short string of characters that lets you know what section 
of the library you can find a book in.

It is usually identified by that short string, but also has an underlying
integer id in the database for joining with other tables.

'''
class Shelfcode(namedtuple('Shelfcode', ['shelfcode_id', 'code', 'description', 
                                         'code_type',  'cost', 'code_class', 
                                         'is_double'])):
        
    def __str__(self):
        return "%s (%s)" % (self.code, self.description)
        
    '''
    Coercing to an int simply returns the shelfcode ID
    '''
    def __int__(self):
        return self.shelfcode_id
    
'''

A dictionary of shelfcode objects, keyed by shelfcode

Loaded from the database on initialization

'''
parse_shelfcodes = None

class Shelfcodes(dict):
        
    def __init__(self, db):
        #keep track of these two lists to build the matching regex
        double = []
        normal = []
        super().__init__()
        for row in self.load_from_db(db):
            (s_id, shelfcode, description, ctype, 
             cost, code_class, is_double) = row
            s = Shelfcode(s_id, shelfcode, description, ctype, cost, 
                          code_class, is_double)
            super().__setitem__(s.code, s)
            if is_double:
                double.append(shelfcode)
            else:
                normal.append(shelfcode)
            Shelfcodes.generate_shelfcode_regex(normal, double)
        
    '''
    Making a separate database load method for easier mocking
    '''
    def load_from_db(self, db):
        c = db.getcursor()
        c.execute("select * from shelfcode where shelfcode_type != 'D'")
        return c.fetchall()


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

    '''
    Some parts of the system need to do a lookup to get a shelfcode (they 
    are after the id, usually). But they are passing a function around 
    and calling that function with a db and the key. So this is a standard
    get call, but taking a DB argument first (and throwing it away)
    '''
    def get_with_db_param(self, db, key):
        if key in self:
            return self[key]
        raise 
    
    def __repr__(self):
        return "\n".join(["%s => %s (%s)" % 
                          (key,
                           super().__getitem__(key).description, 
                           super().__getitem__(key).shelfcode_id)
                          for key in self.keys()])