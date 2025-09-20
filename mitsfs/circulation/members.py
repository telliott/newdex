'''

Code for manipulating the online membership book

'''

import datetime
import re

from mitsfs.core import db
from mitsfs import ui
from mitsfs.util.coercers import coerce_boolean
from mitsfs.circulation.membership import Membership
from mitsfs.circulation.transactions import get_transactions, Transaction
from mitsfs.circulation.checkouts import Checkouts

# constant for number of books a member can have checked out
MAX_BOOKS = 8


def format_name(first, last):
    """
    quick helper to format names into last, first.

    Parameters
    ----------
    first : str
        first name.
    last : str
        last_name.

    Returns
    -------
    str
        a pretty string with the name

    """
    if not last:
        return first or ''
    if not first:
        return last
    return f'{last}, {first}'


class Members(object):
    def __init__(self, db):
        self.db = db

    def find(self, name, pseudo=False):
        """
        returns a list of member objects that match the given name

        Parameters
        ----------
        db : db object
            The db to query against.
        name : str
            a string that will be compared against a concatenation of
            relevant fields.
        pseudo : boolen, optional
            Whether to include the fake members in the search.
            Default is False.

        Returns
        -------
        list(member)
            A list of member objects that match the given string.

        """
        name = re.split(r'[^a-zA-Z]+', name)
        where = ' and '.join(['concat(first_name, last_name,  key_initials, email) ~* %s'] * len(name))

        return [
            Member(self.db, i)
            for i in
            self.db.cursor.execute(
                'select member_id'
                ' from member'
                ' where'
                f' {where}'
                ' and pseudo = %s',
                (*name, pseudo))]

    def complete_name(self, s, pseudo=False):
        '''
        Returns a list of member names for autocompletion

        Parameters
        ----------
        s : str
            A substring to search against the member names.

        Returns
        -------
        list: str
            list of names.

        '''
        return [member.full_name for member in self.find(s, pseudo)]

    def __getitem__(self, member_id):
        """returns the unique member object for a given member_id"""
        return Member(self.db, member_id)


