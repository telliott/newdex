import unittest
import os
import sys

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
            thor_name = 'ODINSON, THOR'
            loki_name = 'ODINSON, LOKI'
            loki_alt = 'PRINCE OF MISCHIEF'
            series_name = 'MIDGARD CHRONICLES'

            library.db.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Small Books', 'C')")
            library.shelfcodes.load_from_db()

            thor = library.db.getcursor().selectvalue(
                "insert into entity"
                " (entity_name, alternate_entity_name)"
                " values(%s, %s)"
                " returning entity_id", (thor_name, None))

            loki = library.db.getcursor().selectvalue(
                "insert into entity"
                " (entity_name, alternate_entity_name)"
                " values(%s, %s)"
                " returning entity_id", (loki_name, loki_alt))

            series_id = library.db.getcursor().selectvalue(
                "insert into series"
                " (series_name)"
                " values(%s)"
                " returning series_id", (series_name,))

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

            # test the shelfcode index
            self.assertEqual(10, len(list(library.catalog.editions['S'])))

            self.assertEqual(1, len(library.catalog.editions.keys()))

            stats = library.catalog.editions.stats()
            self.assertEqual(1, len(stats.keys()))
            self.assertEqual(10, stats['S'])

            # test the author index
            self.assertEqual(5, len(list(library.catalog.authors[thor_name])))
            self.assertEqual(6, len(list(library.catalog.authors[loki_name])))
            self.assertEqual(6, len(list(library.catalog.authors[loki_alt])))
            self.assertEqual(titleids[0],
                             list(library.catalog.authors[loki_name])[0].id)
            self.assertEqual(titleids[1],
                             list(library.catalog.authors[thor_name])[0].id)

            self.assertEqual(
                loki_name,
                library.catalog.authors.complete('PRINCE OF MISC')[0])

            self.assertEqual(
                thor_name,
                library.catalog.authors.complete('ODINSON, TH')[0])

            self.assertEqual(2,
                             len(library.catalog.authors.complete('ODINSON')))

            self.assertEqual(1,
                             len(library.catalog.authors.complete_checkedout(
                                thor_name)))

            self.assertEqual(0,
                             len(library.catalog.authors.complete_checkedout(
                                loki_name)))

            self.assertEqual(2, len(library.catalog.authors.keys()))

            # test the title index

            self.assertEqual(10, len(library.catalog.titles.keys()))

            self.assertEqual(10,
                             len(library.catalog.titles.search('BOOK')))

            self.assertEqual(
                10,
                len(library.catalog.titles.search_by_author('ODINSON')))

            self.assertEqual(
                5,
                len(library.catalog.titles.search_by_author(thor_name)))

            self.assertEqual(
                6,
                len(library.catalog.titles.search_by_author(loki_name)))

            self.assertEqual(
                0,
                len(library.catalog.titles.search_by_author('HEIMDALL')))

            self.assertEqual(
                6,
                len(library.catalog.titles.search_by_author(loki_alt)))

            self.assertEqual(
                1,
                len(list(library.catalog.titles['BOOK8=BOOK EIGHT'])))

            # the alternate title should be ignored
            self.assertEqual(
                1,
                len(list(library.catalog.titles['BOOK8=NOT BOOK EIGHT'])))

            self.assertEqual(
                1,
                len(library.catalog.titles.complete('BOOK8')))

            self.assertEqual('BOOK8=BOOK EIGHT',
                             library.catalog.titles.complete('BOOK8')[0])
            self.assertEqual('BOOK8=BOOK EIGHT',
                             library.catalog.titles.complete('BOOK EIGHT')[0])
            self.assertEqual(
                10,
                len(library.catalog.titles.complete('BOOK')))

            self.assertEqual(
                5,
                len(library.catalog.titles.complete('BOOK', thor_name)))

            self.assertEqual(
                1,
                len(library.catalog.titles.complete_checkedout('BOOK')))

            self.assertEqual(
                'BOOK3',
                library.catalog.titles.complete_checkedout('BOOK')[0])

            self.assertEqual(
                1,
                len(library.catalog.titles.complete_checkedout('BOOK',
                                                               'ODINSON, T')))

            self.assertEqual(
                0,
                len(library.catalog.titles.complete_checkedout('BOOK',
                                                               loki_name)))

            title = next(library.catalog.titles['BOOK8=BOOK EIGHT'])
            self.assertEqual(f'{loki_name}={loki_alt}', title.authors[0])
            self.assertEqual(titleids[8], title.id)

            # test the series index

            self.assertEqual(1, len(list(library.catalog.series.keys())))
            self.assertEqual(series_name, library.catalog.series.keys()[0])
            self.assertEqual(series_id,
                             library.catalog.series.search('MIDGAR')[0])
            self.assertEqual(series_name,
                             library.catalog.series.complete('MIDGAR')[0])

            self.assertEqual(10,
                             len(list(library.catalog.series[series_name])))

        finally:
            library.db.db.close()


if __name__ == '__main__':
    unittest.main()
