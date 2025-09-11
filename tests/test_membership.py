import unittest
import os
import sys
import datetime

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from mitsfs.dexdb import DexDB

from mitsfs.circulation.membership import Membership

from tests.test_setup import Case


class DexDBTest(Case):
    def test_membership(self):
        try:
            future_date = datetime.datetime.now() + datetime.timedelta(days=30)
            expired = datetime.datetime.now() - datetime.timedelta(days=30)
            short_date = future_date.strftime('%Y-%m-%d')
            description = f'New Membership - Y - Expires: {short_date}'

            db = DexDB(dsn=self.dsn)
            member_id = db.getcursor().selectvalue(
                'insert into'
                ' member(first_name, last_name, key_initials, email,'
                ' address, phone, pseudo)'
                " values('New', 'Member', '', 'new@new.com',"
                " '1235 A St, Washington, DC 12345', '', 'f')"
                " returning member_id")
            db.commit()

            # Membership type is inserted as part of the schema

            transaction_id = db.getcursor().selectvalue(
                'insert into'
                ' transaction(transaction_amount, member_id,'
                ' transaction_type, transaction_description)'
                f" values(10, {member_id}, 'M', '{description}')"
                " returning transaction_id")
            db.commit()

            # since it's all ReadFields, can't set it from a membership object
            # Test an expired membership
            membership_id = db.getcursor().selectvalue(
                'insert into'
                ' membership(member_id, membership_expires,'
                ' membership_type, membership_payment)'
                f" values({member_id}, '{expired}', '1',"
                f" {transaction_id})"
                " returning membership_id")
            db.commit()

            new = Membership(db, membership_id)
            self.assertEqual('1 year Nonstudent', new.description)
            self.assertTrue(new.expired)
            self.assertEqual(-10, new.cost)
            self.assertIn("Expired: " + str(expired.date()), str(new))

            # Test an unexpired membership
            membership_id = db.getcursor().selectvalue(
                'insert into'
                ' membership(member_id, membership_expires,'
                ' membership_type, membership_payment)'
                f" values({member_id}, '{future_date}', '1',"
                f" {transaction_id})"
                " returning membership_id")
            db.commit()

            new = Membership(db, membership_id)
            self.assertEqual('1 year Nonstudent', new.description)
            self.assertFalse(new.expired)
            self.assertEqual(-10, new.cost)
            self.assertIn("Expires: " + str(future_date.date()), str(new))

            # Test a life membership
            transaction_id = db.getcursor().selectvalue(
                 'insert into'
                 ' transaction(transaction_amount, member_id,'
                 ' transaction_type, transaction_description)'
                 f" values(100, {member_id}, 'M', 'Life Membership')"
                 " returning transaction_id")
            db.commit()

            # since it's all ReadFields, can't set it from a membership object
            membership_id = db.getcursor().selectvalue(
                 'insert into'
                 ' membership(member_id, '
                 ' membership_type, membership_payment)'
                 f" values({member_id}, 'L',"
                 f" {transaction_id})"
                 " returning membership_id")
            db.commit()

            new = Membership(db, membership_id)
            self.assertEqual('Life', new.description)
            self.assertFalse(new.expired)
            self.assertEqual(-100, new.cost)
            self.assertIn("Expires: Never", str(new))

            # TODO: test a voided transaction

        finally:
            db.db.close()


if __name__ == '__main__':
    unittest.main()
