import unittest
import os
import sys

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from mitsfs.dex.membership_info import MembershipInfo, MembershipOptions
from mitsfs.dexdb import DexDB
from tests.test_setup import Case


class TestShelfcodes(Case):
    def test_shelfcodes(self):
        try:
            db = DexDB(dsn=self.dsn)
            y_id = db.getcursor().selectvalue(
                "select membership_type_id from membership_type"
                " where membership_type = 'Y'"
                )
            
            # membership types are preset by the schema, so we don't need to 
            # load them

            s = MembershipOptions(db)
            self.assertEqual('1 year Nonstudent', s['1'].description)
            self.assertEqual(15.0, s['1'].cost)
            self.assertEqual('1 year Student', s['!'].description)
            self.assertTrue(s['!'].active)
            self.assertNotIn('Y', s)

            self.assertEqual(list(s.keys()), 
                             ['P', 'L', 'T', '1', '4', '!', '$'])

            # The Y type is deprecated, but we can still access it directly
            y = MembershipInfo(db, y_id)
            self.assertEqual('old yearly', y.description)
            self.assertFalse(y.active)

        finally:
            db.db.close()


if __name__ == "__main__":
    unittest.main()
