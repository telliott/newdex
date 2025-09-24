import datetime

from mitsfs.core import db
from mitsfs.util import coercers
from mitsfs import barcode
from mitsfs.circulation import checkouts
from mitsfs.circulation import members
from mitsfs.util import exceptions

class Book(db.Entry):
    def __init__(self, title, book_id):
        super(Book, self).__init__('book', 'book_id', title.db, book_id)
        self.__title = title
        self.book_id = book_id

    def __get_title(self):
        return self.__title

    def __set_title(self, title):
        assert hasattr(title, 'title_id')
        self.cursor.execute('update book set title_id=%s where book_id=%s',
                            (title.title_id, self.book_id))
        self.db.db.commit()
        self.__title = title

    title = property(__get_title, __set_title)

    created = db.ReadField('book_created')
    created_by = db.ReadField('book_created_by')
    created_with = db.ReadField('book_created_with')
    modified = db.ReadField('book_modified')
    modified_by = db.ReadField('book_modified_by')
    modified_with = db.ReadField('book_modified_with')

    visible = db.Field('book_series_visible')
    doublecrap = db.Field('doublecrap')
    review = db.Field('review')
    withdrawn = db.Field('withdrawn')

    comment = db.Field('book_comment')

    # Doing a little bit of hacking here to get a shelfcode object into place
    shelfcode = db.Field(
        'shelfcode_id', coercer=coercers.coerce_shelfcode,
        prep_for_write=coercers.uncoerce_shelfcode)

    @property
    def barcodes(self):
        return self.cursor.fetchlist(
            'select barcode from barcode'
            ' where book_id=%s order by barcode_created',
            (self.book_id,))

    def addbarcode(self, in_barcode):
        in_barcode = barcode.valifrob(in_barcode)
        if in_barcode:
            self.cursor.execute(
                'insert into barcode(book_id, barcode) values (%s,%s)',
                (self.book_id, in_barcode))
            self.db.commit()
            return True
        else:
            return False

    @property
    def checkouts(self):
        return checkouts.Checkouts(self.db, book_id=self.id)

    @property
    def outto(self):
        return ' '.join(str(members.Member(self.db, x.member_id))
                        for x in self.checkouts.out)

    @property
    def out(self):
        return len(self.checkouts.out) > 0

    @property
    def circulating(self):
        return self.shelfcode.code_type == 'C'

    def checkout(self, member, date=None):
        if date is None:
            date = datetime.datetime.now()
        with self.getcursor() as c:
            if self.out:
                raise exceptions.CirculationException(
                    'Book already checked out to ' + str(self.outto))
            c = checkouts.Checkout(self.db, None, member_id=member.id,
                                   checkout_stamp=date, book_id=self.book_id)
            c.create()
            return c

    def __str__(self):
        return '%s<%s<%s<%s<%s' % (
            self.title.authortxt, self.title.titletxt, self.title.seriestxt,
            self.shelfcode, '|'.join(self.barcodes))

    def str_pretty(self):
        return [
            self.title.authortxt[:20],
            self.title.titletxt[:12],
            str(self.shelfcode).ljust(5),
            '|'.join(self.barcodes)[:10],
            ]

    def __repr__(self):
        return '#%d:%d %s' % (
            self.title.title_id[0], self.book_id[0], str(self))

