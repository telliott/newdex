#!/usr/bin/python

import sys
import os
import shutil
import tempfile
import unittest

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from mitsfs.dexfile import Dex, DexLine, deseries, deat
from mitsfs.dex.shelfcodes import Shelfcodes
from mitsfs import utils


class DexfileTest(unittest.TestCase):

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
        # dexline.shelfkey is almost certainly broken owing to how it handles
        # the shelfcode argument
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

    def testMisc(self):
        self.assertEqual('FOO', deseries('@FOO #2B'))
        self.assertEqual('FOO', deat('@FOO'))
        self.assertEqual('FOO', deat('FOO'))

    def testDex(self):
        Shelfcodes.generate_shelfcode_regex(['P', 'H', 'C/P'], [], force=True)
        d = Dex()
        self.assertFalse(isinstance(d, bool))
        d.add('AUTHOR, AN<BOOK, A<<P')
        d.add('AUTHOR, OTHER<BOOK, ANOTHER<<P')
        self.assertEqual(2, len(d))
        self.assertEqual({'P': 2}, d.stats())
        d.add('AUTHOR, THIRD<BOOK, YET ANOTHER<<P:-1')
        self.assertEqual(2, len(d))
        self.assertEqual({'P': 2}, d.stats())
        d.add('AUTHOR, AN<BOOK, A<<P:-2')
        self.assertEqual(1, len(d))
        self.assertEqual({'P': 1}, d.stats())
        d.add('AUTHOR, AN<BOOK, A<<P,H:-2')
        self.assertEqual(2, len(d))
        self.assertEqual(
            {'P': 2, }, dict((k, v) for (k, v) in d.stats().items() if v))
        d.add('AUTHOR, AN<BOOK, A<<C/P')
        self.assertEqual(2, len(d))
        self.assertEqual(
            {'P': 2, 'C/P': 1},
            dict((k, v) for (k, v) in d.stats().items() if v))
        d.add('AUTHOR, AN<BOOK, A<<P:-1,C/P:-2')
        self.assertEqual(1, len(d))
        self.assertEqual(
            {'P': 1, }, dict((k, v) for (k, v) in d.stats().items() if v))

    # def testDeprecated(self):
    #     self.assertEqual(('PA', 1, 'PANTS'), onecode('PANTS{PA}'))
    #     self.assertEqual(
    #         {'C/P': 2, 'P': 1}, dict(Editions('PANTS: C/P:2,P')))
    #     y = Editions('C/P:2,P')
    #     self.assertEqual('C/P:2,P:1', y.logstr())
    #     self.assertEqual('<<<', DexLine().logstr())

    def test_load(self):
        Shelfcodes.generate_shelfcode_regex(['P'], [], force=True)
        dex = Dex('/Nonexistant-file')
        self.assertEqual('/Nonexistant-file', dex.filename)
        self.assertEqual(0, len(dex))

        dex2 = Dex(dex)
        self.assertEqual('/Nonexistant-file', dex2.filename)
        self.assertEqual(0, len(dex2))

        with tempfile.NamedTemporaryFile(mode='w', delete=True) as fp:
            fp.write('A<B<<P\n')
            fp.write('A<C<<P\n')
            fp.write('D<E<<P\n')
            fp.flush()

            dex = Dex(fp.name)
            self.assertEqual(3, len(dex))

    def test_replace(self):
        Shelfcodes.generate_shelfcode_regex(['H', 'P', 'C/P', 'PA'], ['D'],
                                            force=True)
        dex = Dex([
            'A<B<<P',
            'D<E<<P',
            ])

        self.assertEqual(1, int(dex['A<B<<'].codes))
        dex.replace(DexLine('A<B<<'), 'A<B<<P:2')
        self.assertEqual(2, int(dex['A<B<<'].codes))

    def test_contains(self):
        Shelfcodes.generate_shelfcode_regex(['P'], [], force=True)
        dex = Dex([
            'A<B<<P',
            ])
        self.assertTrue('A<B<<' in dex)
        self.assertFalse('A<B<<' not in dex)
        self.assertFalse('C<D<<' in dex)
        self.assertTrue('C<D<<' not in dex)

    def test_merge(self):
        Shelfcodes.generate_shelfcode_regex(['P'], [], force=True)
        dex1 = Dex([
            'A<B<<P',
            ])
        dex2 = Dex([
            'D<E<<P',
            ])
        self.assertEqual(1, len(dex1))
        self.assertEqual(1, len(dex2))
        dex1.merge(dex2)
        self.assertEqual(2, len(dex1))
        self.assertEqual(1, len(dex2))

    def test_sub(self):
        Shelfcodes.generate_shelfcode_regex(['P'], [], force=True)
        dex1 = Dex([
            'A<B<<P',
            ])
        self.assertEqual(1, len(dex1))
        dex2 = dex1 - dex1
        self.assertEqual(1, len(dex1))
        self.assertEqual(0, len(dex2))

    def test_sorted(self):
        Shelfcodes.generate_shelfcode_regex(['P'], [], force=True)
        testlist = [
            'D<E<<P',
            'A<B<<P',
            ]
        dex = Dex(testlist)

        self.assertEqual(testlist, [str(x) for x in dex])
        self.assertEqual(sorted(testlist), [str(x) for x in dex.sorted()])
        dex.sort()
        self.assertEqual(sorted(testlist), [str(x) for x in dex])

    def test_save(self):
        Shelfcodes.generate_shelfcode_regex(['P'], [], force=True)
        testlist = [
            'A<B<<P',
            'D<E<<P',
            ]
        dex1 = Dex(testlist)
        self.assertEqual(testlist, [str(x) for x in dex1])

        tempdir = tempfile.mkdtemp()
        try:
            fname = os.path.join(tempdir, 'dex')
            dex1.save(fname)
            dex2 = Dex(fname)
            self.assertEqual(testlist, [str(x) for x in dex2])
        finally:
            shutil.rmtree(tempdir)

    def test_search(self):
        Shelfcodes.generate_shelfcode_regex(['P'], [], force=True)
        testlist = [
            'A<B<<P',
            'C<EA<<P',
            'C<EB<<P',
            'D<C<<P',
            ]
        dex = Dex(testlist)
        self.assertEqual(testlist[1:3], [str(x) for x in dex.titlesearch('E')])
        self.assertEqual(testlist[1:2], [str(x) for x in dex.grep('EA')])
        self.assertEqual(testlist[3:4], [str(x) for x in dex.grep('<C')])

    def test_string(self):
        Shelfcodes.generate_shelfcode_regex(['P'], [], force=True)
        testlist = [
            'A<B<<P',
            'D<E<<P',
            ]
        dex = Dex(testlist)
        self.assertEqual('\n'.join(testlist), str(dex))
        self.assertRegex(
            repr(dex),
            r'<mitsfs.dexfile.Dex object at 0x[a-f0-9]+ 2 entries 2 books>')


if __name__ == '__main__':
     unittest.main()
