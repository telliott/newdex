#!/usr/bin/python
'''

Code for manipulating the online membership book

'''

import datetime

from mitsfs import db
from mitsfs import dexdb
from mitsfs import ui
from mitsfs.dex.coercers import coerce_datetime_no_timezone, coerce_boolean


__all__ = [
    'Membership', 'find_members',
    'Checkout', 'MembershipBook', 'TimeWarp', 'star_dissociated',
    'role_members', 'star_cttes',
    ]


# these really should be in the database somewhere
MAXDAYSOUT = 21
MAX_BOOKS = 8


def find_members(db, name, pseudo=False):
    """returns a list of member objects that match the given name"""
    return [
        Member(db, i)  # turning the tuple into args
        for i in
        db.cursor.execute(
            'select member_id'
            ' from member'
            ' where concat(first_name, last_name, key_initials, email) ~* %s'
            ' and pseudo = %s',
            (name, pseudo))]


class Member(db.Entry):
    def __init__(self, db, member_id=None, **kw):
        super(Member, self).__init__(
            'member', 'member_id', db, member_id, **kw)

    member_id = db.ReadField('member_id')

    first_name = db.Field('first_name')
    last_name = db.Field('last_name')
    key_initials = db.Field('key_initials')
    email = db.Field('email')
    phone = db.Field('phone')
    address = db.Field('address')

    # used to add permissions to this person for committees, etc
    rolname = db.Field('rolname')

    # fake members representing committees
    pseudo = db.Field('pseudo', coerce_boolean)

    # created = db.ReadField('member_created')
    # created_by = db.ReadField('member_created_by')
    # created_with = db.ReadField('member_created_with')
    # modified = db.ReadField('member_modified')
    # modified_by = db.ReadField('member_modified_by')
    # modified_with = db.ReadField('member_modified_with')


    @property
    def membership(self):

        member_id = self.cursor.selectvalue(
            'select membership_id'
            ' from membership'
            ' where member_id=%s'
            ' order by membership_created desc limit 1',
            (self.member_id,))
        if member_id is None:
            return None

        return Membership(self.db, membership_id=member_id)

    def membership_add(
            self, member_type, expiration=None, cost=None, when='now'):
        # expiration and cost are now ignored
        description, cost, expiration = self.membership_describe(
            member_type, when)
        if expiration:
            description += ' Expires at %s' % (expiration,)

        transaction_id = self.transaction(
            -cost, 'M', description, commit=False)

        self.cursor.execute(
            'insert into membership ('
            ' membership_type, member_id,'
            ' membership_expires, membership_payment)'
            ' values (%s, %s, %s, %s)',
            (member_type, self.member_id, expiration, transaction_id))

        self.db.commit()

    def membership_describe(self, membership_type, when='now'):
        '''Describe a new membership: text description, how much it would cost,
         and wnen it would expire'''

        c = self.cursor.execute(
            'select'
            '  membership_description, membership_cost, membership_duration'
            ' from membership_type'
            '  natural join membership_cost'
            '  natural join ('
            '   select'
            '    membership_type,'
            '    max(membership_cost_valid_from) as membership_cost_valid_from'
            '   from membership_cost'
            '   where membership_cost_valid_from < %s'
            '   group by membership_type) as current'
            ' where membership_type=%s',
            (when, membership_type))

        if c.rowcount == 0:
            return None

        (description, cost, duration) = c.fetchone()

        if duration:
            # + postgres is better at python at time intervals
            # + the return value of date_trunc doesn't always have a time zone;
            #   thus the first "at time zone" on line 4 puts it in a time zone
            #   then converts back to ostensible local time

            c = self.cursor.execute(
                'select'
                "  date_trunc("
                "     'day', max(membership_expires at time zone 'PST8PDT'))"
                "   at time zone 'PST8PDT' at time zone 'EST5EDT'"
                '  + (select membership_duration'
                '      from membership_type'
                '      where membership_type=%s)'
                ' from (select membership_expires from membership'
                '        where member_id=%s'
                '       union select current_timestamp as membership_expires'
                '      ) as ifnotnow',
                (membership_type, self.member_id))
            if c.rowcount == 0:
                expiration = None
            else:
                expiration = c.fetchone()[0]
        else:
            expiration = None

        if self.membership and not self.membership.expired and not expiration:
            cost -= self.membership.cost

        return description, cost, expiration

    @property
    def balance(self):
        return self.cursor.selectvalue(
            'select sum(transaction_amount)'
            ' from transaction'
            ' where member_id=%s',
            (self.member_id,))

    @property
    def memberships(self):

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
        else:
            s += ' ' + ui.money_str(self.balance)
        return s

    @property
    def normal_str(self):
        return '%s %s - (%s) %s' % (
            self.first_name,
            self.last_name,
            self.email,
            (
                "$%.2f" % (self.balance,)
                if not self.pseudo
                else 'COMMITTEE'))

    def info(self):
        if self.pseudo:
            return 'pseudo-member/committee: %s' % self.first_name

        info = f"Name: {self.last_name}, {self.first_name}"
        if self.key_initials:
            info += f" ({self.key_initials})"
        info += '\n'

        if self.email:
            info += f"Email: {self.email}\n"
        if self.phone:
            info += f"Phone: {self.phone}\n"

        if self.address:
            info += f"Home Address: {self.address}\n"

        info += "\n"
        info += "Current Membership: " + str(self.membership)
        info += "\nFine Credit: " + str(self.balance)
        return info

    @property
    def transactions(self):
        return list(self.cursor.execute(
            'select'
            '  transaction_amount, transaction_description,'
            '  transaction_type, transaction_created_by, transaction_created'
            ' from transaction'
            ' where member_id = %s'
            ' order by transaction_created',
            (self.member_id,)))

    def transaction(self, amount, txntype, desc, commit=True):
        txn_id = self.cursor.selectvalue(
            'insert into transaction'
            '  (transaction_amount, member_id,'
            '   transaction_type, transaction_description)'
            ' values (%s, %s, %s, %s) returning transaction_id',
            (amount, self.member_id, txntype, desc))
        if commit:
            self.db.commit()
        return txn_id

    def cash_transaction(self, amount, txntype, desc):
        cash = find_members(self.db, 'CASH', pseudo=True)[0]
        txn1_id = self.transaction(amount, txntype, desc, commit=False)
        txn2_id = cash.transaction(amount, txntype, desc, commit=False)
        self.cursor.execute(
            'insert into transaction_link values (%s, %s)',
            (txn1_id, txn2_id))
        self.db.commit()

    def fine_transaction(self, amount, desc, checkout_id, commit=True):
        txn_id = self.transaction(amount, 'F', desc, commit=False)
        self.cursor.execute(
            'insert into fine_payment values (%s, %s)',
            (checkout_id, txn_id))
        if commit:
            self.db.commit()

    def late_transaction(self, days, book, checkout_id, when, commit=False):
        'Factor out some late finage.  Does not commit by default. '
        fines = dict(self.db.getcursor().execute(
            'select fine_name, fine'
            ' from fine'
            '  natural join ('
            '   select fine_name, max(fine_valid_from) as fine_valid_from'
            '  from fine where fine_valid_from < %s'
            '  group by fine_name) as current',
            (when,)))
        fine = -min(days * fines['lateday'], fines['maxlate'])
        self.fine_transaction(
            fine,
            'Book %s overdue %d days.' % (book, days),
            checkout_id,
            commit=commit)
        return fine

    @property
    def non_void_transactions(self):
        return list(self.cursor.execute(
            "select"
            "  transaction_id, transaction_amount, transaction_description,"
            "  transaction_type, transaction_created_by, transaction_created"
            " from transaction"
            " where transaction_id in ("
            "  select t0.transaction_id"
            "  from transaction t0"
            "  where"
            "   t0.transaction_type != 'V' and"
            "   t0.member_id = %s"
            "  except ("
            "   select t1.transaction_id"
            "    from"
            "     transaction t1"
            "     inner join transaction_link tl"
            "      on (t1.transaction_id = tl.transaction_id1)"
            "     inner join transaction t2"
            "      on (t2.transaction_id =  tl.transaction_id2)"
            "    where t2.transaction_type = 'V'"
            "   union select t1.transaction_id"
            "    from"
            "     transaction t1"
            "     inner join transaction_link tl"
            "      on (t1.transaction_id = tl.transaction_id2)"
            "     inner join transaction t2"
            "      on (t2.transaction_id = tl.transaction_id1)"
            "    where t2.transaction_type = 'V'))"
            " order by transaction_created",
            (self.member_id,)))

    def void_transaction(self, txn_id):
        with self.getcursor() as c:
            txn_ids = self.void_transaction_inner(txn_id, c)
        voided = []
        for x in txn_ids:
            voided += list(self.cursor.execute(
                'select'
                '  transaction_amount, transaction_description,'
                '  transaction_type, transaction_created_by,'
                '  transaction_created, member_id'
                ' from transaction'
                ' where transaction_id = %s',
                (x,)))
        return voided

    def void_transaction_inner(self, txn_id, c):
        txn_ids = [(txn_id, '')]
        txn_ids += list(c.execute(
            'select transaction_id1, transaction_type'
            ' from transaction_link'
            '  join transaction on (transaction_id = transaction_id1)'
            ' where transaction_id2 = %s'
            ' union '
            'select transaction_id2, transaction_type'
            ' from transaction_link'
            '  inner join transaction on (transaction_id = transaction_id2)'
            ' where transaction_id1 = %s', (txn_id, txn_id,)))
        (txn_ids, types) = list(zip(*txn_ids))
        if 'V' in types:
            print("Transaction already void, continuing...")
            return
        void_txn_ids = []
        for x in txn_ids:
            ((amount, desc, member_id, date),) = tuple(c.execute(
                'select transaction_amount, transaction_description,'
                '  member_id, transaction_created'
                ' from transaction where transaction_id = %s', (x,)))
            void_txn_ids += c.execute(
                "insert into transaction (transaction_amount, member_id,"
                "  transaction_type, transaction_description)"
                " values (%s, %s, 'V', %s) returning transaction_id",
                (-amount, member_id,
                 'VOIDED: ' + str(date.date()) + ' Desc: ' + desc))
        c.executemany(
            'insert into transaction_link values (%s, %s)',
            list(zip(txn_ids, void_txn_ids)))
        return txn_ids

    @property
    def checkouts(self):
        c = self.cursor.execute(
            'select checkout_id'
            ' from'
            '  checkout_member'
            '  natural join checkout'
            ' where'
            '  member_id = %s and'
            '  checkin_stamp is null'
            ' order by checkout_stamp',
            (self.member_id,))

        return [ Checkout(self.db, checkout_id=x[0]) for x in c.fetchall() ]

    @property
    def checkout_history(self):
        c = self.cursor.execute(
            'select checkout_id'
            ' from'
            '  checkout_member'
            '  natural join checkout'
            ' where member_id = %s'
            ' order by checkout_stamp desc',
            (self.member_id,))

        return [ Checkout(self.db, checkout_id=x[0]) for x in c.fetchall() ]

    def checkout_good(self, override=False):
        msgs = []
        correct = []


        if self.balance < 0:
            msgs.append(str(self) + ' has a negative balance.')
            correct.append('pay fines')

        if self.membership is None:
            msgs.append(str(self) + ' has no membership.')
            correct.append('get a membership')
        elif self.membership.expired:
            msgs.append(str(self) + ' has an expired membership.')
            correct.append('get new membership')

        books_due = [out for out in self.checkouts if out.due]

        if books_due:
            msg = str(self) + ' has overdue books.'
            if not override:
                msg += '\n' + '\n'.join(str(book) for book in books_due)
            msgs.append(msg)
            correct.append('return books')

        count = len([x for x in self.checkouts if not x.lost])
        if count >= MAX_BOOKS:
            msgs.append(('%s has %d books out.' % (str(self), count)))
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

    def key(self, login):
        self.rolname = login
        cursor = self.db.cursor
        cursor.execute('set role "*chamber"')
        cursor.execute('create role "%s" login' % login)
        cursor.execute('grant keyholders to "%s"' % login)
        cursor.execute('reset role')
        self.db.commit()

    @property
    def committees(self):
        return list(self.db.cursor.execute(
            "select roleid_.rolname"
            " from"
            "  pg_auth_members"
            "  join pg_roles roleid_ on roleid=roleid_.oid"
            "  join pg_roles member_ on member = member_.oid"
            " where"
            " member_.rolname = %s and"
            " roleid_.rolname != 'keyholders'",
            (self.role,)))

    def dekey(self):
        cursor = self.db.cursor
        for group in self.committees:
            cursor.execute('revoke "%s" from "%s"' % (group, self.rolname))
        cursor.execute('set role "*chamber"')
        cursor.execute('drop role "%s"' % (self.rolname,))
        cursor.execute('reset role')
        self.db.commit()

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
                'update member_comment set member_id=%s where member_id=%s',
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
        except:
            self.db.rollback()
            raise
        finally:
            c.execute('reset role')

