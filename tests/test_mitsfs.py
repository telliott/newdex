'''
Unit tests for the mitsfs (python) library.
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

from test_setup import Case
from mitsfs.dexdb import DexDB
from mitsfs.membership import Member
from mitsfs.dexfile import DexLine
from mitsfs.error import handle_exception
from mitsfs.dex.shelfcodes import Shelfcodes
from mitsfs.dex.transactions import CashTransaction
from mitsfs.dex.timewarps import Timewarp

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

            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('P', 'Paperbacks', 'C')")
            d.commit()
            d.shelfcodes = Shelfcodes(d)
            membook = d.membook()

            new_id = create_test_member(d)

            member = Member(d, new_id)
            member.membership_add(membook.membership_types['T'])
            self.assertEqual(member.can_checkout()[0], False)
            tx = CashTransaction(d, new_id, member.normal_str,
                                 amount=-member.balance, transaction_type='P',
                                 description='pay membership')
            tx.create()
            self.assertEqual(member.can_checkout()[0], True)

            # create a book for us to check out
            d.add(DexLine('AUTHOR<TITLE<SERIES<P'))

            titles = list(d.search('AUTHOR', 'TITLE'))
            self.assertEqual(len(titles), 1)

            title = titles[0]

            self.assertEqual(len(title.books), 1)

            book = title.books[0]

            self.assertEqual(book.out, False)
            book.checkout(member)
            self.assertEqual(book.out, True)
            member.checkouts.reload()

            checkouts = member.checkouts.out
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
            member.checkouts.reload()
            
            # because the book was due a week ago
            self.assertEqual(member.can_checkout()[0], False)

            # declare a timewarp encompassing the due date and now
            t = Timewarp(
                d, None,
                start=datetime.datetime.today() - datetime.timedelta(weeks=2),
                end=datetime.datetime.today() + datetime.timedelta(weeks=1),
                )
            t.create()

            # because the book was due a week ago, *still*
            self.assertEqual(member.can_checkout()[0], False)
            # but we wouldn't charge them
            losing_book = member.checkouts.out[0]
            self.assertEqual(member.checkouts.out[0].overdue_days(), 0)
            member.checkouts.out[0].lose()
 
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
        membook = d.membook()
        try:

            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Paperbacks', 'C')")
            d.commit()
            d.shelfcodes = Shelfcodes(d)

            new_id = create_test_member(d)

            member = Member(d, new_id)

            member.membership_add(membook.membership_types['T'])
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
            member.checkouts.reload()

            checkouts = member.checkouts.out
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
            member.checkouts.reload()

            # because the book was due a week ago
            self.assertEqual(member.can_checkout()[0], False)

            # make sure there is no timewarp
            d.cursor.execute('delete from timewarp')
            d.commit()

            self.assertNotEqual(member.checkouts.out[0].overdue_days(), 0)
            losing_book = member.checkouts.out[0]
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
            membook = d.membook()

            # make sure there is no timewarp
            d.cursor.execute('delete from timewarp')
            d.commit()

            # fake up a shelfcode; has to be a real one until we can get our
            # configuration from the db
            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Paperbacks', 'C')")
            d.commit()
            d.shelfcodes = Shelfcodes(d)

            new_id = create_test_member(d)

            member = Member(d, new_id)
            member.membership_add(membook.membership_types['T'])
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
            member.checkouts.reload()
            member.checkouts.out[0].checkin(datetime.datetime(2014, 9, 6, 12))

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
            membook = d.membook()

            # make sure there is no timewarp
            d.cursor.execute('delete from timewarp')
            d.commit()

            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Paperbacks', 'C')")
            d.commit()
            d.shelfcodes = Shelfcodes(d)

            new_id = create_test_member(d)

            member = Member(d, new_id)
            member.membership_add(membook.membership_types['T'])

            observed_cost = -member.balance

            self.assertEqual(observed_cost, member.membership.cost)

        finally:
            d.db.close()

    def testCreateUnexpiredDiscount(self):
        try:
            d = DexDB(dsn=self.dsn)
            membook = d.membook()

            # make sure there is no timewarp
            d.cursor.execute('delete from timewarp')
            d.commit()

            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('S', 'Paperbacks', 'C')")
            d.commit()
            d.shelfcodes = Shelfcodes(d)

            new_id = create_test_member(d)

            member = Member(d, new_id)

            lcost = membook.membership_types['L'].cost
            tcost = membook.membership_types['T'].cost
            ycost = membook.membership_types['1'].cost

            member.membership_add(membook.membership_types['T'])
            observed_cost = -member.balance

            self.assertEqual(observed_cost, member.membership.cost)
            self.assertEqual(observed_cost, tcost)

            tx = CashTransaction(d, new_id, member.normal_str,
                                 amount=-member.balance, transaction_type='P',
                                 description='pay membership')
            tx.create()

            member.membership_add(membook.membership_types['1'])
            observed_cost = -member.balance

            self.assertEqual(observed_cost, member.membership.cost)
            self.assertEqual(observed_cost, ycost)

            tx = CashTransaction(d, new_id, member.normal_str,
                                 amount=-member.balance, transaction_type='P',
                                 description='pay membership')
            tx.create()

            member.membership_add(membook.membership_types['L'])
            observed_cost = -member.balance

            self.assertEqual(observed_cost, member.membership.cost)
            self.assertEqual(observed_cost, lcost - ycost)

        finally:
            d.db.close()


# class MitsfsNoDBTest(unittest.TestCase):
#     def testHandleException(self):
#         with patch("mitsfs.error.subprocess.Popen", wraps=MockPopen) as mockP:
#             try:
#                 try:
#                     {}['foo']
#                 except Exception:
#                     os.environ['MITSFS_EMAIL_DEBUG'] = 'destination@example.com'
#                     handle_exception('test', sys.exc_info())
#                 m = email.parser.Parser().parsestr(mockP.input.getvalue())
#                 self.assertEqual('destination@example.com', m['to'])
#                 self.assertRegex(
#                     m['Subject'],
#                     r"\[.+ error\] [a-zA-Z0-9]+ - KeyError:'foo'")
#                 self.assertRegex(
#                     '\n' + m.get_payload(0).get_payload(),
#                     r'''
# program: .+
# user: [^\n:]+
# context: test
# traceback:
# Traceback \(most recent call last\):

#  +File ".*/test_mitsfs.py", line \d+, in testHandleException
#  +{}\['foo'\]
#  +~~\^\^\^\^\^\^\^

# KeyError: 'foo'
# ''')
#             finally:
#                 pass

# class MockPopen:
#     input = StringIO()
#     input.close = lambda *args, **kwargs: None

#     def __init__(self, *args, **kwargs):
#         self.args = args
#         self.kwargs = args
#         self.stdin = MockPopen.input

#     def wait(self):
#         return 0

if __name__ == '__main__':
    unittest.main()