class Member(db.Entry):
    def __init__(self, db, member_id=None, **kw):
        """
        Class representing an individual member of the library, including
        their contact information, checkouts, balance, etc.

        Parameters
        ----------
        db : database object
            The db to query against.
        member_id : int, optional
            The member to operate on. The default is None.
            If member_id is omitted, it will hold the data provided until
            a create_call is issued.
        **kw : additional parameters
            key/value parameters to initiate the member object with

        Returns
        -------
        None.

        """
        super(Member, self).__init__(
            'member', 'member_id', db, member_id, **kw)

    member_id = db.ReadField('member_id')

    # Core member info from the member table
    first_name = db.Field('first_name')
    last_name = db.Field('last_name')
    email = db.Field('email')
    phone = db.Field('phone')
    address = db.Field('address')

    # initials if you're a keyholder
    key_initials = db.Field('key_initials')

    # used to add db permissions to this person for committees, etc
    rolname = db.Field('rolname')

    # a flag for fake members representing committees
    pseudo = db.Field('pseudo', coerce_boolean)

    membership_ = None
    checkouts_ = None

    @property
    def full_name(self):
        return format_name(self.first_name, self.last_name)

    @property
    def membership(self):
        '''
        The current active membership for the person (if any). Returns a
        Membership object.

        Note that it caches the object to avoid excessive db lookups.

        Returns
        -------
        Membership
            The active or most recent membership associated with a member.

        '''
        if self.membership_:
            return self.membership_

        member_id = self.cursor.selectvalue(
            'select membership_id'
            ' from membership'
            ' where member_id=%s'
            ' order by membership_created desc limit 1',
            (self.member_id,))
        if member_id is not None:
            self.membership_ = Membership(self.db, membership_id=member_id)
        return self.membership_

    def membership_add(self, member_type):
        '''
        Adds new membership of the provided MembershipType object
        to the member, including logging the transaction.

        Parameters
        ----------
        member_type : MembershipType
            The membership type to add

        Returns
        -------
        None.

        '''
        desc = member_type.description
        cost = member_type.cost
        new_expiration = None

        if member_type.duration is not None:
            new_expiration = self.membership_addition_expiration(member_type)
            desc += f" Expires on {new_expiration.strftime('%Y-%m-%d')}"
        elif self.membership and not self.membership.expired:
            # Apply a discount to L/P if they have an active membership
            cost -= self.membership.cost

        tx = Transaction(self.db, self.member_id, amount=-cost,
                         transaction_type='M', description=desc)
        tx.create(commit=False)

        ms_id = self.cursor.selectvalue(
            'insert into membership ('
            ' membership_type, member_id,'
            ' membership_expires, membership_payment)'
            ' values (%s, %s, %s, %s)'
            ' returning membership_id',
            (member_type.code, self.member_id, new_expiration, tx.id))

        self.db.commit()
        self.membership_ = Membership(self.db, membership_id=ms_id)

    def membership_addition_expiration(self, mtype):
        '''
        Calculates the new expiration date for a member if the
        MembershipType object is purchased. Takes into account how much
        time is remaining on their current membership.

        Parameters
        ----------
        member_type : MembershipType
            Proposed MembershipType to purchase

        Returns
        -------
        datetime
            The date the membership will expire.

        '''
        if mtype.duration is None:
            return None

        return self.cursor.selectvalue(
               'select'
               "  date_trunc("
               "     'day', max(membership_expires at time zone 'PST8PDT'))"
               "   at time zone 'PST8PDT' at time zone 'EST5EDT'"
               '  + %s'
               ' from (select membership_expires from membership'
               '        where member_id=%s'
               '       union select current_timestamp as membership_expires'
               '      ) as ifnotnow',
               (mtype.duration, self.member_id))

    @property
    def balance(self):
        '''
        Returns
        -------
        decimal
            The current member balance.

        '''
        bal = self.cursor.selectvalue(
            'select sum(transaction_amount)'
            ' from transaction'
            ' where member_id=%s',
            (self.member_id,))
        return bal or 0

    @property
    def membership_history(self):
        '''
        Returns
        -------
        list
            List of all memberships purchased by the user historically
        '''
        return [
            Membership(self.db, membership_id=x)
            for x in self.cursor.execute(
                'select membership_id'
                ' from membership'
                ' where member_id=%s'
                ' order by membership_created desc',
                (self.member_id,))
            ]

    def __str__(self):
        # sigh, ftr, the angry fruit salad wasn't my idea
        s = ui.Color.info("%s, %s" % (self.last_name, self.first_name))
        email = self.email
        if email:
            s += ' <%s>' % email
        if self.pseudo:
            s += ' COMMITTEE'
        return s

    @property
    def normal_str(self):
        return '%s %s - (%s) %s' % (
            self.first_name,
            self.last_name,
            self.email,
            (f'{self.balance:.2f}' if not self.pseudo else 'COMMITTEE'))

    def info(self):
        '''
        Returns
        -------
        string
            Helpful summary display of basic user information.

        '''
        if self.pseudo:
            return 'pseudo-member/committee: %s' % self.first_name

        info = f"Name: {self.full_name}"
        if self.key_initials:
            info += f" ({self.key_initials})"
        info += '\n'

        if self.email:
            info += f"Email: {self.email}\n"
        if self.phone:
            info += f"Phone: {self.phone}\n"

        if self.address:
            info += f"Home Address: {self.address}\n"

        return info

    @property
    def transactions(self, include_voided=True):
        '''
        Returns
        -------
        list (Transactions).
            A list of transaction objects, sorted oldest to newest

        '''
        return get_transactions(self.db, self.member_id, include_voided)

    @property
    def checkouts(self):
        self.checkouts_ = Checkouts(self.db, member_id=self.member_id)
        return self.checkouts_

    def reset_checkouts(self):
        self.checkouts_ = None

    def can_checkout(self, override=False):
        msgs = []
        correct = []

        if self.balance < 0:
            msgs.append(self.first_name + ' has a negative balance.')
            correct.append('pay fines')

        if self.membership is None:
            msgs.append(self.first_name + ' has no membership.')
            correct.append('get a membership')
        elif self.membership.expired:
            msgs.append(self.first_name + ' has an expired membership.')
            correct.append('get new membership')

        books_due = self.checkouts.overdue

        if books_due:
            msg = self.first_name + ' has overdue books.'
            if not override:
                msg += '\n' + '\n'.join(str(book) for book in books_due)
            msgs.append(msg)
            correct.append('return books')

        count = len([x for x in self.checkouts.out if not x.lost])
        if count >= MAX_BOOKS:
            msgs.append(('%s has %d books out.' % (self.first_name, count)))
            if 'return books' not in correct:
                correct.append('return books')

        cmsg = ''

        if len(correct) > 0:
            cmsg = correct[0].capitalize()
        if len(correct) > 2:
            cmsg += ', ' + ', '.join(correct[1:-1]) + ','
        if len(correct) > 1:
            cmsg += ' and ' + correct[-1]

        return not bool(msgs), msgs, cmsg

    def check_initials_ok(self, inits):
        '''
        Verify that nobody else has the initials being proposed for a member

        Parameters
        ----------
        inits : str
            Set of proposed initials to check.

        Returns
        -------
        bool
            Whether the initials are OK to use (i.e. unused)
        '''
        member = self.db.cursor.selectvalue('select member_id from member'
                                            ' where key_initials = %s',
                                            (inits,))
        if member and member != self.id:
            return False
        return True

    def key(self, login, inits):
        '''
        Keys a member. Doesn't set the necessary values in the member object -
        that is currently all done in hamster and should likely be ported over
        here.

        Parameters
        ----------
        login : str
            the MIT id that this member uses to login.

        Returns
        -------
        None.

        '''
        self.rolname = login
        self.key_initials = inits
        cursor = self.db.cursor
        cursor.execute('set role "*chamber"')
        cursor.execute('create role "%s" login' % login)
        cursor.execute('grant keyholders to "%s"' % login)
        cursor.execute('reset role')
        self.db.commit()

    @property
    def committees(self):
        '''

        Returns
        -------
        list: str
            A list of committees this member is part of.

        '''
        return self.db.cursor.fetchlist(
            "select roleid_.rolname"
            " from"
            "  pg_auth_members"
            "  join pg_roles roleid_ on roleid=roleid_.oid"
            "  join pg_roles member_ on member = member_.oid"
            " where"
            " member_.rolname = %s and"
            " roleid_.rolname != 'keyholders'",
            (self.rolname,))

    def dekey(self):
        '''
        Remove key privileges from a person

        Returns
        -------
        None.

        '''
        cursor = self.db.cursor
        for group in self.committees:
            cursor.execute('revoke "%s" from "%s"' % (group, self.rolname))
        rolname = self.rolname
        cursor.execute('set role "*chamber"')
        cursor.execute('drop role "%s"' % (rolname,))
        cursor.execute('reset role')
        self.db.commit()
        self.key_initials = None
        self.rolname = None

    def grant(self, role):
        if role == '*chamber':
            self.db.cursor.execute('set role "*chamber"')
        self.db.cursor.execute('grant "%s" to "%s"' % (role, self.rolname))
        if role == '*chamber':
            self.db.cursor.execute('reset role')
        self.db.commit()

    def revoke(self, role):
        if role == '*chamber':
            self.db.cursor.execute('set role "*chamber"')
        self.db.cursor.execute('revoke "%s" from "%s"' % (role, self.rolname))
        if role == '*chamber':
            self.db.cursor.execute('reset role')
        self.db.commit()

    def merge(self, other):
        other_id = other.member_id
        assert self.id != other_id
        c = self.db.getcursor()
        c.execute('set role "speaker-to-postgres"')
        try:
            c.execute(
                'update checkout_member set member_id=%s where member_id=%s',
                (self.id, other_id))
            c.execute(
                'update membership set member_id=%s where member_id=%s',
                (self.id, other_id))
            c.execute(
                'update transaction set member_id=%s where member_id=%s',
                (self.id, other_id))
            c.execute(
                'delete from member where member_id=%s',
                (other_id,))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        finally:
            c.execute('reset role')