class Membership(db.Entry):
    def __init__(self, db, membership_id=None, **kw):
        super(Membership, self).__init__(
            'membership', 'membership_id', db, membership_id, **kw)

    created = db.ReadField('membership_created')
    created_by = db.ReadField('membership_created_by')
    created_with = db.ReadField('membership_created_with')
    membership_id = db.ReadField('membership_id')

    member_id = db.ReadField('member_id')
    expires = db.ReadField('membership_expires')
    membership_type = db.ReadField('membership_type')
    payment_id = db.ReadField('membership_payment')

    @property
    def description(self):

        return self.cursor.selectvalue(
            'select membership_description'
            ' from membership_type'
            ' where membership_type=%s',
            (self.membership_type,))

    @property
    def expired(self):
        if self.expires is None:
            return False
        return self.expires.replace(tzinfo=None) < datetime.datetime.today()

    @property
    def cost(self):
        pid = self.payment_id
        v = list(self.cursor.execute(
            'select transaction_id2'
            ' from transaction_link'
            '  join transaction on transaction_id2 = transaction_id'
            " where transaction_id1 = %s and transaction_type='V'",
            (pid,)))
        if v:
            return 0.0

        return self.cursor.selectvalue(
            'select -transaction_amount'
            ' from transaction'
            ' where transaction_id=%s',
            (pid,))

    def __str__(self):
        desc = self.description + " "

        if self.expires is None:
            return desc + ui.Color.good("Expires: Never")

        expires = str(self.expires.date())
        if self.expired:
            return desc + ui.Color.warning("Expired: " + expires)

        return desc + ui.Color.good("Expires: " + expires)


