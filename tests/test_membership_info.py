import unittest
import os
import sys

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from tests.test_setup import Case

from mitsfs.circulation.membership_types import MembershipType, MembershipTypes
from mitsfs.library import Library


class TestShelfcodes(Case):
    def test_membership_info(self):
        try:
            library = Library(dsn=self.dsn)
            y_id = library.db.getcursor().selectvalue(
                "select membership_type_id from membership_type"
                " where membership_type = 'Y'"
                )
            
            # membership types are preset by the schema, so we don't need to 
            # load them

            s = MembershipTypes(library.db)
            self.assertEqual('1 year Nonstudent', s['1'].description)
            self.assertEqual(15.0, s['1'].cost)
            self.assertEqual('1 year Student', s['!'].description)
            self.assertTrue(s['!'].active)
            self.assertNotIn('Y', s)

            self.assertEqual(list(s.keys()), 
                             ['P', 'L', 'T', '1', '4', '!', '$'])

            # The Y type is deprecated, but we can still access it directly
            y = MembershipType(library.db, y_id)
            self.assertEqual('old yearly', y.description)
            self.assertFalse(y.active)

        finally:
            library.db.db.close()


if __name__ == "__main__":
    unittest.main()
