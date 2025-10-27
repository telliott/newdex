#!/usr/bin/python

import re

from mitsfs.core import db
from mitsfs.util.exceptions import InvalidShelfcode
from mitsfs.util import coercers


class Shelfcode(db.Entry):
    '''
    
    A shelfcode is a short string of characters that lets you know what section
    of the library you can find a book in.
    
    It is usually identified by that short string, but also has an underlying
    integer id in the db for joining with other tables.
    
    '''
    def __init__(self, db, shelfcode_id=None, **kw):
        super().__init__('shelfcode', 'shelfcode_id',
                         db, shelfcode_id, **kw)

    code = db.InfoField('shelfcode')
    description = db.InfoField('shelfcode_description')
    code_type = db.InfoField('shelfcode_type')
    code_class = db.InfoField('shelfcode_class')
    replacement_cost = db.InfoField('replacement_cost')
    is_double = db.InfoField('shelfcode_doublecode',
                             coercer=coercers.coerce_boolean)

    @property
    def detail(self):
        return "%s (%s)" % (self.code, self.description)
   
    def __str__(self):
        return self.code


    def __int__(self):
        '''
        Coercing to an int simply returns the shelfcode ID
        '''
        return self.id
    
    def __eq__(self, other):
        '''
        Do the two objects have the same id
        '''
        return self.id == other.id
    
    def deprecate(self):
        '''
        Deprecates this shelfcode so that it won't show up in the
        lists any more

        Parameters
        ----------
        db : TYPE
            DESCRIPTION.

        Returns
        -------
        None.

        '''
        self.db.getcursor().execute("update shelfcode"
                                    " set shelfcode_type = 'D'"
                                    " where shelfcode_id = %s", (self.id))
        self.db.commit


    def commit(self, db):
        '''
        add a shelfcode to the db
    
        @return: the shelfcode with db id now included
        '''
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


parse_shelfcodes = None


class Shelfcodes(dict):
    '''
    A dictionary of shelfcode objects, keyed by shelfcode
    
    Loaded from the db on initialization
    '''
    def __init__(self, db):
        super().__init__()

        self.db = db
        self.load_from_db()

    def load_from_db(self):
        '''
        Making a separate db load method for easier reloading
        '''
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
            s = Shelfcode(self.db, s_id, code=shelfcode,
                          description=description,
                          code_type=ctype, replacement_cost=cost,
                          code_class=code_class, is_double=is_double)
            super().__setitem__(s.code, s)
            if is_double:
                double.append(shelfcode)
            else:
                normal.append(shelfcode)
        Shelfcodes.generate_shelfcode_regex(normal, double, True)

    # Tested in test_indexes
    def get_titles(self, key):
        '''
        A list of all the Titles in a shelfcode

        Parameters
        ----------
        key : Shelfcode
            A shelfcode. Can contain the double information.

        Returns
        -------
        list (Title)
            Titles for each title that has a copy in this shelfcode.

        '''
        c = self.db.getcursor()
        try:
            from mitsfs.dex.editions import Edition
            e = Edition(key)
            code = e.shelfcode
            doublecrap = e.double_info
        except InvalidShelfcode:
            code, doublecrap = key, None
        if code not in self.keys():
            raise InvalidShelfcode(f'shelfcode {code} not found')

        q = (
            'select title_id'
            ' from title'
            '  natural join title_responsibility'
            '  natural join entity'
            '  natural join title_title'
            '  natural join book'
            '  natural join shelfcode'
            ' where order_responsibility_by = 0 and order_title_by = 0'
            '  and shelfcode = upper(%s)'
            )
        values = [code]
        if doublecrap:
            q += ' and upper(doublecrap) = upper(%s)'
            values += [doublecrap]
        q += ' order by entity_name, title_name'
        from mitsfs.dex.titles import Title
        return (
            Title(self.db, title_id[0])
            for title_id
            in c.execute(q, values))

    def stats(self):
        '''
        Helper function to show book counts for each shelfcode. Ignores
        doubles data

        Returns
        -------
        list(Tuple)
            A tuple of (shelfcode, count).

        '''
        c = self.db.getcursor()
        return dict(c.execute(
            "select shelfcode, count(shelfcode)"
            " from"
            "  book"
            "  natural join shelfcode"
            " where not withdrawn"
            " group by shelfcode"))

    # Tested in test_indexes
    def grep(self, s):
        '''
        Grep assistance.

        Parameters
        ----------
        s : string
            Shelfcode to search/filter on

        Returns
        -------
        List of title_ids that have a book in this shelfcode

        '''
        if s not in self: 
            return []
        
        c = self.db.getcursor()
        return c.fetchlist(
            'select distinct title_id'
            ' from book'
            ' where not withdrawn and shelfcode_id = %s',
            (self[s].id,))

    @staticmethod
    def generate_shelfcode_regex(normal, double, force=False):
        '''
        Generates the correct regex to evaluate shelfcodes. Static method
        so that non-db contexts can set it if they need to (testing)
        '''
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
                           super().__getitem__(key).id)
                          for key in self.keys()])