class Checkout(db.Entry):
    def __init__(self, db, checkout_id=None, **kw):
        super(Checkout, self).__init__(
            'checkout', 'checkout_id', db, checkout_id, **kw)

    checkout_id = db.ReadField('checkout_id')
    checkout_stamp = db.ReadField(
        'checkout_stamp', coerce_datetime_no_timezone)
    book_id = db.ReadField('book_id')
    checkout_user = db.ReadField('checkout_user')

    checkin_user = db.ReadField('checkin_user')
    checkin_stamp = db.ReadField('checkin_stamp',coerce_datetime_no_timezone)

    checkout_lost = db.ReadFieldUncached(
        'checkout_lost', coerce_datetime_no_timezone)

    @property
    def title(self):
        return dexdb.Title(self.db,
            self.cursor.selectvalue(
                'select title_id'
                ' from book'
                ' where book_id = %s',
                (self.book_id,)))

    @property
    def book(self):
        return dexdb.Book(self.title, self.book_id)

    @property
    def due_stamp(self):
        when = self.checkout_stamp + datetime.timedelta(days=MAXDAYSOUT)
        new = datetime.datetime(when.year, when.month, when.day, 3, 0, 0, 0)
        if when.hour >= 3:
            new += datetime.timedelta(days=1)
        return new

    @property
    def due_date(self):
        # visible due date should be the day before the 3am actual due datetime
        when = self.due_stamp - datetime.timedelta(days=1)
        return datetime.datetime(when.year, when.month, when.day, 3, 0, 0, 0)

    def _timewarp(self, stamp):
        timewarp = self.cursor.selectvalue(
            'select timewarp_end'
            ' from timewarp'
            ' where'
            '  timewarp_start < %s'
            '  and timewarp_end > %s',
            (stamp, stamp,))
        if timewarp is None:
            return stamp

        return coerce_datetime_no_timezone(timewarp)

    @property
    def due(self):
        return self.due_stamp < datetime.datetime.now() and not self.lost

    def overdue_days(self, when=None):
        '''Returns the number of days something is overdue by,
        possibly vs. a specified checkin date'''
        if when is None:
            when = datetime.datetime.now()

        delta = (when - self._timewarp(self.due_stamp))

        return max(delta.days, 0)

    @property
    def lost(self):
        return self.checkout_lost

    @property
    def member(self):
        # uncached for the moment, so use it somewhat sparingly
        member_ids = list(self.cursor.execute(
            'select member_id from checkout_member where checkout_id = %s',
            (self.id,)))
        if not member_ids:
            # database constraints say there will be one or zero
            return None
        return Member(self.db, member_ids[0])

    def lose(self, when=None):
        '''Declare a book lost.  Return what to tell the user.'''

        msgs = []

        if when is None:
            when = datetime.datetime.today()

        if self.lost:  # you can only lose a book once per checkout
            return

        late = self.overdue_days(when)
        if late:
            fine = self.member.late_transaction(late, self.book, self.id, when)
            msgs.append('FINE: %s, book was overdue %d days' % (
                ui.money_str(-fine), late))

        self.cursor.execute(
            'update checkout set checkout_lost=%s where checkout_id=%s',
            (when, self.id))

        fine = -self.book.shelfcode.cost
        self.member.fine_transaction(
            fine,
            'Lost book %s' % (self.book,),
            self.id,
            commit=True)
        msgs.append(
            'FINE: %s for lost %s' % (-fine, self.book.shelfcode.description))

        return '\n'.join(msgs)

    def _fine_txns(self, match):  # match='%'
        return list(self.cursor.execute(
            'select transaction_id'
            ' from'
            '  transaction'
            '  natural join fine_payment'
            ' where'
            '  checkout_id=%s and'
            '  transaction_description like %s',
            (self.id, match)))

    @property
    def lost_txns(self):
        '''returns a list.  If it has more than one member, things
        will likely go pear shaped relatively rapidly .'''
        return self._fine_txns('Lost book %')

    def checkin(self, when=None):
        msgs = []
        if when is None:
            when = datetime.datetime.now()
        with self.getcursor() as c:
            checkouts = list(c.execute(
                'select'
                '  member_id, checkout_stamp, checkin_stamp'
                ' from'
                '  checkout'
                '  natural join checkout_member'
                ' where checkout_id=%s',
                (self.id,)))
            if len(checkouts) != 1:
                raise dexdb.CirculationException(
                    "%d checkout rows, can't proceed; apologize and"
                    " convey book to libcomm"
                    % len(checkouts))
            ((member_id, checkout_stamp, checkin_stamp),) = checkouts

            if checkin_stamp:
                raise dexdb.CirculationException(
                    '%s already checked in' % (str(self),))

            if not self.member.pseudo:
                if self.lost:
                    ltxns = self.lost_txns
                    if ltxns:
                        self.member.void_transaction_inner(ltxns[-1], c)
                        msgs.append('Lost book fine voided.')
                else:
                    days = self.overdue_days(when)
                    if days and not self.member.pseudo:
                        msgs.append('Book is overdue %d days' % (days,))
                        fine = self.member.late_transaction(
                            days, self.book, self.id, when)
                        msgs.append(
                            'FINE: %s added to balance' % (
                                ui.money_str(fine),))

            c.execute(
                'update checkout'
                ' set checkin_stamp = %s, checkin_user = current_user'
                ' where checkout_id=%s',
                (when, self.id))

            msgs.append(
                'Book checked out to %s has been checked in' % (self.member,))

            if self.book.withdrawn:
                msgs += [
                    '',
                    '***',
                    'Returned book was withdrawn from the library.',
                    'Please place it on the Panthercomm shelf with a note.',
                    '***',
                    ]
        return '\n'.join(msgs)

    def __str__(self):
        return ' '.join(str(x) for x in (
            self.book, self.checkout_stamp, self.checkout_user,
            self.checkin_stamp, self.checkin_user))


