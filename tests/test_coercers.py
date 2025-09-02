import sys
import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from mitsfs.dex.shelfcodes import Shelfcodes, Shelfcode
from mitsfs.dex.coercers import coerce_datetime_no_timezone, coerce_boolean
from mitsfs.dex.coercers import coerce_shelfcode, uncoerce_shelfcode

'''
The shelfcode coercers are tested in the Shelfcode tests, where the 
infrasturcture is better set up for them.
'''
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


if __name__ == '__main__':
    unittest.main()
