import unittest
import os
import sys

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from tests.test_setup import Case

from mitsfs.circulation.members import Member, Members
from mitsfs.library import Library

class DexDBTest(Case):
    def test_members(self):
        try:
            library = Library(dsn=self.dsn)
            db = library.db
            db.getcursor().execute(
                'insert into'
                ' member(first_name, last_name, key_initials, email,'
                ' address, phone, pseudo)'
                " values('New', 'Member', '', 'new@new.com',"
                " '1235 A St, Washington, DC 12345', '', 'f'),"
                " ('Old', 'Member', 'OMB', 'old@new.com',"
                " '1235 A St, Washington, DC 12345', '', 'f'),"
                " ('Thor', 'Odinson', 'TO', 'thor@asgard.com',"
                " 'Asgard', '', 'f')")
            db.commit()

            results = library.members.find('NotaMember')
            self.assertEqual(0, len(results))

            results = library.members.find('Memb')
            self.assertEqual(2, len(results))
            self.assertEqual('Member', results[0].last_name)
            first_names = [r.first_name for r in results]
            self.assertIn('New', first_names)
            self.assertIn('Old', first_names)

            results = library.members.find('new.com')
            self.assertEqual(2, len(results))
            self.assertEqual('Member', results[0].last_name)
            first_names = [r.first_name for r in results]
            self.assertIn('New', first_names)
            self.assertIn('Old', first_names)

            results = library.members.find('Thor')
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
            self.assertEqual('TO', new_thor.key_initials)
            self.assertFalse(new_thor.pseudo)

            # create loki from scracth
            loki = Member(db)
            loki.first_name = 'Loki'
            loki.last_name = 'Odinson'
            loki.address = 'Jotunheim'

            # no email, so shouldn't be able to create
            self.assertRaises(Exception, loki.create)

            loki.email = 'loki@asgard.com'
            loki.create()

            loki_id = loki.member_id
            loki = Member(db, loki_id)
            self.assertEqual('Jotunheim', loki.address)
            self.assertEqual('Loki', loki.first_name)
            self.assertEqual('Odinson', loki.last_name)
            self.assertEqual('loki@asgard.com', loki.email)
            self.assertEqual(None, loki.key_initials)

            loki.address = 'Asgard'
            loki.email = 'loki@frostgiants.com'
            loki.phone = '650-555-1212'

            loki = Member(db, loki_id)
            self.assertEqual('Asgard', loki.address)
            self.assertEqual('loki@frostgiants.com', loki.email)
            self.assertEqual('650-555-1212', loki.phone)

            results = library.members.find('Odins')
            self.assertEqual(2, len(results))

            # set through keyword arguments
            hela = Member(db, None, first_name='Hela', email='hela@asgard.com',
                          address='Nifelheim')
            hela.create()
            hela_id = hela.member_id

            hela = Member(db, hela_id)
            self.assertEqual('Nifelheim', hela.address)
            self.assertEqual('hela@asgard.com', hela.email)
            self.assertEqual('Hela', hela.first_name)

        finally:
            db.db.close()


if __name__ == '__main__':
    unittest.main()
