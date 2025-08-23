import unittest
import os
import sys

testdir = os.path.dirname(__file__)
srcdir = '../'

sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))


from test_setup import Case
from mitsfs.dexfile import DexLine, Dex
from mitsfs.dexdb import DexDB
from mitsfs.dex.shelfcodes import Shelfcodes


class DexDBTest(Case):
    def test_search(self):
        try:
            d = DexDB(dsn=self.dsn)

            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('P', 'Paperbacks', 'C')")
            d.commit()
            d.shelfcodes = Shelfcodes(d)

            d.add(DexLine('AUTHOR<TITLE<SERIES<P'))
            d.add(DexLine('FOO<BAR<<P'))

            self.assertEqual(
                ['AUTHOR<TITLE<SERIES<P'],
                [str(x) for x in d.grep('thor')])

            d.add(DexLine('BOOK<THOR: THE THORENING<<P'))

            self.assertEqual(
                ['BOOK<THOR: THE THORENING<<P'],
                [str(x) for x in d.grep('<thor')])

            self.assertEqual(
                ['BOOK<THOR: THE THORENING<<P'],
                [str(x) for x in d.titlesearch('thor')])
        finally:
            d.db.close()

    def test_things(self):
        try:
            d = DexDB(dsn=self.dsn)

            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('P', 'Paperbacks', 'C')")
            d.commit()
            d.shelfcodes = Shelfcodes(d)

            dex = Dex([
                'A<B<<P',
                'D<E<<P',
                ])

            d.merge(dex)

            self.assertEqual('A<B<<P', str(d.get('A<B<<')))
            self.assertEqual('A<B<<P', str(d['A<B<<']))
            self.assertEqual('A<B<<P', str(d[d['A<B<<']]))
            self.assertEqual(None, d.get('FOO<BAR<<'))
            self.assertRaises(KeyError, lambda: d['FOO<BAR<<'])

            d.add(DexLine('F<G<H<P'))
            d.add(DexLine('F<G<H<P'))
            self.assertEqual(2, int(d['F<G<H<'].codes))
            d.add(DexLine('F<G<H<P:-1'))
            self.assertEqual(1, int(d['F<G<H<'].codes))
        finally:
            d.db.close()

if __name__ == '__main__':
    unittest.main()