def invalid_logins(db):
    """Returns a list of roles in the database that can log in, with
    no associated member."""
    return db.cursor.fetchlist(
        'select rolname'
        ' from'
        '  pg_roles'
        '  left join pg_auth_members on pg_roles.oid = roleid'
        '  natural left join member'
        ' where'
        '  roleid is null and'
        '  rolcanlogin and'
        '  not rolsuper and'
        '  member.rolname is null'
        ' order by rolname')


def role_members(db, role):
    """Returns an iterator of member objects associated with a given
    database role."""
    return sorted(
        (
            Member(db, member_id)
            for member_id in db.getcursor().fetchlist(
                'select member_id'
                ' from'
                '  pg_auth_members'
                '  join pg_roles roleid_'
                '   on pg_auth_members.roleid = roleid_.oid'
                '  join pg_roles member_ on'
                '   pg_auth_members.member = member_.oid'
                '  join member on member.rolname = member_.rolname'
                ' where roleid_.rolname = %s',
                (role,))),
        key=lambda mem: str(mem.full_name))


def star_committees(db):
    """Returns a list of committee roles"""
    omit = ['speaker-to-postgres', 'keyholders', 'wheel']
    committees = db.cursor.fetchlist(
        'select rolname'
        ' from'
        '  pg_roles'
        ' where not rolcanlogin'
        "  and rolname !~ '^pg_'")
    return list(set(committees) - set(omit))
