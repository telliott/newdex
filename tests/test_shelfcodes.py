# -*- coding: utf-8 -*-

import unittest
import os
import sys

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from mitsfs.dex.shelfcodes import Shelfcodes, Shelfcode
from mitsfs.dexdb import DexDB
from tests.test_setup import Case
from mitsfs.dex.coercers import coerce_shelfcode, uncoerce_shelfcode

test_shelfcodes = [
    ]

shelfcode_re = r'L => Large Fiction \([0-9]*\)\nS => Small Fiction \([0-9]*\)'


class TestShelfcodes(Case):
    def test_shelfcodes(self):
        try:
            db = DexDB(dsn=self.dsn)
            l_id = db.getcursor().selectvalue(
                'insert into'
                ' shelfcode(shelfcode, shelfcode_description, shelfcode_type,'
                ' replacement_cost, shelfcode_class, shelfcode_doublecode)'
                " values"
                " ('L', 'Large Fiction', 'C', 40, 'F', 'f')"
                " returning shelfcode_id"
                )

            s_id = db.getcursor().selectvalue(
                'insert into'
                ' shelfcode(shelfcode, shelfcode_description, shelfcode_type,'
                ' replacement_cost, shelfcode_class, shelfcode_doublecode)'
                " values"
                " ('S', 'Small Fiction', 'C', 15, 'F', 'f')"
                " returning shelfcode_id"
                )

            db.commit()
            sfwa_id = db.getcursor().selectvalue(
                'insert into'
                ' shelfcode(shelfcode, shelfcode_description, shelfcode_type,'
                ' replacement_cost, shelfcode_class, shelfcode_doublecode)'
                " values"
                " ('SFWA-TD', 'SFWA Tor Double', 'D', 40, 'D', 't')"
                " returning shelfcode_id"
                )
            db.commit()

            s = Shelfcodes(db)
            self.assertEqual(s['L'].description, 'Large Fiction')
            self.assertEqual(s['S'].description, 'Small Fiction')
            self.assertNotIn('SFWA-TD', s)

            s = Shelfcodes(db)
            # assert I can write and get back without going to db. Note that
            # any id you pass here will be ignored
            n = Shelfcode(db, None, code='TEST', description='SFWA Tor Double',
                          code_type='D', replacement_cost=40,
                          code_class='D', is_double='t')
            s['TEST'] = n
            self.assertEqual(s['TEST'].replacement_cost, 40)
            self.assertEqual(3, len(s))

            s = Shelfcodes(db)
            self.assertEqual(2, len(s))

            self.assertEqual(list(s.keys()), ['L', 'S'])

            s = Shelfcodes(db)
            self.assertRegex(str(s), shelfcode_re)

            # The SFWA-TD is deprecated, but we can still access it directly
            sfwa = Shelfcode(db, sfwa_id)
            self.assertEqual(40, sfwa.replacement_cost)
            self.assertTrue(sfwa.is_double)

            # test coerce_shelfcode
            self.assertEqual('S', coerce_shelfcode(s_id, db).code)
            self.assertEqual('L', coerce_shelfcode(l_id, db).code)

            # test uncoerce_shelfcode
            x = s['L']
            self.assertEqual(x.id, uncoerce_shelfcode(x))

        finally:
            db.db.close()


if __name__ == "__main__":
    unittest.main()
