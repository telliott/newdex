import unittest
import os
import sys

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from tests.test_setup import Case

from mitsfs.library import Library
from mitsfs.circulation.members import Member
from mitsfs.dex.series import Series
from mitsfs.dex.authors import Author
from mitsfs.dex.books import Book
from mitsfs.dex.shelfcodes import Shelfcode
from mitsfs.dex.titles import Title, sanitize_title
from mitsfs.util import exceptions

from mitsfs.dex.inventory import Inventories, Inventory, InventorySection, \
    InventorySections, INVENTORY_SIZE

# Titles are tested in test_indexes.py
class InventoryTest(Case):
    def test_inventory(self):
        library = Library(dsn=self.dsn)
        try:
            library.db.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Small Books', 'C'), ('L', 'Large Books', 'C')")
            library.db.getcursor().execute(
                'insert into'
                ' member(first_name, last_name, key_initials, email,'
                ' address, phone, pseudo)'
                " values ('Thor', 'Odinson', 'TO', 'thor@asgard.com',"
                " 'Asgard', '', 'f')")
            library.db.commit()
            library.shelfcodes.load_from_db()
            shelf_s = library.shelfcodes['S']
            shelf_l = library.shelfcodes['L']
            thor = library.members.find('Thor')[0]
            
            self.assertEqual(500, INVENTORY_SIZE)
            for i in range(1, 551):
                library.catalog.add_from_dexline(f'AUTHOR<SMALL{i}<SERIES<S')
            for i in range(1, 51):                
                library.catalog.add_from_dexline(f'AUTHOR<LARGE{i}<SERIES<L')

            self.assertEqual(library.inventory, None)

            inv = Inventories(library.db)
            self.assertEqual(inv.get_open(), None)
            inv.create("test inventory", library.shelfcodes)
            library.reset_inventory()
            self.assertRaises(exceptions.InventoryAlreadyOpenException,
                              inv.create, "bad test", library.shelfcodes)
            
            open_inv = inv.get_open()
            self.assertNotEqual(open_inv, None)
            self.assertEqual(library.inventory.id, open_inv.id)
            self.assertEqual('test inventory', open_inv.description)
            
            self.assertEqual(3, len(open_inv.sections.get()))
            self.assertEqual(2, len(open_inv.sections.get(shelf_s)))
            self.assertEqual(1, len(open_inv.sections.get(shelf_s, 2)))
            
            for i in range(1,11):
                book = library.catalog.grep(
                    f'AUTHOR<SMALL{i}')[0].books[0]
                open_inv.report_missing_book(book)
                book = library.catalog.grep(
                    f'AUTHOR<LARGE{i}')[0].books[0]
                open_inv.report_missing_book(book)
            
            stats = open_inv.stats()
            self.assertEqual(2, len(stats))
            self.assertEqual(10, stats['S'])
            self.assertEqual(10, stats['L'])
            self.assertEqual(10, open_inv.stats(shelf_s))
            self.assertEqual(10, open_inv.stats(shelf_l))

            for i in range(1, 6):
                book = library.catalog.grep(
                    f'AUTHOR<SMALL{i}')[0].books[0]
                open_inv.find_book(book)

            stats = open_inv.stats()
            self.assertEqual(2, len(stats))
            self.assertEqual(5, stats['S'])
            self.assertEqual(10, stats['L'])
            
            missing_books = []
            for i in range(6, 11):
                missing_books.append(
                    library.catalog.grep(f'AUTHOR<SMALL{i}')[0].books[0])
            
            
            db_missing = open_inv.get_missing_books(shelf_s)
            self.assertEqual(5, len(db_missing))
                              
            for book in db_missing:
                self.assertIn(book, missing_books)
            
            self.assertRaises(exceptions.DuplicateEntry, 
                              open_inv.sections.add_shelfcode, shelf_s, 1)
            sa = Shelfcode(library.db, code='SA')
            open_inv.sections.add_shelfcode(sa, 2)
            self.assertEqual(5, len(open_inv.sections.get()))
           
            open_inv.sections.checkout_section(shelf_s, 1, thor)
            self.assertEqual(thor.id, 
                             open_inv.sections.get(shelf_s, 1)[0].member_id)
            self.assertEqual(thor, open_inv.sections.get(shelf_s, 1)[0].out_to)
            
            
            open_inv.sections.complete_section(shelf_s, 1)
            self.assertTrue(open_inv.sections.get(shelf_s, 1)[0].complete)
            
            
            old_counts = library.shelfcodes.stats()
            self.assertEqual(550, old_counts['S'])
            self.assertEqual(50, old_counts['L'])
            
            open_inv.close()

            new_counts = library.shelfcodes.stats()
            self.assertEqual(545, new_counts['S'])
            self.assertEqual(40, new_counts['L'])

        finally:
            library.db.db.close()


if __name__ == '__main__':
    unittest.main()
