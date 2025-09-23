import unittest
import os
import sys
import datetime

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from tests.test_setup import Case

from mitsfs.library import Library
from mitsfs.dex import indexes


class IndexesTest(Case):
    def test_indexes(self):
        library = Library(dsn=self.dsn)
        try:
            library.db.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Small Books', 'C')")
            library.shelfcodes.load_from_db()

            thor = library.db.getcursor().selectvalue(
                "insert into entity"
                " (entity_name, alternate_entity_name)"
                " values(%s, %s)"
                " returning entity_id", ('ODINSON, THOR', None))

            loki = library.db.getcursor().selectvalue(
                "insert into entity"
                " (entity_name, alternate_entity_name)"
                " values(%s, %s)"
                " returning entity_id", ('ODINSON, LOKI',
                                         'PRINCE OF MISCHIEF'))

            series_id = library.db.getcursor().selectvalue(
                "insert into series"
                " (series_name)"
                " values(%s)"
                " returning series_id", ('MIDGARD CHRONICLES',))

            titleids = []
            for i in range(10):

                title_id = library.db.getcursor().selectvalue(
                    'insert into title default values returning title_id')

                titleids.append(title_id)
                library.db.getcursor().execute(
                    "insert into"
                    " title_title"
                    " (title_id, title_name, order_title_by, alternate_name)"
                    " values(%s, %s, %s, %s)",
                    (title_id, f'BOOK{i}', 0,
                     "BOOK EIGHT" if i == 8 else None))

                library.db.getcursor().execute(
                    "insert into"
                    " title_responsibility"
                    " (title_id, entity_id, order_responsibility_by)"
                    " values(%s, %s, %s)",
                    (title_id, thor if i % 2 else loki, 0))

                library.db.getcursor().execute(
                     "insert into"
                     " title_series"
                     " (title_id, series_id, series_index)"
                     " values(%s, %s, %s)",
                     (title_id, series_id, i))

                book_id = library.db.getcursor().selectvalue(
                    "insert into"
                    " book"
                    " (title_id, shelfcode_id)"
                    " values(%s, %s)"
                    " returning book_id",
                    (title_id, library.shelfcodes['S'].id))
                
                if i == 3:
                    # Add a book to be checked out
                    library.db.getcursor().execute(
                        "insert into"
                        " checkout"
                        " (book_id, member_id)"
                        " values(%s, %s)",
                        (book_id, 10000))
                    

            # Add loki to a book by thor
            library.db.getcursor().execute(
                "insert into"
                " title_responsibility"
                " (title_id, entity_id, order_responsibility_by)"
                " values(%s, %s, %s)",
                (titleids[5], loki, 1))


            self.assertEqual(10, len([i for i in
                                      library.catalog.editions['S']]))

            self.assertEqual(6, len([i for i in
                                     library.catalog.authors['ODINSON, LOKI']]
                                    ))

            self.assertEqual(5, len([i for i in
                                     library.catalog.authors['ODINSON, THOR']]
                                    ))

            self.assertEqual(6,
                             len([i for i in
                                  library.catalog.authors['PRINCE OF MISCHIEF']
                                  ]))
            self.assertEqual(
                'ODINSON, LOKI',
                library.catalog.authors.complete('PRINCE OF MISC')[0])

            self.assertEqual(
                'ODINSON, THOR',
                library.catalog.authors.complete('ODINSON, TH')[0])

            self.assertEqual(2,
                             len(library.catalog.authors.complete('ODINSON')))
            
            self.assertEqual(1,
                            len(library.catalog.authors.complete_checkedout(
                                'ODINSON, THOR')))
            self.assertEqual(0,
                            len(library.catalog.authors.complete_checkedout(
                                'ODINSON, LOKI')))





        finally:
            library.db.db.close()


if __name__ == '__main__':
    unittest.main()
