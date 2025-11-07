#!/usr/bin/python

import sys
import os
import unittest

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from mitsfs.core.dexline import DexLine
from mitsfs.dex.shelfcodes import Shelfcodes
from mitsfs.util import utils


class DexlineTest(unittest.TestCase):

    def testFieldtuple(self):
        self.assertEqual((), utils.FieldTuple())
        t = utils.FieldTuple('abc|def')
        self.assertEqual(('abc', 'def'), t)
        self.assertEqual('abc|def', str(t))
        self.assertEqual("FieldTuple(('abc', 'def'))", repr(t))

    def testDexline(self):
        Shelfcodes.generate_shelfcode_regex(['P', 'H'], ['D'], force=True)
        self.assertEqual('<<<', str(DexLine()))
        self.assertEqual('<<<', str(DexLine('<<<')))
        t = DexLine('<<<')
        t.title_id = 'BANANAS'
        self.assertEqual('BANANAS', DexLine(t).title_id)
        self.assertEqual(
            '<<<', str(DexLine('<<<', '', '', '', '')))
        self.assertEqual('<<<H:-1', str(DexLine('<<<H').negate()))
        self.assertEqual((('a',), ('b',)), DexLine('a<b<<').key())
        self.assertEqual("DexLine('<<<')", repr(DexLine()))
        m = DexLine('AUTHOR|AUTHOR<TITLE|TITLE<SERIES #99<D7')
        self.assertEqual(
            (('AUTHOR', 'TITLE', 'AUTHOR|AUTHOR', 'TITLE', 'TITLE|TITLE'), m),
            m.sortkey())
        self.assertEqual(
            ('7', 'AUTHOR', 'SERIES 000099', ' 000099', 'TITLE'),
            m.shelfkey('@D7'))
        m = DexLine('AUTHOR<TITLE<<P')
        self.assertEqual(('AUTHOR', 'TITLE'), m.shelfkey('P'))
        self.assertTrue(DexLine('A<B<<') < DexLine('C<D<<'))
        self.assertTrue(DexLine('C<D<<') > DexLine('A<B<<'))
        self.assertTrue(DexLine('A<B<<') == DexLine('A<B<<'))

    def testPlacefilter(self):
        pass  # XXX


if __name__ == '__main__':
    unittest.main()
