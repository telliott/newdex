'''
Unit tests for the mitsfs (python) lib.
'''

from io import StringIO
import datetime
import email
import os
import sys
import unittest
from unittest.mock import patch

testdir = os.path.dirname(__file__)
srcdir = '../'
sys.path.insert(0, os.path.abspath(os.path.join(testdir, srcdir)))

from mitsfs.core import settings

from test_setup import Case
from mitsfs.library import Library

from mitsfs.dex.shelfcodes import Shelfcodes

from mitsfs.circulation.transactions import CashTransaction
from mitsfs.circulation.timewarps import Timewarp
from mitsfs.circulation.members import Member

from mitsfs.dexdb import DexDB
from mitsfs.dexfile import DexLine
from mitsfs.error import handle_exception


def create_test_member(d):
    # create a user to do the checking out
    newmember = Member(d)
    newmember.email = 'thor@asgard.com'
    newmember.first_name = 'Thor'
    newmember.last_name = 'Odinson'
    newmember.create(commit=True)
    return newmember.id


class MitsfsTest(Case):
    def testConnect(self):
        try:
            d = DexDB(dsn=self.dsn)
        finally:
            d.db.close()

    def testCreateCheckoutCheckin(self):
        try:
            d = DexDB(dsn=self.dsn)

            d.cursor.execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Paperbacks', 'C')")
            d.commit()

            # set our globals
            lib = Library(db=d)
            d.shelfcodes = lib.shelfcodes

            new_id = create_test_member(d)

            member = Member(d, new_id)
            member.membership_add(lib.membership_types['T'])
            self.assertEqual(member.can_checkout()[0], False)
            tx = CashTransaction(d, new_id, member.normal_str,
                                 amount=-member.balance, transaction_type='P',
                                 description='pay membership')
            tx.create()
            self.assertEqual(member.can_checkout()[0], True)

            # create a book for us to check out
            d.add(DexLine('AUTHOR<TITLE<SERIES<S'))

            titles = list(d.search('AUTHOR', 'TITLE'))
            self.assertEqual(len(titles), 1)

            title = titles[0]

            self.assertEqual(len(title.books), 1)

            book = title.books[0]

            self.assertEqual(book.out, False)
            book.checkout(member)
            self.assertEqual(book.out, True)
            member.checkout_history.reload()

            checkouts = member.checkout_history.out
            self.assertEqual(len(checkouts), 1)

            # we only have one book out, so
            self.assertEqual(member.can_checkout()[0], True)

            checkout = checkouts.out[0]

            checkout.checkin()
            self.assertEqual(book.out, False)

            # instantly overdue
            book.checkout(
                member,
                datetime.datetime.today() - datetime.timedelta(weeks=4))
            member.checkout_history.reload()

            # because the book was due a week ago
            self.assertEqual(member.can_checkout()[0], False)

            # declare a timewarp encompassing the due date and now
            lib.timewarps.add(
                start=datetime.datetime.today() - datetime.timedelta(weeks=2),
                end=datetime.datetime.today() + datetime.timedelta(weeks=1))

            # because the book was due a week ago, *still*
            self.assertEqual(member.can_checkout()[0], False)
            # but we wouldn't charge them
            losing_book = member.checkout_history.out[0]
            self.assertEqual(member.checkout_history.out[0].overdue_days(), 0)
            member.checkout_history.out[0].lose()

            # now owes a fine
            self.assertEqual(member.can_checkout()[0], False)

            tx = CashTransaction(d, new_id, member.normal_str,
                                 amount=-member.balance, transaction_type='P',
                                 description='simulate fine payment')
            tx.create()

            # should be able to check out books again
            self.assertEqual(member.can_checkout()[0], True)

            # check the book in which should make it unlost
            losing_book.checkin()

            self.assertEqual(member.can_checkout()[0], True)
        finally:
            d.db.close()

    def testCheckOutLoseNoTimewarp(self):
        # Consider refactoring a bunch of this into a fixture of some sort
        d = DexDB(dsn=self.dsn)

        try:

            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Paperbacks', 'C')")
            d.commit()

            # set our globals
            lib = Library(db=d)
            d.shelfcodes = lib.shelfcodes

            new_id = create_test_member(d)

            member = Member(d, new_id)

            member.membership_add(lib.membership_types['T'])
            self.assertEqual(member.can_checkout()[0], False)
            tx = CashTransaction(d, new_id, member.normal_str,
                                 amount=-member.balance, transaction_type='P',
                                 description='pay membership')
            tx.create()

            self.assertEqual(member.can_checkout()[0], True)

            # create a book for us to check out
            d.add(DexLine('AUTHOR<TITLE<SERIES<S'))

            titles = list(d.search('AUTHOR', 'TITLE'))
            self.assertEqual(len(titles), 1)

            title = titles[0]

            self.assertEqual(len(title.books), 1)

            book = title.books[0]

            self.assertEqual(book.out, False)
            book.checkout(member)
            self.assertEqual(book.out, True)
            member.checkout_history.reload()

            checkouts = member.checkout_history.out
            self.assertEqual(len(checkouts), 1)

            # we only have one book out, so
            self.assertEqual(member.can_checkout()[0], True)

            checkout = checkouts.out[0]

            checkout.checkin()
            self.assertEqual(book.out, False)

            # instantly overdue
            book.checkout(
                member,
                datetime.datetime.today() - datetime.timedelta(weeks=4))
            member.checkout_history.reload()

            # because the book was due a week ago
            self.assertEqual(member.can_checkout()[0], False)

            # make sure there is no timewarp
            d.cursor.execute('delete from timewarp')
            d.commit()

            self.assertNotEqual(member.checkout_history.out[0].overdue_days(), 
                                0)
            losing_book = member.checkout_history.out[0]
            losing_book.lose()

            # owes a fine
            self.assertEqual(member.can_checkout()[0], False)

            tx = CashTransaction(d, new_id, member.normal_str,
                                 amount=-member.balance, transaction_type='P',
                                 description='simulate fine payment')
            tx.create()

            # should be able to check out books again
            self.assertEqual(member.can_checkout()[0], True)

            # check the book in which should make it unlost
            losing_book.checkin()

            self.assertEqual(member.can_checkout()[0], True)

        finally:
            d.db.close()

    def testCreateFineChanges(self):
        try:
            d = DexDB(dsn=self.dsn)

            # fake up a shelfcode; has to be a real one until we can get our
            # configuration from the db
            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Paperbacks', 'C')")
            d.commit()

            # set our globals
            lib = Library(db=d)
            d.shelfcodes = lib.shelfcodes

            new_id = create_test_member(d)

            member = Member(d, new_id)
            member.membership_add(lib.membership_types['T'])
            tx = CashTransaction(d, new_id, member.normal_str,
                                 amount=-member.balance, transaction_type='P',
                                 description='simulate membership payment')
            tx.create()

            self.assertEqual(member.can_checkout()[0], True)

            # create a book for us to check out
            d.add(DexLine('AUTHOR<TITLE<SERIES<S'))

            titles = list(d.search('AUTHOR', 'TITLE'))
            self.assertEqual(len(titles), 1)

            title = titles[0]

            self.assertEqual(len(title.books), 1)

            book = title.books[0]

            book.checkout(member, datetime.datetime(2014, 1, 1))
            member.checkout_history.reload()
            member.checkout_history.out[0].checkin(
                datetime.datetime(2014, 9, 6, 12))

            self.assertEqual(member.balance, -4)
            tx = CashTransaction(d, new_id, member.normal_str,
                                 amount=-member.balance, transaction_type='P',
                                 description='simulate fine payment')
            tx.create()
        finally:
            d.db.close()

    def testCreateCost(self):
        try:
            d = DexDB(dsn=self.dsn)
 
            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Paperbacks', 'C')")
            d.commit()

            # set our globals
            lib = Library(db=d)
            d.shelfcodes = lib.shelfcodes

            new_id = create_test_member(d)

            member = Member(d, new_id)
            member.membership_add(lib.membership_types['T'])

            observed_cost = -member.balance

            self.assertEqual(observed_cost, member.membership.cost)

        finally:
            d.db.close()

    def testCreateUnexpiredDiscount(self):
        try:
            d = DexDB(dsn=self.dsn)

            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Paperbacks', 'C')")
            d.commit()

            # set our globals
            lib = Library(db=d)
            d.shelfcodes = lib.shelfcodes

            new_id = create_test_member(d)

            member = Member(d, new_id)

            lcost = lib.membership_types['L'].cost
            tcost = lib.membership_types['T'].cost
            ycost = lib.membership_types['1'].cost

            member.membership_add(lib.membership_types['T'])
            observed_cost = -member.balance

            self.assertEqual(observed_cost, member.membership.cost)
            self.assertEqual(observed_cost, tcost)

            tx = CashTransaction(d, new_id, member.normal_str,
                                 amount=-member.balance, transaction_type='P',
                                 description='pay membership')
            tx.create()

            member.membership_add(lib.membership_types['1'])
            observed_cost = -member.balance

            self.assertEqual(observed_cost, member.membership.cost)
            self.assertEqual(observed_cost, ycost)

            tx = CashTransaction(d, new_id, member.normal_str,
                                 amount=-member.balance, transaction_type='P',
                                 description='pay membership')
            tx.create()

            member.membership_add(lib.membership_types['L'])
            observed_cost = -member.balance

            self.assertEqual(observed_cost, member.membership.cost)
            self.assertEqual(observed_cost, lcost - ycost)

        finally:
            d.db.close()


if __name__ == '__main__':
    unittest.main()
