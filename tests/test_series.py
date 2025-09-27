import unittest
import os
import sys

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from tests.test_setup import Case

from mitsfs.dex.series import Series
from mitsfs.library import Library


# SeriesIndex is tested in test_indexes.py
class SeriesTest(Case):
    def test_series(self):
        library = Library(dsn=self.dsn)
        try:
            thor_name = 'ODINSON, THOR'
            series_name = 'MIDGARD CHRONICLES'

            series = Series(library.db)
            series.series_name = series_name
            series.create()

            thor = library.db.getcursor().selectvalue(
                "insert into entity"
                " (entity_name, alternate_entity_name)"
                " values(%s, %s)"
                " returning entity_id", (thor_name, None))

            # do them backwards to prove sort is OK
            for i in range(10, 0, -1):

                title_id = library.db.getcursor().selectvalue(
                    'insert into title default values returning title_id')

                library.db.getcursor().execute(
                    "insert into"
                    " title_title"
                    " (title_id, title_name, order_title_by, alternate_name)"
                    " values(%s, %s, %s, %s)",
                    (title_id, f'BOOK{i}', 0, None))

                library.db.getcursor().execute(
                    "insert into"
                    " title_responsibility"
                    " (title_id, entity_id, order_responsibility_by)"
                    " values(%s, %s, %s)",
                    (title_id, thor, 0))

                library.db.getcursor().execute(
                     "insert into"
                     " title_series"
                     " (title_id, series_id, series_index, order_series_by)"
                     " values(%s, %s, %s, %s)",
                     (title_id, series.id, i, i))

            # Create a new series object with the created series id
            testcase = Series(library.db, series.id)

            self.assertEqual(10, len(testcase))

            series_list = list(testcase)
            self.assertEqual(10, len(series_list))

            i = 1
            for title in series_list:
                self.assertEqual(f'{series_name} {i}', str(title.series))
                i += 1

        finally:
            library.db.db.close()


if __name__ == '__main__':
    unittest.main()
