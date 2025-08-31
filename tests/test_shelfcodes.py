# -*- coding: utf-8 -*-

from mitsfs.dex.shelfcodes import Shelfcodes, Shelfcode
import unittest
import os
import sys

from unittest.mock import patch

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))


test_shelfcodes = [
    (1195341, 'L', 'Large Fiction', 'C', 40, 'F', 'f'),
    (1195344, 'S', 'Small Fiction', 'C', 15, 'F', 'f'),
    (74, 'SFWA-TD', 'SFWA Tor Double', 'D', 40, 'D', 't')]

shelfcode_str = \
    '''L => Large Fiction (1195341)
S => Small Fiction (1195344)
SFWA-TD => SFWA Tor Double (74)'''


def fake_load(self, db):
    return test_shelfcodes


@patch.object(Shelfcodes, 'load_from_db', fake_load)
class TestShelfcodes(unittest.TestCase):
    d = object

    def test_get(self):
        s = Shelfcodes(self.d)
        self.assertEqual(s['L'].shelfcode_id, 1195341)
        self.assertEqual(s['S'].shelfcode_id, 1195344)
        self.assertEqual(s['SFWA-TD'].shelfcode_id, 74)

    def test_set(self):
        s = Shelfcodes(self.d)
        n = Shelfcode(75, 'TEST', 'SFWA Tor Double', 'D', 40, 'D', 't')
        s['TEST'] = n
        self.assertEqual(s['TEST'].shelfcode_id, 75)

    def test_keys(self):
        s = Shelfcodes(self.d)
        self.assertEqual(list(s.keys()), ['L', 'S', 'SFWA-TD'])

    def test_print(self):
        s = Shelfcodes(self.d)
        self.assertEqual(str(s), shelfcode_str)


if __name__ == "__main__":
    unittest.main()
