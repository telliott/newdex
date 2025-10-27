import datetime

from mitsfs.core import db
from mitsfs.util import coercers
from mitsfs.circulation import checkouts
from mitsfs.circulation import members
from mitsfs.util import exceptions


class Book(db.Entry):
    def __init__(self, database, book_id=None, **kw):
        super().__init__('book', 'book_id', database, book_id, **kw)

    # Doing a little bit of hacking here to get title and shelfcode
    # objects into place
    title = db.Field(
        'title_id', coercer=coercers.coerce_title,
        prep_for_write=coercers.uncoerce_title)
    shelfcode = db.Field(
        'shelfcode_id', coercer=coercers.coerce_shelfcode,
        prep_for_write=coercers.uncoerce_shelfcode)

    visible = db.Field('book_series_visible')
    doublecrap = db.Field('doublecrap')
    review = db.Field('review')
    withdrawn = db.Field('withdrawn')

    # probably vestigial
    comment = db.Field('book_comment')

    @property 
    def titles(self):
        return self.title.titles
    
    @property 
    def authors(self):
        return self.title.authors
    
    
    def create(self, commit=True):
        if self.title is None or self.shelfcode is None:
            raise exceptions.Ambiguity('Title and Shelfcode must be'
                                       ' defined to create a book')
        super().create(commit)

    @property
    def checkout_history(self):
        return checkouts.Checkouts(self.db, book_id=self.id)

    @property
    def outto(self):
        '''
        Thm member this book is out to, if any. If there are multiple
        members... probably not great
        '''
        return ' '.join(members.Member(self.db, x.member_id).full_name
                        for x in self.checkout_history.out)

    @property
    def out(self):
        return len(self.checkout_history.out) > 0

    @property
    def circulating(self):
        return self.shelfcode.code_type == 'C'

    def checkout(self, member, date=None):
        '''
        Check out this book

        Parameters
        ----------
        member : Member object
            The member to check this book out to.
        date : date, optional
            Date to check it out on. Default is now

        Raises
        ------
        CirculationException
            Raised when trying to check out a book that is already out.
        '''
        if date is None:
            date = datetime.datetime.now()
        if self.out:
            raise exceptions.CirculationException(
                'Book already checked out to ' + str(self.outto))
        c = checkouts.Checkout(self.db, None, member_id=member.id,
                               checkout_stamp=date, book_id=self.id)
        c.create()
        return c

    def withdraw(self):
        self.withdrawn = True

    def __str__(self):
        return '%s<%s<%s<%s' % (
            self.title.authortxt, self.title.titletxt, self.title.seriestxt,
            self.shelfcode)

    def str_pretty(self):
        '''
        returns the first few characters of each section for a fixed width
        display
        '''
        return [
            self.title.authortxt[:20],
            self.title.titletxt[:12],
            str(self.shelfcode).ljust(5)
            ]

    def __repr__(self):
        return '#%d:%d %s' % (
            self.title.title_id, self.id, str(self))

    def __eq__(self, other):
        return self.id == other.id