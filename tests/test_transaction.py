import unittest
import os
import sys

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from mitsfs.dexdb import DexDB
from mitsfs.dexfile import DexLine
from mitsfs.membership import Member
from tests.test_setup import Case
from mitsfs.dex.transactions import get_transactions, Transaction, \
    CashTransaction, FineTransaction, OverdueTransaction, get_CASH_id
from mitsfs.dex.shelfcodes import Shelfcodes

def create_test_member(d):
    # create a user to do the checking out
    newmember = Member(d)
    newmember.email = 'thor@asgard.com'
    newmember.first_name = 'Thor'
    newmember.last_name = 'Odinson'
    newmember.create(commit=True)
    return newmember


class DexDBTest(Case):
    def test_members(self):
        try:
            db = DexDB(dsn=self.dsn)

            thor = create_test_member(db)

            # create shelfcodes for our book
            db.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('P', 'Paperbacks', 'C')")
            db.commit()
            db.shelfcodes = Shelfcodes(db)

            # create our book for checking out
            db.add(DexLine('AUTHOR<TITLE<SERIES<P'))
            titles = list(db.search('AUTHOR', 'TITLE'))
            title = titles[0]
            book = title.books[0]


            #add a couple basic transactions
            tx1 = Transaction(db, thor.id, amount=10, transaction_type='M',
                              description='Transaction one')
            tx1.create()

            transactions = get_transactions(db, thor.id)
            self.assertEqual(1, len(transactions))

            self.assertEqual(10, transactions[0].amount)
            self.assertEqual(thor.id, transactions[0].member_id)
            self.assertEqual('M', transactions[0].transaction_type)
            self.assertEqual('Transaction one', transactions[0].description)
            self.assertFalse(transactions[0].linked_transaction)

            rx = r'.*\$10\.00[^,]+, [0-9-]+, M, Transaction one'
            self.assertRegex(str(tx1), rx)

            # add a second transaction
            tx2 = Transaction(db, thor.id, amount=-10, transaction_type='P',
                              description='Transaction two')
            tx2.create()

            self.assertEqual(2, len(get_transactions(db, thor.id)))

            # void a simple transaction
            voided_transactions = tx1.void()
            self.assertEqual(1, len(voided_transactions))
            self.assertEqual(1, len(tx1.linked_transaction))
            self.assertEqual(tx1.id, voided_transactions[0].id)
            self.assertTrue(tx1.is_void())

            self.assertEqual(3, len(get_transactions(db, thor.id)))

            transactions = get_transactions(db, thor.id, include_voided=False)
            self.assertEqual(1, len(transactions))

            tx3 = CashTransaction(db, thor.id, thor.normal_str, amount=100,
                                  transaction_type='M',
                                  description='Transaction 3 (cash)')
            tx3.create()
            cash_id = get_CASH_id(db)

            cash_transactions = get_transactions(db, cash_id)
            self.assertEqual(1, len(cash_transactions))
            transactions = get_transactions(db, thor.id, include_voided=False)
            self.assertEqual(2, len(transactions))

            self.assertEqual(1, len(tx3.linked_transaction))

            tx3.void()
            self.assertEqual(2, len(tx3.linked_transaction))
            self.assertTrue(tx3.is_void())
            self.assertTrue(cash_transactions[0].is_void())

            self.assertEqual(5, len(get_transactions(db, thor.id)))
            self.assertEqual(2, len(get_transactions(db, cash_id)))

            transactions = get_transactions(db, thor.id, include_voided=False)
            self.assertEqual(1, len(transactions))

            checkout = book.checkout(thor)
            tx4 = FineTransaction(db, thor.id, checkout.id, amount=.30,
                                  description='Transaction 4 (fine)')
            tx4.create()
   
            self.assertEqual(6, len(get_transactions(db, thor.id)))

            self.assertEqual('F', tx4.transaction_type)
            r = db.cursor.execute('select checkout_id, transaction_id'
                                  ' from fine_payment')
            result = r.fetchall()
            self.assertEqual(1, len(result))

            self.assertEqual(result[0][0], checkout.id[0])
            self.assertEqual(result[0][1], tx4.id)

            # now a short and a max overdue transaction
            tx5 = OverdueTransaction(db, thor.id, checkout.id, 5, book)
            tx5.create()
            self.assertEqual(-.50, tx5.amount)
            self.assertEqual('Book AUTHOR<TITLE<SERIES<P (Paperbacks)< '
                             'overdue 5 days.', tx5.description)
            self.assertEqual(7, len(get_transactions(db, thor.id)))

            tx6 = OverdueTransaction(db, thor.id, checkout.id, 500, book)
            tx6.create()
            self.assertEqual(-4.00, tx6.amount)
            self.assertEqual('Book AUTHOR<TITLE<SERIES<P (Paperbacks)< '
                             'overdue 500 days.', tx6.description)
            self.assertEqual(8, len(get_transactions(db, thor.id)))

            r = db.cursor.execute('select checkout_id, transaction_id'
                                  ' from fine_payment')
            result = r.fetchall()
            self.assertEqual(3, len(result))



        finally:
            db.db.close()


if __name__ == '__main__':
    unittest.main()
