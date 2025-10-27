import math
from datetime import datetime

from mitsfs.core import db
from mitsfs.util import coercers
from mitsfs.dex.books import Book
from mitsfs.util import exceptions
from mitsfs.circulation import members

# the default size for each section. If there are more than INVENTORY_SIZE
# books, it'll be broken into two sections, etc.
INVENTORY_SIZE  = 500

'''
Inventory has three database tables. The first simply opens and closes an
inventory, putting the library into inventory mode. 

The second table defines how many sections the library is broken into, and 
then keeps track of who has checked out each section and which sections are 
complete.

The third table keeps track of the books that are discovered missing from 
the library (and lets you note when they are found)
'''
class Inventories(object):
    def __init__(self, db):
        '''
        Basic access to the inventory object

        Parameters
        ----------
        db : Database
            database object to query against

        Returns
        -------
        None.

        '''
        self.db = db

    def get_open(self):
        '''
        Returns
        -------
        Inventory
            An Inventory object if there's an inventory object. 
            Otherwise, None.

        '''
        invid = self.db.cursor.selectvalue(
            'select inventory_id from inventory'
            ' where inventory_closed is null')
        return None if not invid else Inventory(self.db, invid)

    def create(self, desc, shelfcodes):
        '''
        Open a new inventory

        Parameters
        ----------
        desc : str
            A string describing this inventory.

        Raises
        ------
        exceptions.InventoryAlreadyOpenException
            Raised if there is already an inventory open.

        Returns
        -------
        Inventory
            The newly opened inventory object.

        '''
        if self.get_open():
            raise exceptions.InventoryAlreadyOpenException(
                'Cannot have multiple inventories open')
        
        inv = Inventory(self.db)
        inv.open_date = datetime.now()
        inv.description = desc
        inv.create(shelfcodes)
        return inv

    
class Inventory(db.Entry):
    def __init__(self, db, inventory_id=None, **kw):
        '''
        If there's a row in the inventory table that hasn't been closed,
        the library is in inventory mode.

        Parameters
        ----------
        db : Database
            The database with the inventory table.
        inventory_id : int, optional
            Use if loading a specific inventory from the database. 
            The default is None.
        **kw : 
            Fields to set (open_date, description, close_date) if creating a
            new inventory

        Returns
        -------
        None.

        '''
        super().__init__('inventory', 'inventory_id', db, inventory_id, **kw)

    open_date = db.Field('inventory_stamp', 
                               coercer=coercers.coerce_datetime_no_timezone)
    close_date = db.Field('inventory_closed', 
                               coercer=coercers.coerce_datetime_no_timezone)
    description = db.Field('inventory_desc')

    @property 
    def sections(self):
        '''
        Return the section objects associated with this inventory session

        Returns
        -------
        list (InventorySection)
            The sections associated with this inventory.

        '''
        return InventorySections(self.db, self.id)
    
    def create(self, shelfcodes):
        '''
        Creates the inventory, and also figures out the sections for the 
        shelfcodes provided

        Parameters
        ----------
        shelfcodes : List(Shelfcode objects)
            The shelfcodes to create sections for.

        Returns
        -------
        None.

        '''
        super().create(commit=False)
        counts = shelfcodes.stats()
        for shelfcode in shelfcodes.values():
            if shelfcode.code not in counts:
                continue
            count = counts[shelfcode.code]
            sections = math.ceil(count / INVENTORY_SIZE)
            self.sections.add_shelfcode(shelfcode, sections)
        self.db.commit()
    
    
    def close(self):
        '''
        Finishes up the inventory. Any books still missing will be withdrawn
        from the library, then the close date will be added to the inventory
        row, returning the library to normal function.

        Returns
        -------
        None.

        '''
        for book in self.get_missing_books():
            book.withdraw()
        self.db.commit()
        self.close_date = datetime.now()

    def report_missing_book(self, book):
        '''
        Register that a book has been discovered missing during the inventory

        Parameters
        ----------
        book : Book
            The book that is missing.

        Returns
        -------
        None.

        '''
        self.cursor.execute(
            'insert into inventory_missing ('
            ' inventory_id, book_id, shelfcode, located)'
            ' values (%s, %s, %s, %s)',
            (self.id, book.id, book.shelfcode.code, False))
        self.db.commit()
        
    def find_book(self, book):
        '''
        Report a book that was previously missing has been located.

        Parameters
        ----------
        book : Book
            The book that has been found.

        Returns
        -------
        None.

        '''
        self.cursor.execute(
            'update inventory_missing'
            ' set located = %s'
            ' where inventory_id = %s and book_id = %s',
            (True, self.id, book.id))
        self.db.commit()

    def get_missing_books(self, shelfcode=None):
        '''
        A list of the books that are missing in this inventory.

        Parameters
        ----------
        shelfcode : Shelfcode object, optional
            Restrict the missing books to only this shelfcode.

        Returns
        -------
        list(Book)
            The missing books.

        '''
        s = ''
        args = [self.id]
        if shelfcode:
            s = ' and shelfcode = %s'
            args.append(shelfcode.code)
            
        return [Book(self.db, i) for i in 
                self.cursor.fetchlist(
                    'select book_id from inventory_missing'
                    ' where inventory_id = %s'
                    + s +
                    ' and not located',
                    args
                    )]
    
    def stats(self, shelfcode=None):
        '''
        Get the count of missing books for each shelfcode. Returns an int
        if no shelfcode is provided, otherwise a dict of shelfcode->int

        Parameters
        ----------
        shelfcode : Shelfcode object, optional
            Restrict the stats to just this shelfcode. The default is None.

        Returns
        -------
        dict(str => int) or int

        '''
        if not shelfcode:
            return dict(self.cursor.execute(
                'select shelfcode, count(*)'
                ' from inventory_missing'
                ' where not located'
                ' group by shelfcode order by shelfcode'))

        return self.cursor.selectvalue(
            'select count(*) from inventory_missing'
            ' where shelfcode = %s and not located',
            (shelfcode.code,))
    
    
