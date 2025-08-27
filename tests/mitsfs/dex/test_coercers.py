import sys
import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

testdir = os.path.dirname(__file__)
srcdir = '../../../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from mitsfs.dex.shelfcodes import Shelfcodes, Shelfcode
from mitsfs.dex.coercers import coerce_datetime_no_timezone, coerce_boolean
from mitsfs.dex.coercers import coerce_shelfcode, uncoerce_shelfcode

test_shelfcodes = [
    (1195341, 'L', 'Large Fiction', 'C', 40, 'F', 'f'),
    (1195344, 'S', 'Small Fiction', 'C', 15, 'F', 'f'),
    (74, 'SFWA-TD', 'SFWA Tor Double', 'D', 40, 'D', 't')]


def fake_load(self, db):
    return test_shelfcodes


@patch.object(Shelfcodes, 'load_from_db', fake_load)
class CoercersTest(unittest.TestCase):

    def test_coerce_datetime_no_timezone(self):
        x = datetime(2020, 5, 17, 12, 15, 27,
                     tzinfo=ZoneInfo(key='Europe/Amsterdam'))

        self.assertEqual('2020-05-17 12:15:27',
                         str(coerce_datetime_no_timezone(x)))

    def test_coerce_boolean(self):
        self.assertEqual(True, coerce_boolean(1))
        self.assertEqual(True, coerce_boolean('t'))
        self.assertEqual(False, coerce_boolean(0))
        self.assertEqual(False, coerce_boolean(''))

    def test_coerce_shelfcode(self):
        d = object

        self.assertEqual('SFWA-TD', coerce_shelfcode(74, d).code)
        self.assertEqual('L', coerce_shelfcode(1195341, d).code)

    def test_uncoerce_shelfcode(self):
        x = Shelfcode(25, 'L', 'desc', 'C', 40, 'F', None)
        y = 25

        self.assertEqual(25, uncoerce_shelfcode(x))
        self.assertEqual(25, uncoerce_shelfcode(y))


if __name__ == '__main__':
    unittest.main()
