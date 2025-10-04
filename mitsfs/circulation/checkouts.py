import datetime

from mitsfs.core import settings
from mitsfs.core import db
from mitsfs.util import ui

from mitsfs.util import coercers
from mitsfs.circulation import transactions

# how long you can have a book out for
MAXDAYSOUT = 21


class Checkouts(list):
    def __init__(self, db, member_id=None,
                 book_id=None, out=False, checkouts=[]):
        '''
        Get a history of checkouts given the provided parameters. It is
        theoretically possible to use more than one of the inputs, but it's
        unlikely to be useful.

        Parameters
        ----------
        db : Database
            The database to get history from.
        member_id : int
             The id of the person
        book_id : int
            The id of the book

        Returns
        -------
        None.
        '''
        super().__init__()
        c = db.getcursor()
        self.book_id = book_id
        self.member_id = member_id
        self.db = db

        if book_id:
            sql = 'select checkout_id from checkout where book_id = %s'
            if out:
                sql += ' and checkin_stamp is null'
            c_ids = c.fetchlist(sql, (book_id,))
            for c_id in c_ids:
                self.append(Checkout(self.db, checkout_id=c_id))

        if member_id:
            sql = 'select checkout_id from checkout where member_id = %s'
            if out:
                sql += ' and checkin_stamp is null'
            c_ids = c.fetchlist(sql, (member_id,))
            for c_id in c_ids:
                self.append(Checkout(self.db, checkout_id=c_id))

        for x in checkouts:
            self.append(x)

    def _clone(self, checkouts):
        c = Checkouts(self.db, checkouts=checkouts)

        # have to set these separately, or they'd trigger an init load
        c.book_id = self.book_id
        c.member_id = self.member_id

        return c

    @property
    def out(self):
        '''
        Returns
        -------
        list
            Checkouts currently open for this entity.

        '''
        return self._clone([x for x in self
                            if x.checkin_stamp is None and not x.lost])

    @property
    def overdue(self):
        '''
        Returns
        -------
        list
            Checkouts currently overdue for this entity.

        '''
        return self._clone([x for x in self if x.overdue])

    def reload(self):
        self.clear()
        self.__init__(self.db, member_id=self.member_id, book_id=self.book_id)

    def display(self, width=79, show_members=False, enum=False):
        results = []
        for num, checkout in enumerate(self):
            if checkout.lost:
                duestr = ui.Color.warning('LOST: ')
                duedate = checkout.checkin_stamp.date()
            elif checkout.checkin_stamp:
                duestr = 'In: '
                duedate = checkout.checkin_stamp.date()
            else:
                duestr = 'Due: '
                duedate = ui.color_due_date(checkout.due_stamp)

            duestr = f'  {duestr}{duedate}'
            color_padding = len(duestr) - ui.len_color_str(duestr)

            author = checkout.book.title.authortxt
            if enum:
                author = f'{ui.Color.select(num + 1)}. {author}'
            author = author[:width - ui.len_color_str(duestr)]

            left_offset = width - ui.len_color_str(author) + color_padding

            results.append(f'{author}{duestr:>{left_offset}}')

            title = checkout.book.title.titletxt

            if checkout.book.visible:
                title = checkout.book.title.seriestxt + ': ' + title

            title = (' ' * 6) + title + \
                ' < ' + checkout.book.shelfcode.code

            if not show_members:
                title = title[:width]
                results.append(title)
                continue

            from mitsfs.circulation.members import Member
            member = Member(self.db, checkout.member_id)
            memstr = member.full_name
            memstr = '  ' + memstr
            title = title[:width - len(memstr)]
            results.append(f'{title}{memstr:>{width - len(title)}}')

        return '\n'.join(results)

    def member_display(self, prefix=''):
        from mitsfs.circulation.members import Member
        for checkout in self:
            member = Member(self.db, checkout.member_id)
            if checkout.lost:
                duestr = ui.Color.warning('LOST: ')
                duedate = checkout.checkin_stamp.date()
            elif checkout.checkin_stamp:
                duestr = 'In: '
                duedate = checkout.checkin_stamp.date()
            else:
                duestr = 'Due: '
                duedate = ui.color_due_date(checkout.due_stamp)

            return f'{prefix}{member.full_name}  ({duestr}{duedate})'

    def vgg(self):
        '''
        Returns
        -------
        list
            Data structure describing all the people with books currently
            overdue.

        '''
        bad_people = list(self.db.cursor.execute(
            'select'
            '  email, first_name, last_name, '
            '  array_agg(checkout_stamp),'
            '  array_agg(shelfcode),'
            '  array_agg(title_id)'
            ' from'
            '  checkout'
            '  natural join member'
            '  natural join book'
            '  natural join shelfcode'
            ' where'
            '  not pseudo'
            '  and checkin_stamp is null'
            '  and checkout_lost is null'
            '  and checkout_stamp <'
            "   (current_timestamp - interval '3 weeks 1 day')"
            ' group by email, first_name, last_name order by last_name'))
        from mitsfs.dex.titles import Title
        return [
            (
                email,
                f'{last_name}, {first_name}',
                [
                    (checkout_stamp, shelfcode, Title(self.db, title_id))
                    for (checkout_stamp, shelfcode, title_id)
                    in list(zip(stamps, shelfcodes, title_ids))
                    ]
                )
            for (email, first_name, last_name, stamps, shelfcodes, title_ids)
            in bad_people]