class MembershipBook(object):
    def __init__(self, db):
        'Takes a db aggregator object which is presumably a DexDB for now'
        self.db = db
        self.txn_types = dict(self.db.cursor.execute(
            'select'
            '  transaction_type, transaction_type_description'
            ' from transaction_type'))
        self.basic_transactions = dict(self.db.cursor.execute(
            'select'
            '  transaction_type, transaction_type_description'
            ' from transaction_type'
            ' where transaction_type_basic'))
        self.fancy_transactions = dict(self.db.cursor.execute(
            'select'
            '  transaction_type, transaction_type_description'
            ' from transaction_type'
            ' where not transaction_type_basic'))
        self.membership_types = list(self.db.cursor.execute(
            'select membership_type, membership_description, membership_cost'
            ' from membership_type'
            ' natural join membership_cost'
            ' natural join ('
            '  select'
            '   membership_type,'
            '   max(membership_cost_valid_from) as membership_cost_valid_from'
            '  from membership_cost'
            '  where membership_cost_valid_from < current_timestamp'
            '  group by membership_type) as current_costs'
            ' where'
            '  (membership_type_valid_until is null'
            '   or current_timestamp < membership_type_valid_until)'
            '  and current_timestamp > membership_type_valid_from'
            ' order by membership_duration, membership_type'
            ))
        self.db.rollback()

    def complete_name(self, s):
        return [str(member) for member in find_members(self.db, s)]

    def get(self, name):
        return find_members(self.db, name)

    def search(self, name):
        return find_members(self.db, name)

    def __getitem__(self, member_id):
        """returns the unique member object for a given member_id"""
        return Member(self.db, member_id)

    def vgg(self):
        bad_people = list(self.db.cursor.execute(
            'select'
            '  member_email,'
            '  member_name,'
            '  array_agg(checkout_stamp),'
            '  array_agg(shelfcode),'
            '  array_agg(title_id)'
            ' from'
            '  checkout'
            ' natural join checkout_member'
            ' natural join member'
            ' join member_name on member_name_default = member_name_id'
            ' join member_email on member_email_default = member_email_id'
            ' natural join book'
            ' natural join shelfcode'
            ' where'
            '  not pseudo'
            '  and checkin_stamp is null'
            '  and checkout_lost is null'
            '  and checkout_stamp <'
            "   (current_timestamp - interval '3 weeks 1 day')"
            ' group by member_name, member_email order by member_name'))
        return [
            (
                email,
                name,
                [
                    (checkout_stamp, shelfcode, dexdb.Title(
                        self.db, title_id))
                    for (checkout_stamp, shelfcode, title_id)
                    in list(zip(stamps, shelfcodes, title_ids))
                    ]
                )
            for (email, name, stamps, shelfcodes, title_ids) in bad_people]


