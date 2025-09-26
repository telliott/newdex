import unittest
import os
import sys
import datetime

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from tests.test_setup import Case
from mitsfs.dexdb import DexDB
from mitsfs.dexfile import DexLine

from mitsfs.dex.shelfcodes import Shelfcodes

from mitsfs.circulation.members import Member
from mitsfs.circulation.checkouts import Checkout, Checkouts
from mitsfs.circulation.transactions import get_transactions, Transaction


def create_test_member(d):
    # create a user to do the checking out
    newmember = Member(d)
    newmember.email = 'thor@asgard.com'
    newmember.first_name = 'Thor'
    newmember.last_name = 'Odinson'
    newmember.create(commit=True)
    return newmember


class DexDBTest(Case):
    def test_checkouts(self):
        try:
            db = DexDB(dsn=self.dsn)

            thor = create_test_member(db)
            today = datetime.datetime.today()

            # create shelfcodes for our book
            db.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('P', 'Paperbacks', 'C')")
            db.commit()
            db.shelfcodes = Shelfcodes(db)

            books = {}

            for i in range(1, 9):
                db.add(DexLine(f'AUTHOR<TITLE{i}<SERIES<P'))
                titles = list(db.search('AUTHOR', f'TITLE{i}'))
                title = titles[0]
                books[i] = title.books[0]

            c1 = Checkout(db, None, member_id=thor.id,
                          checkout_stamp=today,
                          book_id=books[1].id)
            c1.create()

            self.assertEqual(thor.id, c1.member_id)
            self.assertEqual(today, c1.checkout_stamp)
            self.assertEqual(books[1].id, c1.book_id)
            self.assertEqual(c1.get_logger(), c1.checkout_user)
            self.assertEqual('AUTHOR<TITLE1<SERIES<P', str(c1.book.title))
            self.assertFalse(c1.overdue)

            due = today + datetime.timedelta(weeks=3)
            if due.hour < 3:
                due -= datetime.timedelta(days=1)

            self.assertEqual(datetime.date(due.year, due.month, due.day),
                             c1.due_date)

            checkouts = Checkouts(db, member_id=thor.id)
            self.assertEqual(1, len(checkouts))
            self.assertEqual(1, len(checkouts.out))
            self.assertEqual(0, len(checkouts.overdue))

            self.assertEqual(thor.id, checkouts[0].member_id)

            # now add an overdue book
            checkout_timestamp = today - datetime.timedelta(weeks=5)
            c2 = Checkout(db, None, member_id=thor.id,
                          checkout_stamp=checkout_timestamp,
                          book_id=books[2].id)
            c2.create()
            self.assertTrue(c2.overdue)
            self.assertEqual(13, c2.overdue_days())

            checkouts = Checkouts(db, member_id=thor.id)
            self.assertEqual(2, len(checkouts))
            self.assertEqual(2, len(checkouts.out))
            self.assertEqual(1, len(checkouts.overdue))

            # check in book 1

            # the book_ids are all tuples. I will make that go away someday
            book_checkouts = Checkouts(db, book_id=books[1].id)
            self.assertEqual(1, len(book_checkouts.out))
            b1 = book_checkouts.out[0]
            b1.checkin(today)

            self.assertEqual(c1.get_logger(), b1.checkin_user)
            self.assertEqual(today, b1.checkin_stamp)

            # can't checkin a book that isn't checked out
            self.assertIn(' is already checked in', b1.checkin())

            checkouts.reload()
            self.assertEqual(1, len(checkouts.out))
            self.assertEqual(2, len(checkouts))

            # check in the overdue book
            c2.checkin()
            tx = get_transactions(db, c2.member_id)
            self.assertEqual(1, len(tx))

            # check out book 3, which we will lose
            c3 = Checkout(db, None, member_id=thor.id,
                          checkout_stamp=today,
                          book_id=books[3].id)
            c3.create()
            c3.lose()

            # one new transaction here, because it's not overdue
            tx = get_transactions(db, c2.member_id)
            self.assertEqual(2, len(tx))

            # retroactively check out book 3, which we will lose
            checkout_timestamp = today - datetime.timedelta(weeks=5)
            c4 = Checkout(db, None, member_id=thor.id,
                          checkout_stamp=checkout_timestamp,
                          book_id=books[2].id)
            c4.create()
            c4.lose()
            lost_tx_id = c4.lost

            # since this was overdue, should have both an overdue transaction
            # and a lost book transaction
            tx = get_transactions(db, thor.id)
            self.assertEqual(4, len(tx))

            # Whoops! We found book 4
            c4.checkin()
            tx = get_transactions(db, thor.id)
            self.assertEqual(5, len(tx))
            self.assertEqual(None, c4.lost)

            lost_tx = Transaction(db, thor.id, lost_tx_id)
            self.assertTrue(lost_tx.is_void())
            self.assertEqual(1, len(lost_tx.linked_transaction))

        finally:
            db.db.close()


if __name__ == '__main__':
    unittest.main()