class Checkout(db.Entry):
    def __init__(self, db, checkout_id=None, **kw):
        '''
        Class encapsulating checkout/checkin functionality.

        Parameters
        ----------
        db : Database
            The database to operate against.
        checkout_id : int, optional
            The checkout being edited. Leave as None if this is a new checkout.
        **kw : dict
            keyword arguments to set the fields

        Returns
        -------
        None.

        '''
        super(Checkout, self).__init__(
            'checkout', 'checkout_id', db, checkout_id, **kw)
        if checkout_id is None:
            self.checkout_user = self.get_logger()

    checkout_id = db.Field('checkout_id')
    member_id = db.Field('member_id')
    checkout_stamp = db.Field('checkout_stamp',
                              coercers.coerce_datetime_no_timezone)
    book_id = db.Field('book_id')
    checkout_user = db.Field('checkout_user')

    checkin_user = db.Field('checkin_user')
    checkin_stamp = db.Field('checkin_stamp',
                             coercers.coerce_datetime_no_timezone)

    lost = db.Field('checkout_lost')

    @property
    def title(self):
        '''
        Get the title of the book

        Returns
        -------
        title: Title
            Information about the title.

        '''
        return self.book.title

    @property
    def book(self):
        '''
        Returns
        -------
        book: Book
            Information about the book edition

        '''
        from mitsfs.dex.books import Book
        return Book(self.db, self.book_id)

    @property
    def due_stamp(self):
        '''
        Returns
        -------
        new : datetime
            Internal date for when the book is due back.

        '''
        when = self.checkout_stamp + datetime.timedelta(days=MAXDAYSOUT)
        due = datetime.datetime(when.year, when.month, when.day, 3, 0, 0, 0)
        if when.hour >= 3:
            due += datetime.timedelta(days=1)
        return due

    @property
    def due_date(self):
        '''
        Returns
        -------
        date
            Official visible date of when the book is due.

        '''
        # visible due date should be the day before the 3am actual due datetime
        when = self.due_stamp - datetime.timedelta(days=1)
        return datetime.date(when.year, when.month, when.day)

    @property
    def overdue(self):
        '''
        Returns
        -------
        boolean
            book is now overdue.

        '''
        return self.checkin_stamp is None and not self.lost \
            and self.due_stamp < datetime.datetime.now()

    def overdue_days(self, when=None):
        '''
        Returns
        -------
            int
                The number of days something is overdue by,
                possibly vs. a specified checkin date. Takes into account any
                timewarps that might be in effect.
        '''
        if not when:
            when = datetime.datetime.today()
        due = self.due_stamp

        if settings.timewarps_global:
            due = settings.timewarps_global.warp_date(due)
        diff = when - due
        return max(diff.days, 0)

    def lose(self, when=None):
        '''
        Declare a book lost.

        Returns
        -------
        str
            Messages to be printed back to the administrator
        '''
        if not when:
            when = datetime.datetime.today()

        msgs = []

        if self.lost:  # you can only lose a book once per checkout
            msgs.apppend('Book is already lost. Nothing to do.')
            return

        # check the book in so that we charge any overdue fee and have a
        # checkin stamp/user
        self.checkin(when, commit=False)

        # Add a fine transaction for the lost book
        fine = -self.book.shelfcode.replacement_cost
        tx = transactions.FineTransaction(self, self.member_id, self.id,
                                          amount=fine,
                                          description=f'Lost book {self.book}')
        tx.create()

        # TODO setting the transaction_id marks the book as lost. But that just
        # marks it in the checkout. Should we also update the book here?
        self.lost = tx.id
        self.db.commit()

        msgs.append(
            'FINE: %s for lost %s' % (-fine, self.book.shelfcode.description))

        return '\n'.join(msgs)

    def get_logger(self):
        '''
        Because we use postgres to track who is making changes, we need to ask
        it for that info

        Returns
        -------
        id: string
            name of the user performing the checkin

        '''
        return self.db.cursor.selectvalue('select current_user')

    def checkin(self, when=None,
                is_pseudo=False, commit=True):
        '''
        Checks in a book that had been checked out. Assesses any overdue fines.

        Parameters
        ----------
        when : datetime, optional
            When to check in the book as of. The default is now.

        Returns
        -------
        str
            Messages to be printed back to the administrator

        '''
        if not when:
            when = datetime.datetime.today()

        msgs = []

        if self.checkin_stamp and not self.lost:
            return f'{self} is already checked in'

        if not is_pseudo:
            if self.lost:
                # book is being returned, so the lost book fine should be
                # voided
                tx = transactions.Transaction(self.db, self.member_id,
                                              self.lost)
                tx.void()
                self.lost = None
            else:
                days = self.overdue_days(when)
                if days:
                    msgs.append('Book is overdue %d days' % (days,))
                    fine = transactions.OverdueTransaction(self.db,
                                                           self.member_id,
                                                           self.id, days=days,
                                                           book=self.title)
                    fine.create()
                    msgs.append('FINE: %s added to balance' % (
                        ui.money_str(fine.amount),))
        self.checkin_stamp = when
        self.checkin_user = self.get_logger()

        msgs.append(f'{self.book} has been checked in')
        if self.book.withdrawn:
            msgs += [
                '',
                '***',
                'Returned book was withdrawn from the library.',
                'Please place it on the Panthercomm shelf with a note.',
                '***',
                ]
        if commit:
            self.db.commit()

        return '\n'.join(msgs)

    def __str__(self):
        return ', '.join(str(x) for x in (
            f'{self.book} ({self.book_id})', self.checkout_stamp,
            self.checkout_user, self.checkin_stamp, self.checkin_user))