class TimeWarp(db.Entry):
    def __init__(self, db, timewarp_id=None, **kw):
        super(TimeWarp, self).__init__(
            'timewarp', 'timewarp_id', db, timewarp_id, **kw)

    timewarp_id = db.ReadField('timewarp_id')
    start = db.Field('timewarp_start', coerce_datetime_no_timezone)
    end = db.Field('timewarp_end', coerce_datetime_no_timezone)

    created = db.ReadField('timewarp_created')
    created_by = db.ReadField('timewarp_created_by')
    created_with = db.ReadField('timewarp_created_with')

    modified = db.ReadField('timewarp_modified')
    modified_by = db.ReadField('timewarp_modified_by')
    modified_with = db.ReadField('timewarp_modified_with')


def star_dissociated(db):
    """Returns a list of roles in the database that can log in, with
    no associated member."""
    return list(db.cursor.execute(
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
        ' order by rolname'))


def role_members(db, role):
    """Returns an iterator of member objects associated with a given
    database role."""
    return sorted(
        (
            Member(db, member_id)
            for member_id in db.getcursor().execute(
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
        key=lambda mem: str(mem.name))


def star_cttes(db):
    """Returns a list of committee roles"""
    return list(db.getcursor().execute(
        'select roleid_.rolname'
        ' from'
        '  pg_auth_members'
        '  join pg_roles roleid_ on roleid = roleid_.oid'
        '  join pg_roles member_ on member = member_.oid'
        " where"
        "  member_.rolname = '*chamber' and"
        "  admin_option and"
        "  roleid_.rolname != 'keyholders'")) + ['*chamber']
