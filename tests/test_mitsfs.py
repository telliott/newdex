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
from mitsfs.membership import Member, MemberName, TimeWarp
from mitsfs.dexfile import DexLine
from mitsfs.error import handle_exception
from mitsfs.dex.shelfcodes import Shelfcodes

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

            # create a user to do the checking out
            newmember = Member(d)
            newmember.create(commit=False)
            member_name = MemberName(
                d, member_id=newmember.id, member_name='USER')
            member_name.create(commit=False)
            newmember.member_name_default = member_name.id
            newmember.commit()

            member = Member(d, newmember.id)
            member.membership_add(
                'T',
                datetime.datetime.today() + datetime.timedelta(weeks=12),
                0)
            self.assertEqual(member.checkout_good()[0], False)
            member.cash_transaction(-member.balance, 'P', 'pay membership')

            self.assertEqual(member.checkout_good()[0], True)

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

            checkouts = member.checkouts
            self.assertEqual(len(checkouts), 1)

            # we only have one book out, so
            self.assertEqual(member.checkout_good()[0], True)

            checkout = checkouts[0]

            checkout.checkin()
            self.assertEqual(book.out, False)

            # instantly overdue
            book.checkout(
                member,
                datetime.datetime.today() - datetime.timedelta(weeks=4))

            # because the book was due a week ago
            self.assertEqual(member.checkout_good()[0], False)

            # declare a timewarp encompassing the due date and now
            t = TimeWarp(
                d, None,
                start=datetime.datetime.today() - datetime.timedelta(weeks=2),
                end=datetime.datetime.today() + datetime.timedelta(weeks=1),
                )
            t.create()

            # because the book was due a week ago, *still*
            self.assertEqual(member.checkout_good()[0], False)
            # but we wouldn't charge them
            self.assertEqual(member.checkouts[0].overdue_days(), 0)
            member.checkouts[0].lose()

            # now owes a fine
            self.assertEqual(member.checkout_good()[0], False)

            member.cash_transaction(
                -member.balance, 'P', 'simulate fine payment')

            # should be able to check out books again
            self.assertEqual(member.checkout_good()[0], True)

            # check the book in which should make it unlost
            member.checkouts[0].checkin()

            self.assertEqual(member.checkout_good()[0], True)
        finally:
            d.db.close()

    def testCheckOutLoseNoTimewarp(self):
        # Consider refactoring a bunch of this into a fixture of some sort
        d = DexDB(dsn=self.dsn)
        try:
  
            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('P', 'Paperbacks', 'C')")
            d.commit()
            d.shelfcodes = Shelfcodes(d)

            # create a user to do the checking out
            newmember = Member(d)
            newmember.create(commit=False)
            member_name = MemberName(
                d, member_id=newmember.id, member_name='USER')
            member_name.create(commit=False)
            newmember.member_name_default = member_name.id
            newmember.commit()

            member = Member(d, newmember.id)

            member.membership_add(
                'T',
                datetime.datetime.today() + datetime.timedelta(weeks=12),
                0)
            self.assertEqual(member.checkout_good()[0], False)
            member.cash_transaction(-member.balance, 'P', 'pay membership')
            
            self.assertEqual(member.checkout_good()[0], True)
            
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

            checkouts = member.checkouts
            self.assertEqual(len(checkouts), 1)

            # we only have one book out, so
            self.assertEqual(member.checkout_good()[0], True)

            checkout = checkouts[0]

            checkout.checkin()
            self.assertEqual(book.out, False)

            # instantly overdue
            book.checkout(
                member,
                datetime.datetime.today() - datetime.timedelta(weeks=4))

            # because the book was due a week ago
            self.assertEqual(member.checkout_good()[0], False)

            # make sure there is no timewarp
            d.cursor.execute('delete from timewarp')
            d.commit()

            self.assertNotEqual(member.checkouts[0].overdue_days(), 0)
            member.checkouts[0].lose()

            # owes a fine
            self.assertEqual(member.checkout_good()[0], False)

            member.cash_transaction(
                -member.balance, 'P', 'simulate fine payment')

            # should be able to check out books again
            self.assertEqual(member.checkout_good()[0], True)

            # check the book in which should make it unlost
            member.checkouts[0].checkin()

            self.assertEqual(member.checkout_good()[0], True)
        finally:
            d.db.close()

    def testDuesChange(self):
        try:
            d = DexDB(dsn=self.dsn)

            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('P', 'Paperbacks', 'C')")
            d.commit()
            d.shelfcodes = Shelfcodes(d)

            # create a user to do the checking out
            newmember = Member(d)
            newmember.create(commit=False)
            member_name = MemberName(
                d, member_id=newmember.id, member_name='USER')
            member_name.create(commit=False)
            newmember.member_name_default = member_name.id
            newmember.commit()

            ''' This section is not working and if we actually used it we'd need to '
start fro scratch
           member = Member(d, newmember.id)
            member.membership_add('4', when='2014-12-01')

            self.assertEqual(int(member.balance), -44)
            member.cash_transaction(-member.balance, 'P', 'pay membership')
            self.assertTrue(member.membership)
            self.assertTrue(not member.membership.expired)
            _, cost, expiration = member.membership_describe(
                '4', when='2035-01-01')
            self.assertTrue(expiration)
            self.assertEqual(cost, 45)
            member.membership_add('4', when='2035-01-01')
            self.assertEqual(int(member.balance), -45)
'''
        finally:
            d.db.close()

    def testCreateFineChanges(self):
        try:
            d = DexDB(dsn=self.dsn)

            # make sure there is no timewarp
            d.cursor.execute('delete from timewarp')
            d.commit()

            # fake up a shelfcode; has to be a real one until we can get our
            # configuration from the db
            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('P', 'Paperbacks', 'C')")
            d.commit()
            d.shelfcodes = Shelfcodes(d)

            # create a user to do the checking out
            newmember = Member(d)
            newmember.create(commit=False)
            member_name = MemberName(
                d, member_id=newmember.id, member_name='USER')
            member_name.create(commit=False)
            newmember.member_name_default = member_name.id
            newmember.commit()

            member = Member(d, newmember.id)
            member.membership_add(
                'T',
                datetime.datetime.today() + datetime.timedelta(weeks=12),
                0)
            self.assertEqual(member.checkout_good()[0], False)
            member.cash_transaction(-member.balance, 'P', 'pay membership')

            self.assertEqual(member.checkout_good()[0], True)

            # create a book for us to check out
            d.add(DexLine('AUTHOR<TITLE<SERIES<P'))

            titles = list(d.search('AUTHOR', 'TITLE'))
            self.assertEqual(len(titles), 1)

            title = titles[0]

            self.assertEqual(len(title.books), 1)

            book = title.books[0]

            # instantly overdue, January 2014 edition
            book.checkout(member, datetime.datetime(2014, 1, 1))

            # before the rate change
            member.checkouts[0].checkin(datetime.datetime(2014, 8, 14, 12))

            self.assertEqual(member.balance, -10)
            member.cash_transaction(
                -member.balance, 'P', 'simulate fine payment')

            book.checkout(member, datetime.datetime(2014, 1, 1))
            # after the first rate change
            member.checkouts[0].checkin(datetime.datetime(2014, 8, 15, 12))

            self.assertEqual(member.balance, 0)
            member.cash_transaction(
                -member.balance, 'P', 'simulate fine payment')

            book.checkout(member, datetime.datetime(2014, 1, 1))
            # after the second rate change
            member.checkouts[0].checkin(datetime.datetime(2014, 9, 6, 12))

            self.assertEqual(member.balance, -4)
            member.cash_transaction(
                -member.balance, 'P', 'simulate fine payment')
        finally:
            d.db.close()

    def testCreateCost(self):
        try:
            d = DexDB(dsn=self.dsn)

            # make sure there is no timewarp
            d.cursor.execute('delete from timewarp')
            d.commit()

            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('P', 'Paperbacks', 'C')")
            d.commit()
            d.shelfcodes = Shelfcodes(d)

            # create a user to do the checking out
            newmember = Member(d)
            newmember.create(commit=False)
            member_name = MemberName(
                d, member_id=newmember.id, member_name='USER')
            member_name.create(commit=False)
            newmember.member_name_default = member_name.id
            newmember.commit()

            member = Member(d, newmember.id)

            member.membership_add('T')

            observed_cost = -member.balance

            self.assertEqual(observed_cost, member.membership.cost)

        finally:
            d.db.close()

    def testCreateUnexpiredDiscount(self):
        try:
            d = DexDB(dsn=self.dsn)

            # make sure there is no timewarp
            d.cursor.execute('delete from timewarp')
            d.commit()

            d.getcursor().execute(
                "insert into"
                " shelfcode(shelfcode, shelfcode_description, shelfcode_type)"
                " values('P', 'Paperbacks', 'C')")
            d.commit()
            d.shelfcodes = Shelfcodes(d)

            # create a user to do the checking out
            newmember = Member(d)
            newmember.create(commit=False)
            member_name = MemberName(
                d, member_id=newmember.id, member_name='USER')
            member_name.create(commit=False)
            newmember.member_name_default = member_name.id
            newmember.commit()

            member = Member(d, newmember.id)

            _, life_cost, _ = member.membership_describe('L')
            _, term_cost, _ = member.membership_describe('T')
            _, year_cost, _ = member.membership_describe('1')
            
            member.membership_add('T')
            observed_cost = -member.balance
            

            self.assertEqual(observed_cost, member.membership.cost)
            self.assertEqual(observed_cost, term_cost)

            member.cash_transaction(-member.balance, 'P', 'pay membership')

            member.membership_add('1')
            observed_cost = -member.balance

            self.assertEqual(observed_cost, member.membership.cost)
            self.assertEqual(observed_cost, year_cost)

            member.cash_transaction(-member.balance, 'P', 'pay membership')

            member.membership_add('L')
            observed_cost = -member.balance

            self.assertEqual(observed_cost, member.membership.cost)
            self.assertEqual(observed_cost, life_cost - year_cost)

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