class InventorySections(object):
    def __init__(self, db, inventory_id):
        '''
        Inventory is broken up into sections. The first level of section is
        the shelfcode, but some of the larger shelfcodes (S and L in
        particular) are too large for one team to work with. So they are 
        broken up into multiple sections, and this class tracks completion

        Parameters
        ----------
        db : Database
            The database that contains the table
        inventory_id : int
            id of the inventory that these sections are in.

        Returns
        -------
        None.

        '''
        self.db = db
        self.inventory_id = inventory_id
    
    def get(self, shelfcode=None, section=None):
        '''
        Get a list of rows in the InventorySection table (as InventorySection
        objects)

        Parameters
        ----------
        shelfcode : Shelfcode object, optional
            Limit to just the sections for one shelfcode. The default is None.
        section : int, optional
            The section to limit it to the one row. The default is None.
            Technically, you can provide a section without a shelfcode, but
            that'll give you some pretty strange results.

        Returns
        -------
        list(InventorySection)
            The InventorySections requested.

        '''
        args = [self.inventory_id]
        shelfcode_query = ''
        section_query = ''
        
        if shelfcode:
            shelfcode_query = ' and shelfcode = %s'
            args.append(shelfcode.code)
        
        if section:
            section_query = ' and section = %s'
            args.append(section)
        
        results = self.db.cursor.execute(
            'select shelfcode, section, member_id, complete'
            ' from inventory_sections'
            ' where inventory_id = %s'
            + shelfcode_query
            + section_query +
            ' order by shelfcode, section',
            args)
        
        return [InventorySection(self.db, *i) for i in results]

    def add_shelfcode(self, shelfcode, section_count):
        '''
        Add a shelfcode (and accompanying sections) to the inventory

        Parameters
        ----------
        shelfcode : Shelfcode object
            The shelfcode we are adding to the library.
        section_count : int
            The number of sections to associate with the shelfcode.

        Raises
        ------
        exceptions.DuplicateEntry:
            The shelfcode already exists in the inventory
            
        Returns
        -------
        None.

        '''
        if self.get(shelfcode):
            raise exceptions.DuplicateEntry('Shelfcode has already been added')
        rows = [(self.inventory_id, shelfcode.code, i, False) 
                for i in range(1, section_count + 1)]
        self.db.cursor.executemany(
           'insert into inventory_sections'
           ' (inventory_id, shelfcode, section, complete)'
           ' values (%s, %s, %s, %s)', 
           rows)
        self.db.commit()
        
    def checkout_section(self, shelfcode, section, member):
        '''
        Claim a section for a member who is going to work on it.

        Parameters
        ----------
        shelfcode : Shelfcode object
            the shelfcode.
        section : int
            The section being claimed.
        member : Member
            The member claiming the section.

        Returns
        -------
        None.

        '''
        self.db.cursor.execute(
           'update inventory_sections set member_id = %s'
           ' where inventory_id = %s'
           ' and shelfcode = %s'
           ' and section = %s', 
           (member.id, self.inventory_id, shelfcode.code, section))
        self.db.commit()

    def complete_section(self, shelfcode, section):
        '''
        Mark a section completed

        Parameters
        ----------
        shelfcode : Shelfcode object
            The shelfcode.
        section : int
            The section in the shelfcode.

        Returns
        -------
        None.

        '''
        self.db.cursor.execute(
           'update inventory_sections set complete = %s'
           ' where inventory_id = %s'
           ' and shelfcode = %s'
           ' and section = %s', 
           (True, self.inventory_id, shelfcode.code, section))
        self.db.commit()

        
class InventorySection(object):
    def __init__(self, db, shelfcode, section, member_id, complete):
        '''
        Just a data object to give you structured access to the rows

        Parameters
        ----------
        db : Database
            The database being used. Only needed as a passthrough to getting
            a member object.
        shelfcode : string
            The shelfcode for this section. Note that this is the code, not 
            the object
        section : int
            The section within this shelfcode.
        member_id : int
            The member who has checked out this section (if any).
        complete : boolean
            Whether the section has been completed..

        Returns
        -------
        None.

        '''
        self.db = db
        self.shelfcode = shelfcode
        self.section = section
        self.complete = complete
        self.member_id = member_id
    
    @property
    def out_to(self):
        '''
        Returns
        -------
        Member
            The member object associated with this section, or None.
        '''
        return members.Member(self.db, 
                              self.member_id) if self.member_id else None

    def __repr__(self):
        return (f'<{self.shelfcode}, {self.section}, '
                f'{self.complete}, {self.member_id}>')