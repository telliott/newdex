import unittest
import os
import sys
import psycopg2

testdir = os.path.dirname(__file__)
srcdir = '../../..'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from mitsfs.dexdb import DexDB
from tests.test_setup import Case
from mitsfs.membership import Member, find_members



class DexDBTest(Case):
    def test_search(self):
        try:
            db = DexDB(dsn=self.dsn)

            db.getcursor().execute(
                'insert into'
                ' member(first_name, last_name, key_initials, email,'
                ' address, pseudo)'
                " values('New', 'Member', 'newb', 'new@new.com',"
                " '1235 A St, Washington, DC 12345', '', 'f'),"
                " ('Old', 'Member', 'oldie', 'old@new.com',"
                " '1235 A St, Washington, DC 12345', '', 'f'),"
                " ('Thor', 'Odinson', 'TO', 'thor@asgard.com',"
                " 'Asgard', '', 'f')")
            db.commit()

            results = find_members(db, 'NotaMember')
            self.assertEqual(0, len(results))

            results = find_members(db, 'Memb')
            self.assertEqual(2, len(results))
            self.assertEqual('Member', results[0].last_name)
            first_names = [r.first_name for r in results]
            self.assertIn('New', first_names)
            self.assertIn('Old', first_names)

            results = find_members(db, 'new.com')
            self.assertEqual(2, len(results))
            self.assertEqual('Member', results[0].last_name)
            first_names = [r.first_name for r in results]
            self.assertIn('New', first_names)
            self.assertIn('Old', first_names)

            results = find_members(db, 'Thor')
            self.assertEqual(1, len(results))
            self.assertEqual('Odinson', results[0].last_name)

            # update Thor
            thor = results[0]
            thor_id = thor.member_id
            thor.address = 'Midgard'
            thor.commit()

            new_thor = Member(db, thor_id)
            self.assertEqual('Midgard', new_thor.address)
            self.assertEqual('Thor', new_thor.first_name)
            self.assertEqual('Odinson', new_thor.last_name)
            self.assertEqual('thor@asgard.com', new_thor.email)
            self.assertEqual('TO', new_thor.nickname)
            self.assertFalse(new_thor.pseudo)

            loki = Member(db)
            loki.first_name = 'Loki'
            loki.last_name = 'Odinson'
            loki.address = 'Jotunheim'
            self.assertRaises(Exception, loki.create)
            
            loki.email = 'loki@asgard.com'
            loki.create()
            
            loki_id = loki.member_id
            loki = Member(db, loki_id)
            self.assertEqual('Jotunheim', loki.address)
            self.assertEqual('Loki', loki.first_name)
            self.assertEqual('Odinson', loki.last_name)
            self.assertEqual('loki@asgard.com', loki.email)
            self.assertEqual(None, loki.nickname)

            loki.address = 'Asgard'
            loki.email = 'loki@frostgiants.com'
            loki.phone = '650-555-1212'
            
            loki = Member(db, loki_id)
            self.assertEqual('Asgard', loki.address)
            self.assertEqual('loki@frostgiants.com', loki.email)
            self.assertEqual('650-555-1212', loki.phone)
                        
            
            results = find_members(db, 'Odins')
            self.assertEqual(2, len(results))

        finally:
            db.db.close()


if __name__ == '__main__':
    unittest.main()
