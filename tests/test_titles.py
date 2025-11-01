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
from mitsfs.dex.titles import Title, sanitize_title, check_for_leading_article
from mitsfs.util import exceptions


# Titles are tested in test_indexes.py
class TitleTest(Case):
    def test_title(self):
        library = Library(dsn=self.dsn)
        try:
            library.db.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Small Books', 'C'), ('L', 'Large Books', 'C')")
            library.shelfcodes.load_from_db()

            odin = Member(library.db, email='odin@asgard.org')
            odin.create()

            title = Title(library.db)
            title.create()
            title_id = title.id
            
            thor_name = 'ODINSON, THOR'
            loki_name = 'ODINSON, LOKI'
            loki_alt = 'PRINCE OF MISCHIEF'
            series_name = 'MIDGARD CHRONICLES'

            series = Series(library.db)
            series.series_name = series_name
            series.create()

            thor = Author(library.db)
            thor.name = thor_name
            thor.create()

            loki = Author(library.db)
            loki.name = loki_name
            loki.alt_name = loki_alt
            loki.create()

            title.add_author(thor)
            title.add_title("TITLE 1", "TITLE ONE")
            title.add_series(series, 3, True)

            # test title sanitization
            self.assertEqual(None, sanitize_title(None))
            self.assertEqual('ABCDE', sanitize_title('a\\b|c=d<e'))
            
            # test article starts
            self.assertTrue(check_for_leading_article('A PROBLEM'))
            self.assertTrue(check_for_leading_article('AN ERROR'))
            self.assertTrue(check_for_leading_article('THE FAUX PAS'))
            self.assertFalse(check_for_leading_article('ALL GOOD'))
            
            
            self.assertEqual("TITLE 1=TITLE ONE", str(title.titles))

            book = Book(library.db, title=title,
                        shelfcode=library.shelfcodes['S'])
            book.create()

            self.assertEqual(1, len(title.authors))
            self.assertEqual(thor_name, title.authors[0])
  
            title.add_author(loki)
            self.assertEqual(2, len(title.authors))
            self.assertEqual(thor_name, title.authors[0])
            self.assertEqual(str(loki), title.authors[1])
           
            title.remove_author(loki)
            self.assertRaises(exceptions.NotFoundException,
                              title.remove_author, loki)
            db_title = Title(library.db, title_id)
            self.assertEqual(1, len(db_title.authors))
            self.assertEqual(thor_name, db_title.authors[0])
            title.add_author(loki)
            title = Title(library.db, title_id)

            self.assertEqual(2, len(title.author_objects))
            self.assertEqual(thor_name, title.author_objects[0].name)
            self.assertEqual(loki_name, title.author_objects[1].name)
            self.assertEqual(f'{thor}', str(title.author_objects[0]))
            self.assertEqual(f'{loki_name}={loki_alt}',
                             str(title.author_objects[1]))

            self.assertEqual(f'@{series_name} 3', title.series[0])
            self.assertRaises(exceptions.DuplicateEntry,
                              title.add_author, thor)
            self.assertRaises(exceptions.DuplicateEntry,
                              title.add_author, loki)
            self.assertRaises(exceptions.DuplicateEntry,
                              title.add_series, series)

            title.add_title("TITLE 2")
            self.assertEqual("TITLE 1=TITLE ONE|TITLE 2", str(title.titles))

            self.assertRaises(exceptions.DuplicateEntry,
                              title.add_title, 'TITLE 1')
            self.assertRaises(exceptions.DuplicateEntry,
                              title.add_title, 'TITLE 2', 'TITLE TWO')

            self.assertEqual(1, len(title.books))
            self.assertEqual('S', title.books[0].shelfcode.code)
            self.assertEqual(False, title.books[0].visible)

            self.assertEqual('S', str(title.codes))
            book = Book(library.db, title=title,
                        shelfcode=library.shelfcodes['S'])
            book.create()
            self.assertEqual('S:2', str(title.codes))
            book = Book(library.db, title=title,
                        shelfcode=library.shelfcodes['L'])
            book.create()
            self.assertEqual('L,S:2', str(title.codes))

            self.assertEqual(f'{thor_name}|{loki_name}={loki_alt}'
                             f'<TITLE 1=TITLE ONE|TITLE 2'
                             f'<@{series_name} 3'
                             f'<L,S:2', str(title))

            self.assertEqual('Title 1 [@Midgard Chronicles 3]'
                             '|Title 2 [@Midgard Chronicles 3]',
                             title.nicetitle())

            self.assertFalse(title.checkedout)
            checkout = book.checkout(odin)
            self.assertTrue(title.checkedout)
            checkout.checkin()
            self.assertFalse(title.checkedout)

            self.assertEqual(0, len(title.withdrawn_books))
            for book in title.books:
                if book.out:
                    book.checkin()
                book.withdraw()
            self.assertEqual(3, len(title.withdrawn_books))

        finally:
            library.db.db.close()


if __name__ == '__main__':
    unittest.main()
