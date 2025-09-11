import unittest
import os
import sys
import datetime

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from mitsfs.core.db import Database
from mitsfs.circulation.timewarps import Timewarps
from tests.test_setup import Case


class DexDBTest(Case):
    def test_timewarps(self):
        try:
            db = Database(dsn=self.dsn)
            tw = Timewarps(db)

            today = datetime.datetime.today()
            six_weeks_ago = today - datetime.timedelta(weeks=6)
            five_weeks_ago = today - datetime.timedelta(weeks=5)
            four_weeks_ago = today - datetime.timedelta(weeks=4)
            three_weeks_ago = today - datetime.timedelta(weeks=3)
            two_weeks_ago = today - datetime.timedelta(weeks=2)
            one_week_ago = today - datetime.timedelta(weeks=1)

            # enter these out of order to check if they are sorted correctly
            tw.add(three_weeks_ago, one_week_ago)
            tw.add(five_weeks_ago, four_weeks_ago)

            # overlapping timewarp with the previous one
            tw.add(two_weeks_ago, today)

            self.assertEqual(3, len(tw))
            self.assertEqual(four_weeks_ago, tw[0].end)

            # no change here
            self.assertEqual(six_weeks_ago,
                             tw.warp_date(six_weeks_ago))

            self.assertEqual(four_weeks_ago,
                             tw.warp_date(five_weeks_ago))

            self.assertEqual(today,
                             tw.warp_date(two_weeks_ago))

            # this one should warp twice
            self.assertEqual(today,
                             tw.warp_date(three_weeks_ago))

            expected_regex = r'Timewarp\([-0-9: \.]+ - [-0-9: \.]+\)'
            self.assertRegex(str(tw[0]), expected_regex)

        finally:
            db.db.close()


if __name__ == '__main__':
    unittest.main()
