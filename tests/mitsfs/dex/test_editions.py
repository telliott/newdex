from mitsfs.dex.shelfcodes import Shelfcodes
from mitsfs.dex.editions import Edition, Editions, InvalidShelfcode
import sys
import os
import unittest

testdir = os.path.dirname(__file__)
srcdir = '../../../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))


class EditionsTest(unittest.TestCase):

    def testEdition(self):
        x = Edition('C/P:2')
        y = Edition('@D400')

        self.assertRaises(InvalidShelfcode, Edition, 'FOOBAR')

        self.assertEqual(2, x.count)
        self.assertEqual('C/P', x.shelfcode)
        self.assertEqual(False, x.series_visible)
        self.assertEqual(None, x.double_info)
        self.assertEqual(2, int(x))
        self.assertEqual('C/P:2', str(x))
        self.assertEqual('Edition(series_visible: False, shelfcode: C/P, ' +
                         'double_info: None, count: 2)', repr(x))

        self.assertEqual(1, y.count)
        self.assertEqual('D', y.shelfcode)
        self.assertEqual(True, y.series_visible)
        self.assertEqual('400', y.double_info)
        self.assertEqual(1, int(y))
        self.assertEqual('@D400', str(y))
        self.assertEqual('Edition(series_visible: True, shelfcode: D, ' +
                         'double_info: 400, count: 1)', repr(y))

    def testEditions(self):
        x = Editions({'C/P': 2, 'L': 1})
        y = Editions('C/P:2,L')

        self.assertEqual(str(x), str(y))

        self.assertEqual(2, x['C/P'].count)
        self.assertEqual(1, x['L'].count)
        self.assertFalse(x['L'].series_visible)
        self.assertEqual(2, y['C/P'].count)
        self.assertEqual(1, y['L'].count)

        self.assertEqual(['C/P:2', 'L'], y.list())
        self.assertEqual('C/P:2,L', str(y))

        self.assertEqual(None, y['PA'])
        self.assertEqual(True, bool(y))

        z = Editions(y)
        self.assertEqual(repr(z), repr(y))

    def testEditionsMath(self):
        x = Editions('C/P:2,L,D400:2')
        y = Editions('L, D300, PA:2')

        self.assertEqual(5, int(x))

        z = x + y
        self.assertEqual(2, z['L'].count)
        self.assertEqual(3, z['D'].count)
        self.assertEqual(9, int(z))

        z = x - y
        self.assertEqual(2, z['C/P'].count)
        self.assertEqual(None, z['L'])
        self.assertEqual(1, z['D'].count)

        z = -x
        self.assertEqual(-2, z['C/P'].count)
        self.assertEqual(-1, z['L'].count)

        self.assertEqual(0, len(x + z))

        remove = Editions('L:-2')
        z = x + remove
        self.assertEqual(4, int(z))
        self.assertEqual(2, len(z.keys()))

if __name__ == '__main__':
    Shelfcodes.generate_shelfcode_regex(['L', 'C/P', 'PA'], ['D'])
    unittest.main()
