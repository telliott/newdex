#!/usr/bin/python
'''

code for manipulating pinkdexen stored in postgres databases

'''

import datetime
import difflib
import itertools
import os
import re
import warnings
import copy

import psycopg2

from mitsfs import barcode
from mitsfs import constants
from mitsfs import db
from mitsfs import dexfile
from mitsfs import lock_file
from mitsfs import membership
from mitsfs import utils
from mitsfs.dex.shelfcodes import Shelfcodes
from mitsfs.dex.editions import Edition, Editions, InvalidShelfcode
from mitsfs.dex.coercers import coerce_shelfcode, uncoerce_shelfcode
from mitsfs.dex.checkouts import Checkouts, Checkout

# if we ever switch away from postgres, we may need to export a different
# exception type as DataError
from psycopg2 import DataError
from io import open


__all__ = [
    'DexDB', 'Ambiguity', 'dg', 'Book', 'Title', 'CirculationException',
    'DataError',
    ]


# hacktackular!
gensym_seed = itertools.count()


def gensym():
    return ('G%04d' % next(gensym_seed))


NOTERE = re.compile(r'(.*)\((.*)\)')


class Ambiguity(Exception):
    pass


class CirculationException(Exception):
    pass


def notesplit(s):
    if s[-1] == ')':
        m = NOTERE.match(s)
        if m:
            name, note = m.groups()
            return name.strip(), note.strip()
    return s, ''


class Series(db.Entry):
    def __init__(self, db, series_id=None, **kw):
        super(Series, self).__init__(
            'series', 'series_id', db, series_id, **kw)

    created = db.ReadField('series_created')
    created_by = db.ReadField('series_created_by')
    created_with = db.ReadField('series_created_with')
    modified = db.ReadField('series_modified')
    modified_by = db.ReadField('series_modified_by')
    modified_with = db.ReadField('series_modified_with')
    name = db.Field('series_name')
    comment = db.Field('series_comment')

    def __len__(self):
        c = self.db.getcursor()
        c.execute(
            'select count(title_id)' +
            ' from title' +
            '  natural join title_series' +
            '  natural join series' +
            ' where series_id=%s',
            (self.id,))
        return c.fetchone()[0]

    def __iter__(self):
        # sort this properly 'cus it's convenient
        c = self.db.getcursor()
        c.execute(
            'select title_id' +
            ' from title' +
            '  natural join title_responsibility natural join entity' +
            '  natural join title_title' +
            '  natural join title_series' +
            '  natural join series' +
            ' where order_responsibility_by = 0 and order_title_by = 0' +
            '  and series_id = %s' +
            ' order by upper(entity_name), upper(title_name)',
            (self.id,))
        if c.rowcount == 0:
            return []

        return [Title(self.db, x[0]) for x in c.fetchall()]


class Book(db.Entry):
    def __init__(self, title, book_id):
        super(Book, self).__init__('book', 'book_id', title.dex, book_id)
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
        'shelfcode_id', coercer=coerce_shelfcode,
        prep_for_write=uncoerce_shelfcode)

    @property
    def barcodes(self):
        return tuple(self.cursor.execute(
            'select barcode from barcode'
            ' where book_id=%s order by barcode_created',
            (self.book_id,)))

    def addbarcode(self, in_barcode):
        in_barcode = barcode.valifrob(in_barcode)
        if in_barcode:
            try:
                self.cursor.execute(
                    'insert into barcode(book_id, barcode) values (%s,%s)',
                    (self.book_id, in_barcode))
                self.db.commit()
                return True
            except psycopg2.IntegrityError:
                self.db.rollback()
                return False
        else:
            return False

    @property
    def checkouts(self):
        return Checkouts(self.db, book_id=self.id)

    @property
    def outto(self):
        return ' '.join(str(x.member) for x in self.checkouts)

    @property
    def out(self):
        return self.cursor.execute(
            'select checkout_id from checkout'
            ' where book_id=%s and checkin_stamp is null',
            (self.id,)).rowcount > 0

    @property
    def circulating(self):
        return self.shelfcode.code_type == 'C'

    def checkout(self, member, date=None):
        if date is None:
            date = datetime.datetime.now()
        with self.getcursor() as c:
            if self.out:
                raise CirculationException(
                    'Book already checked out to ' + str(self.outto))
            c = Checkout(self.db, None, member_id=member.id,
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


class SeriesIndex(object):
    def __init__(self, dex):
        self.dex = dex

    def iterkeys(self):
        c = self.dex.getcursor()
        return c.execute(
            'select distinct upper(series_name)'
            ' from series'
            '  natural join title_series'
            '  natural join title'
            '  natural join book'
            ' where not withdrawn order by upper(series_name)')

    def complete(self, s):
        c = self.dex.getcursor()
        return c.execute(
            'select series_name from series'
            ' where position(%s in upper(series_name)) = 1'
            ' order by series_name',
            (s.strip().upper(),))

    def __getitem__(self, key):
        c = self.dex.getcursor()
        # sort this properly 'cus it's convenient
        return (
            Title(self.dex, title_id)
            for title_id
            in c.execute(
                'select title_id' +
                ' from title' +
                '  natural join title_responsibility natural join entity' +
                '  natural join title_title' +
                '  natural join title_series' +
                '  natural join series' +
                ' where order_responsibility_by = 0 and order_title_by = 0' +
                '  and upper(series_name) = upper(%s)' +
                ' order by upper(entity_name), upper(title_name)',
                (key,)))


class TitleIndex(object):
    def __init__(self, dex):
        self.dex = dex

    def iterkeys(self):
        c = self.dex.getcursor()
        # XXX rewrite to be clearer about join conditions
        return c.execute(
            "select t2.title_name || '=' || t1.title_name"
            "  from"
            "   title_title t1,"
            "   title_title t2"
            "  where"
            "   t1.order_title_by = 0 and"
            "   t1.title_type='=' and"
            "   t1.title_id = t2.title_id and"
            "   t2.order_title_by = 1"
            " union select t1.title_name"
            "   from title_title t1"
            "   left join title_title t2 on"
            "    t1.title_id = t2.title_id and"
            "    t2.order_title_by = 1"
            "  where"
            "   t1.order_title_by = 0 and"
            "   t1.title_type!='='"
            " union select t2.title_name"
            "  from"
            "   title_title t1,"
            "   title_title t2"
            "  where"
            "   t1.order_title_by = 0 and"
            "   t1.title_type!='=' and"
            "   t1.title_id = t2.title_id and"
            "   t2.order_title_by = 1"
            " union select title_name"
            "  from title_title"
            "  where order_title_by > 1")

    def search(self, author):
        c = self.dex.getcursor()
        l, a = len(author), author
        # XXX rewrite to be clearer about join conditions
        return c.execute(
            "select t2.title_name || '=' || t1.title_name"
            "  from"
            "   title_title t1,"
            "   title_title t2,"
            "   title_responsibility r"
            "   natural join entity"
            "  where"
            "   t1.order_title_by = 0 and"
            "   t1.title_type='=' and"
            "   t1.title_id = t2.title_id and"
            "   t2.order_title_by = 1 and"
            "   t1.title_id = r.title_id and"
            "   length(entity_name)>=%s and"
            "   upper(substring(entity_name from 1 for %s)) = upper(%s)"
            " union select t1.title_name"
            "  from"
            "   title_title t1"
            "   left join title_title t2 on"
            "    t1.title_id = t2.title_id and"
            "    t2.order_title_by = 1,"
            "   title_responsibility r"
            "   natural join entity"
            "  where"
            "   t1.order_title_by = 0 and"
            "   t1.title_type!='=' and"
            "   t1.title_id = r.title_id and"
            "   length(entity_name)>=%s and"
            "   upper(substring(entity_name from 1 for %s)) = upper(%s)"
            " union select t2.title_name"
            "  from"
            "   title_title t1,"
            "   title_title t2,"
            "   title_responsibility r"
            "   natural join entity"
            "  where"
            "   t1.order_title_by = 0 and"
            "   t1.title_type!='=' and"
            "   t1.title_id = t2.title_id and"
            "   t2.order_title_by = 1 and"
            "   t1.title_id = r.title_id and"
            "   length(entity_name)>=%s and"
            "   upper(substring(entity_name from 1 for %s)) = upper(%s)"
            " union select title_name"
            "  from"
            "   title_title t1,"
            "   title_responsibility r"
            "   natural join entity"
            "  where"
            "   order_title_by > 1 and"
            "   t1.title_id = r.title_id and"
            "   length(entity_name)>=%s and"
            "   upper(substring(entity_name from 1 for %s)) = upper(%s)",
            (l, l, a, l, l, a, l, l, a, l, l, a))

    def complete(self, title, author=''):
        c = self.dex.getcursor()
        # XXX rewrite to be clearer about join conditions
        return (i for i in c.execute(
            "select t2.title_name || '=' || t1.title_name"
            "  from"
            "   title_title t1,"
            "   title_title t2,"
            "   title_responsibility r"
            "   natural join entity"
            "  where"
            "   t1.order_title_by = 0 and"
            "   t1.title_type='=' and"
            "   t1.title_id = t2.title_id and"
            "   t2.order_title_by = 1 and"
            "   t1.title_id = r.title_id and"
            "   position(upper(%s) in upper(entity_name)) = 1 and"
            "   position(upper(%s)"
            "    in upper(t2.title_name || '=' || t1.title_name)) = 1"
            " union select t1.title_name"
            "  from"
            "   title_title t1"
            "   left join title_title t2 on"
            "    t1.title_id = t2.title_id and"
            "    t2.order_title_by = 1,"
            "   title_responsibility r"
            "   natural join entity"
            "  where t1.order_title_by = 0 and"
            "   t1.title_type!='=' and"
            "   t1.title_id = r.title_id and"
            "   position(upper(%s) in upper(entity_name)) = 1 and"
            "   position(upper(%s) in upper(t1.title_name)) = 1"
            " union select t2.title_name"
            "  from"
            "   title_title t1,"
            "   title_title t2,"
            "   title_responsibility r"
            "   natural join entity"
            "  where t1.order_title_by = 0 and"
            "   t1.title_type!='=' and"
            "   t1.title_id = t2.title_id and"
            "   t2.order_title_by = 1 and"
            "   t1.title_id = r.title_id and"
            "   position(upper(%s) in upper(entity_name)) = 1 and"
            "   position(upper(%s) in upper(t2.title_name)) = 1"
            " union select title_name"
            "  from"
            "   title_title t1,"
            "   title_responsibility r"
            "   natural join entity"
            "  where"
            "   order_title_by > 1 and"
            "   t1.title_id = r.title_id and"
            "   position(upper(%s) in upper(entity_name)) = 1 and"
            "   position(upper(%s) in upper(title_name)) = 1",
            (author, title, author, title, author, title, author, title)))

    def complete_checkedout(self, title, author=''):
        c = self.dex.getcursor()
        # XXX rewrite to be clearer about join conditions
        return (i for i in c.execute(
            "with tt as ("
            " select *"
            "   from title_title"
            "  where"
            "   title_id in ("
            "    select title_id"
            "     from"
            "      title_title"
            "      natural join book"
            "      natural join checkout"
            "     where"
            "      checkin_stamp is null"
            "     group by title_id))"
            " select t2.title_name || '=' || t1.title_name"
            "  from"
            "   tt t1,"
            "   tt t2,"
            "   title_responsibility r"
            "   natural join entity"
            "  where"
            "   t1.order_title_by = 0 and"
            "   t1.title_type='=' and"
            "   t1.title_id = t2.title_id and"
            "   t2.order_title_by = 1 and"
            "   t1.title_id = r.title_id and"
            "   position(upper(%s) in upper(entity_name)) = 1 and"
            "   position(upper(%s) in"
            "    upper(t2.title_name || '=' || t1.title_name)) = 1"
            " union select t1.title_name"
            "  from"
            "   tt t1"
            "   left join tt t2 on"
            "    t1.title_id = t2.title_id and"
            "    t2.order_title_by = 1,"
            "   title_responsibility r"
            "   natural join entity"
            "  where"
            "   t1.order_title_by = 0 and"
            "   t1.title_type!='=' and"
            "   t1.title_id = r.title_id and"
            "   position(upper(%s) in upper(entity_name)) = 1 and"
            "   position(upper(%s) in upper(t1.title_name)) = 1"
            " union select t2.title_name"
            "  from"
            "   tt t1,"
            "   tt t2,"
            "   title_responsibility r"
            "   natural join entity"
            "  where"
            "   t1.order_title_by = 0 and"
            "   t1.title_type!='=' and"
            "   t1.title_id = t2.title_id and"
            "   t2.order_title_by = 1 and"
            "   t1.title_id = r.title_id and"
            "   position(upper(%s) in upper(entity_name)) = 1 and"
            "   position(upper(%s) in upper(t2.title_name)) = 1"
            " union select title_name"
            "  from"
            "   tt t1,"
            "   title_responsibility r"
            "   natural join entity"
            " where"
            "  order_title_by > 1 and"
            "  t1.title_id = r.title_id and"
            "  position(upper(%s) in upper(entity_name)) = 1 and"
            "  position(upper(%s) in upper(title_name)) = 1",
            (author, title, author, title, author, title, author, title)))

    def __getitem__(self, key):
        c = self.dex.getcursor()
        if '=' in key:
            name, sortby = key.split('=')
            args = (sortby, name)
            # XXX rewrite to be clearer about join conditions
            q = (
                "select distinct t1.title_id"
                " from"
                "  title_title t1,"
                "  title_title t2"
                " where"
                "  t1.title_type='=' and"
                "  t1.order_title_by=0 and"
                "  t1.title_name=%s and"
                "  t1.title_id = t2.title_id and"
                "  t2.order_title_by=1 and"
                "  t2.title_name=%s"
                )
        else:
            q = (
                'select distinct title_id'
                ' from title_title'
                ' where'
                '  upper(title_name) = upper(%s)'
                )
            args = (key,)
        return (
            Title(self.dex, title_id)
            for title_id
            in c.execute(q, args))


class AuthorIndex(object):
    def __init__(self, dex):
        self.dex = dex

    def iterkeys(self):
        c = self.dex.getcursor()

        def notify(name, note):
            if note:
                return name + ' ' + note  # XXX is this right?
            else:
                return name

        return (
            notify(name, note)
            for (name, note)
            in c.execute(
                'select entity_name, entity_note'
                ' from entity'
                ' order by upper(entity_name), upper(entity_note)'))

    def __getitem__(self, key):
        c = self.dex.getcursor()
        return (
            Title(self.dex, title_id)
            for title_id
            in c.execute(
                'select distinct title_id'
                ' from title_responsibility'
                '  natural join entity'
                ' where'
                '  upper(entity_name) = upper(%s)',
                (key,)))

    def complete(self, key):
        c = self.dex.getcursor()
        return (i for i in c.execute(
            'select entity_name'
            ' from entity'
            ' where position(upper(%s) in upper(entity_name)) = 1',
            (key,)))

    def complete_checkedout(self, key):
        c = self.dex.getcursor()
        return (i for i in c.execute(
            'select entity_name'
            ' from'
            '  entity'
            '  natural join title_responsibility'
            '  natural join book'
            '  natural join checkout'
            ' where'
            '  checkin_stamp is null and'
            '  position(upper(%s) in upper(entity_name)) = 1',
            (key,)))


class CodeIndex(object):
    def __init__(self, dex):
        self.dex = dex

    def iterkeys(self):
        c = self.dex.getcursor()
        return (
            code + (doublecrap or '')
            for code, doublecrap
            in c.execute(
                'select distinct shelfcode, doublecrap'
                ' from book natural join shelfcode'))

    def __getitem__(self, key):
        c = self.dex.getcursor()
        try:
            e = Edition(key)
            code = e.code
            doublecrap = e.double_info
        except InvalidShelfcode:
            code, doublecrap = key, None
        # sort this properly 'cus we sort of need it
        q = (
            'select title_id'
            ' from title'
            '  natural join title_responsibility natural join entity'
            '  natural join title_title'
            '  natural join book'
            '  natural join shelfcode'
            ' where order_responsibility_by = 0 and order_title_by = 0'
            '  and upper(shelfcode) = upper(%s)'
            )
        a = [code]
        if doublecrap:
            q += ' and upper(doublecrap) = upper(%s)'
            a += [doublecrap]
        q += ' order by upper(entity_name), upper(title_name)'
        return (
            Title(self.dex, title_id)
            for title_id
            in c.execute(q, a))


class DexDB(db.Database):
    codere = None

    def __init__(
            self, client='mitsfs.dexdb',
            dsn=os.environ.get('MITSFS_DSN') or constants.DATABASE_DSN
            ):
        super(DexDB, self).__init__(client=client, dsn=dsn)
        self.filename = self.dsn
        self.indices = utils.PropDict(
            series=SeriesIndex(self),
            titles=TitleIndex(self),
            authors=AuthorIndex(self),
            codes=CodeIndex(self))
        self.shelfcodes = Shelfcodes(self)

    def xsearch(self, ops, conjunction='and'):
        fields = {
            'title': (
                '$1.title_name',
                'join title_title $1 using(title_id)',
                '$1.order_title_by = %s'),
            'author': (
                '$2.entity_name',
                'join title_responsibility $1 using(title_id)'
                ' join entity $2 on $1.entity_id = $2.entity_id',
                '$1.order_responsibility_by = %s'),
            'series': (
                '$2.series_name',
                'left join title_series $1 using(title_id)'
                ' left join series $2 on $1.series_id = $2.series_id',
                '$1.order_series_by = %s'),
            'shelfcode': (
                '$2.shelfcode',
                'join book $1 using(title_id)'
                ' join shelfcode $2 on $1.shelfcode_id = $2.shelfcode_id',
                None),
            }
        optmpls = {
            '=': 'upper(%s) = upper(%%s)',
            'in': 'position(upper(%%s) in upper(%s)) != 0',
            'startswith': 'position(upper(%%s) in upper(%s)) = 1',
            '~': '%s ~* %%s',
            }

        t = ''  # tables
        p = []  # predicates
        a = []  # args

        for op in ops:
            field, op, val = op[:3]
            if field in fields:
                string, join, subscript = fields[field]
                syms = {}

                def subst(s):
                    return re.sub(
                        r'\$\d',
                        lambda m: syms.setdefault(m.group(), gensym()),
                        s)

                t += ' ' + subst(join)
                p += [optmpls[op] % subst(string)]
                a += [val]

        c = self.getcursor()
        return (Title(self, i)
                for (i, author1, title1)
                in c.execute(
                    'select'
                    '  distinct title_id,'
                    '  entity.entity_name,'
                    '  title_title.title_name'
                    ' from'
                    '  title_responsibility'
                    '  natural join entity'
                    '  natural join title_title ' +
                    t +
                    ' where'
                    '  title_responsibility.order_responsibility_by = 0 and'
                    '  title_title.order_title_by = 0 and'
                    ' (' + (' %s ' % conjunction.strip()).join(p) + ')'
                    ' order by entity.entity_name, title_title.title_name',
                    a))

    def grep(self, s):
        pats = [i or None for i in re.split(r'[<`]', s)]

        if not pats:
            return []

        if len(pats) == 1 and pats[0][0] != '^':
            # patterns anchored at the other end will produce weird results.
            # I can't think of a reason to do that, and it won't do what
            # anyone will expect anyway, so....
            return self.xsearch(
                [(field, '~', pats[0])
                 for field in ['author', 'title', 'series']],
                'or')
        else:
            search = [
                (field, '~', pat)
                for (field, pat)
                in zip(['author', 'title', 'series'], pats)
                if pat]
            if len(pats) == 4 and pats[3]:
                search += [
                    ('shelfcode', '=', code.strip())
                    for code in pats[3].split(',')]
            return self.xsearch(search, 'and')

    def barcode(self, code):
        code = barcode.valifrob(code)
        if code:
            try:
                ((title_id, book_id),) = self.cursor.execute(
                    'select title_id, book_id'
                    ' from'
                    '  barcode'
                    '  natural join book'
                    ' where barcode=%s',
                    (code,))
            except ValueError:
                return None
        else:
            return None
        return Book(Title(self, title_id), book_id)

    def exdex(self, c, callback=lambda: None):
        authors = {}
        for (title_id, responsibility_type, entity_name) in c.execute(
                'select title_id, responsibility_type, entity_name'
                ' from'
                '  title_responsibility'
                '  natural join entity'
                '  order by title_id, order_responsibility_by'):
            authors.setdefault(title_id, []).append(
                (responsibility_type, entity_name))

        titles = {}
        for (title_id, title_type, title_name) in c.execute(
                'select title_id, title_type, title_name'
                ' from title_title'
                ' order by title_id, order_title_by'):
            titles.setdefault(title_id, []).append((title_type, title_name))

        series = {}
        for (
            title_id, series_name, series_index,
            series_visible, number_visible) in c.execute(
                'select'
                ' title_id, series_name, series_index,'
                ' series_visible, number_visible'
                ' from'
                '  title_series'
                '  natural join series'
                ' order by title_id, order_series_by'):
            series.setdefault(title_id, []).append(
                (series_name, series_index, series_visible, number_visible))

        codes = {}
        for (title_id, code, doublecrap, series_visible, count) in c.execute(
                'select'
                '  title_id, shelfcode, doublecrap,'
                '  book_series_visible, count(shelfcode)'
                ' from'
                '  book'
                ' natural join shelfcode'
                ' where not withdrawn'
                ' group by title_id, shelfcode, doublecrap,'
                '  book_series_visible'):
            codes.setdefault(title_id, []).append(
                (('@' if series_visible else '') + code + (doublecrap or ''),
                 count))

        d = dexfile.Dex()
        count = 0
        for title_id in codes.keys():
            line = dexfile.DexLine(
                authors=deeq(authors[title_id]),
                titles=deeq(titles[title_id]),
                series=[
                    ('@' if series_visible else '') +
                    series_name +
                    (' ' + ('#' if number_visible else '') + series_index
                        if series_index else '')
                    for (
                        series_name, series_index,
                        series_visible, number_visible)
                    in series.get(title_id, '')],
                codes=codes[title_id])
            d.add(line)
            count += 1
            if (count % 1000) == 0:
                callback()
        return d

    def save(self):
        # XXX
        if os.uname()[1] != 'monolith':
            raise Exception('Not saving, wrong machine')

        try:
            linkpath = os.readlink(constants.DATADEX_FILE)
            olddex = os.path.basename(linkpath)
        except OSError:
            olddex = None
        old_dexen = [
            (re.match(r'^datadex\.(\d+)$', i), i)
            for i in os.listdir(constants.DEXBASE)
            if i != olddex]
        old_dex_serials = [(int(m.group(1)), i) for (m, i) in old_dexen if m]
        old_dex_serials.sort()
        # remove all but the last two dexes not currently pointed to

        for (n, i) in old_dex_serials[:-2]:
            os.unlink(os.path.join(constants.DEXBASE, i))

        self.db.commit()  # make sure we're in a new transaction
        c = self.getcursor()
        (generation,) = c.execute("select last_value from log_generation_seq")
        target = constants.DATADEX_FILE + ('.%d' % generation)
        if os.path.exists(target):  # a copy of this datadex already exists
            return False

        d = self.exdex(c)

        lock = lock_file.LockFile(constants.DATADEX_FILE)
        try:
            d.save(target)
            if not os.path.exists(constants.DATADEX_FILE):
                prevgeneration = 0
            elif os.path.islink(constants.DATADEX_FILE):
                try:
                    old = os.readlink(constants.DATADEX_FILE)
                    prevgeneration = int(old.split('.')[-1])
                except (IOError, ValueError):
                    prevgeneration = 0
                try:
                    os.unlink(constants.DATADEX_FILE)
                except IOError:
                    pass
            else:
                prevgeneration = 0
                os.rename(
                    constants.DATADEX_FILE,
                    constants.DATADEX_FILE + '.' + utils.timestamp())
            os.symlink(target, constants.DATADEX_FILE)
            fp = open(
                os.path.join(
                    constants.DEXBASE, 'dblogs', 'delta.%d' % generation),
                'w')
            first = True
            for entry in c.execute(
                    'select * from log where generation > %s',
                    (prevgeneration,)):
                if first:
                    fp.write(len(entry + "\n"))
                    first = False
                for i in entry:
                    fp.write(i + "\n")
            fp.close()
        finally:
            lock.unlock()
        return (old, target)

    def sortcode(self, code):
        pass

    modified = False

    # iterate (over the whole dex)
    def iter(self, q=None, a=(), c=None, constructor=None):
        if constructor is None:
            constructor = Title
        if c is None:
            c = self.getcursor()
        if not q:
            q = (
                'select title_id'
                ' from title'
                '  natural join title_responsibility natural join entity'
                '  natural join title_title'
                ' where order_responsibility_by = 0 and order_title_by = 0'
                ' order by upper(entity_name), upper(title_name)')
        c.execute(q, a)
        return (constructor(self, title_id) for title_id in c)

    def pinkdex(self, q='', a=(), limit=None, c=None):
        if c is None:
            c = self.getcursor()
        q = (
            'select pinkdex.*'
            ' from pinkdex ' +
            q +
            ' order by upper(authors[0]), upper(titles[0])'
            )
        if limit is not None:
            q += ' limit ' + limit
        c.execute(q, a)
        fields = utils.PropDict(
            reversed(x)
            for x in enumerate(
                column[0]
                for column in c.description))
        for row in c:
            yield utils.PropDict(
                title_id=row[fields.title_id],
                responsibility=[
                    utils.PropDict(list(zip(
                        ['entity', 'entity_id', 'type'],
                        subrow[1:])))
                    for subrow
                    in sorted(zip(
                        row[fields.order_responsibility_bys],
                        row[fields.authors],
                        row[fields.entity_ids],
                        row[fields.responsibility_types]),
                        key=lambda x: x[0])],
                title=[
                    utils.PropDict(list(zip(['title', 'type'], subrow[1:])))
                    for subrow
                    in sorted(zip(
                        row[fields.order_title_bys],
                        row[fields.titles],
                        row[fields.title_types]),
                        key=lambda x: x[0])],
                series=(
                    [
                        utils.PropDict(
                            list(zip([
                                'series', 'index', 'visible',
                                'number', 'series_id'],
                                subrow[1:])))
                        for subrow
                        in sorted(zip(
                            row[fields.order_series_bys],
                            row[fields.series],
                            row[fields.series_indexes],
                            row[fields.series_visibles],
                            row[fields.number_visibles],
                            row[fields.series_ids]),
                            key=lambda x: x[0])
                        ] if row[fields.series] is not None else []),
                books=[
                    utils.PropDict(
                        list(zip(['code', 'shelfcode_id', 'type', 'count'],
                                 subrow)))
                    for subrow
                    in (
                        k + (len(list(g)),)
                        for (k, g)
                        in itertools.groupby(
                            sorted(list(zip(
                                row[fields.shelfcodes],
                                row[fields.shelfcode_ids],
                                row[fields.shelfcode_types])))))]
                )

    def __iter__(self):
        return self.iter()

    def search(self, author, titlename):
        c = self.getcursor()
        ps = []
        ts = ''
        args = []
        for (sortby, name) in uneq(author.split('|')):
            t_r = gensym()
            ent = gensym()
            ts += (
                (' join %s using (title_id)' if ts else '%s') % (
                    'title_responsibility %s natural join entity %s' % (
                        t_r, ent),))
            ps.append(
                "%s.responsibility_type %s '=' and"
                " position(upper(%%s) in upper(%s.entity_name)) " %
                (t_r, ('=' if sortby else '!='), ent) +
                ('!= 0' if name[0] == '-' else '= 1'))
            args.append(name if name[0] != '-' else name[1:])
        for (sortby, name) in uneq(titlename.split('|')):
            ttl = gensym()
            ts += (
                (' join %s using (title_id)' if ts else '%s') %
                ('title_title %s' % ttl,))
            ps.append(
                "%s.title_type %s '=' and"
                " position(upper(%%s) in upper(%s.title_name)) " %
                (ttl, ('=' if sortby else '!='), ttl) +
                ('!= 0' if name[0] == '-' else '= 1'))
            args.append(name if name[0] != '-' else name[1:])
        q = (
            'select distinct title_id from ' + ts +
            ' where ' + ' and '.join(ps))

        return sorted(
            (Title(self, title_id) for title_id in c.execute(q, args)),
            key=lambda x: x.sortkey())

    def titlesearch(self, frag):
        c = self.getcursor()
        return (
            Title(self, title_id) for title_id in
            c.execute(
                "select distinct title_id"
                " from title_title"
                " where"
                "  length(title_name) >= %s and"
                "  upper(substring(title_name from 1 for %s)) = upper(%s)",
                (len(frag), len(frag), frag)))

    def get(self, key):
        c = self.cursor
        if hasattr(key, 'title_id'):
            (count,) = tuple(c.execute(
                'select count(title_id) from title where title_id=%s',
                (key.title_id,)))
            if count:
                return Title(self, key.title_id)
            else:
                raise KeyError('No such title_id %d', key.title_id)
        if hasattr(key, 'authors') and hasattr(key, 'titles'):
            authors, titles = key.authors, key.titles
        else:
            authors, titles = [i.split('|') for i in key.split('<')][:2]
        # do this the kludgy but easy way
        asortby, tsortby = None, None
        if '=' in authors[0]:
            author, asortby = authors[0].split('=')
            authors = [asortby, author] + list(authors[1:])
        if '=' in titles[0]:
            name, tsortby = titles[0].split('=')
            titles = [tsortby, name] + list(titles[1:])
        candidates = set()

        for index, name in enumerate(authors):
            subcands = set(c.execute(
                "select title_id"
                " from"
                "  title_responsibility"
                "  natural join entity"
                " where"
                "  upper(entity_name) = upper(%s) and"
                "  order_responsibility_by = %s" +
                (" and responsibility_type = '='"
                 if asortby and index == 0
                 else ''),
                (name, index)))
            if not subcands:
                return None
            if index == 0:
                candidates = subcands
            else:
                candidates &= subcands
        for index, name in enumerate(titles):
            subcands = set(c.execute(
                "select title_id"
                " from title_title"
                " where"
                "  title_name = %s and"
                "  order_title_by = %s" +
                (" and title_type = '='" if tsortby and index == 0 else ''),
                (name, index)))
            if not subcands:
                return None
            candidates &= subcands
        for check in list(candidates):
            if (list(c.execute(
                "select title_id"
                " from title_responsibility"
                " where"
                "  title_id = %s and"
                "  order_responsibility_by >= %s", (check, len(authors)))) or
                list(c.execute(
                    "select title_id"
                    " from title_title"
                    " where"
                    "  title_id = %s and"
                    "  order_title_by >= %s", (check, len(titles))))):
                candidates.remove(check)
        assert len(candidates) < 2, 'database key ambiguity %s' % repr(key)
        if candidates:
            return Title(self, candidates.pop())
        else:
            return None

    def __getitem__(self, key):
        got = self.get(key)
        if got is None:
            raise KeyError(key)
        return got

    def __contains__(self, key):
        return self.get(key) is not None

    def get_entity(self, name, c=None):
        if c is None:
            c = self.cursor
        c.execute(
            "select entity_id"
            " from entity"
            " where upper(entity_name) = upper(%s)", (name,))
        if c.rowcount == 0:
            c.execute(
                "insert into entity(entity_name, entity_type)"
                " values (%s, %s)",
                (name.upper(), '?'))
            c.execute('select last_value from id_seq')
        (entity_id,) = c.fetchone()
        return entity_id

    def get_series(self, name, c=None):
        if c is None:
            c = self.cursor

        c.execute(
                "select series_id"
                " from series"
                " where upper(series_name) = upper(%s)",
                (name,))
        if c.rowcount == 0:
            c.execute(
                "insert into series(series_name) values (%s)",
                (name.upper(),))
            c.execute("select last_value from id_seq")
        (series_id,) = c.fetchone()
        return series_id

    def series(self, name=None):
        c = self.cursor
        if name is None:
            return Series(self)  # initializea new series
        if not c.execute(
                "select series_id"
                " from series"
                " where upper(series_name) = %s",
                (name.upper().strip(),)):
            return None  # not found
        ((val,),) = c.fetchall()  # will raise in case of constraint violation
        return Series(self, val)

    def get_shelfcode(self, name, c=None):
        if c is None:
            c = self.cursor
        try:
            (code_id,) = list(c.execute(
                'select shelfcode_id from shelfcode where shelfcode=upper(%s)',
                (name,)))
        except ValueError:
            raise KeyError(name)
        return code_id

    def replace(self, line, replacement):
        victim = self[line]
        title_id = victim.title_id
        # now figure out what changed and fiddle it
        # we "know" that we don't have to worry about shelfcodes

        vdata = uneq(victim.authors)
        rdata = uneq(replacement.authors)

        off = 0
        for (i1, i2, j1, j2) in diff(vdata, rdata):
            delta = (j2 - j1) - (i2 - i1)
            if (i2 - i1) > 0:
                self.cursor.execute(
                    "delete from title_responsibility"
                    " where"
                    " title_id=%s and"
                    " order_responsibility_by >= %s and"
                    " order_responsibility_by < %s",
                    (title_id, i1 + off, i2 + off))
            self.cursor.execute(
                "update title_responsibility"
                " set order_responsibility_by = order_responsibility_by + %s"
                " where"
                "  title_id=%s and"
                "  order_responsibility_by >= %s",
                (delta, title_id, i2 + off))
            if (j2 - j1) > 0:
                self.cursor.executemany(
                    "insert into"
                    " title_responsibility"
                    "  (title_id,"
                    "   entity_id,"
                    "   order_responsibility_by,"
                    "   responsibility_type)"
                    " values (%s, %s, %s, %s)",
                    [(
                        title_id,
                        self.get_entity(name),
                        i1 + off + i,
                        '=' if sortby else '?'
                        )
                     for (i, (sortby, name)) in enumerate(rdata[j1:j2])])
            off += delta

        vdata = uneq(victim.titles)
        rdata = uneq(replacement.titles)

        off = 0
        for (i1, i2, j1, j2) in diff(vdata, rdata):
            delta = (j2 - j1) - (i2 - i1)
            if (i2 - i1) > 0:
                self.cursor.execute(
                    "delete from title_title"
                    " where"
                    "  title_id=%s and"
                    "  order_title_by >= %s and"
                    "   order_title_by < %s",
                    (title_id, i1 + off, i2 + off))
            self.cursor.execute(
                "update title_title"
                " set order_title_by = order_title_by + %s"
                " where"
                "  title_id=%s and"
                "  order_title_by >= %s",
                (delta, title_id, i2 + off))
            if (j2 - j1) > 0:
                self.cursor.executemany(
                    "insert into title_title"
                    "  (title_id, title_name, order_title_by, title_type)"
                    " values (%s, %s, %s, %s)",
                    [(title_id, name, i1 + off + i, '=' if sortby else 'T')
                     for (i, (sortby, name)) in enumerate(rdata[j1:j2])])
            off += delta

        vdata = victim.series
        rdata = replacement.series

        off = 0
        for (i1, i2, j1, j2) in diff(vdata, rdata):
            delta = (j2 - j1) - (i2 - i1)
            if (i2 - i1) > 0:
                self.cursor.execute(
                    "delete from title_series"
                    " where"
                    "  title_id=%s and"
                    "  order_series_by >= %s and"
                    "  order_series_by < %s",
                    (title_id, i1 + off, i2 + off))
            self.cursor.execute(
                "update title_series"
                " set order_series_by = order_series_by + %s"
                " where"
                "  title_id=%s and"
                "  order_series_by >= %s",
                (delta, title_id, i2 + off))
            if (j2 - j1) > 0:
                self.cursor.executemany(
                    "insert into title_series"
                    "  (title_id, series_id, series_index,"
                    "   order_series_by, series_visible, number_visible)"
                    " values (%s, %s, %s, %s, %s, %s)",
                    [(
                        title_id,
                        self.get_series(name),
                        index,
                        i1 + off + i,
                        series_visible,
                        number_visible
                        )
                     for (i, (name, index, series_visible, number_visible))
                     in enumerate(
                         munge_series(s) for s in rdata[j1:j2])])
            off += delta
        self.db.commit()

    def newtitle(self, authors, titles, series, c=None):
        '''authors, titles, series, [ c ] -> title
        DOES NOT COMMIT
        '''
        if c is None:
            c = self.cursor
        title_id = c.selectvalue(
            'insert into title default values returning title_id',
            (self.client, self.client))
        c.executemany(
            "insert into title_responsibility"
            "  (title_id, entity_id,"
            "   order_responsibility_by, responsibility_type)"
            " values (%s, %s, %s, %s)",
            [(title_id, self.get_entity(name, c), order, rtype)
             for (order, (rtype, name)) in enumerate(authors)])
        c.executemany(
            "insert into title_title"
            " (title_id, title_name, order_title_by, title_type)"
            " values (%s, %s, %s, %s)",
            [(title_id, name.upper(), order, ttype)
             for (order, (ttype, name)) in enumerate(titles)])
        c.executemany(
            "insert into title_series"
            " (title_id, series_id, series_index,"
            "  order_series_by, series_visible, number_visible)"
            " values (%s, %s, %s, %s, %s, %s)",
            [(
                title_id,
                self.get_series(name),
                index.upper() if index else None,
                order,
                series_visible,
                number_visible
                )
             for (order, (name, index, series_visible, number_visible))
             in enumerate(series)])
        return Title(self, title_id)

    def newbook(
            self, title_id, shelfcode, review=False, c=None, comment=None):
        '''title_id, shelfcode, [review], [c], [comment] -> book_id
        DOES NOT COMMIT'''
        if c is None:
            c = self.cursor
        e = Edition(shelfcode)
        return c.selectvalue(
            "insert into book"
            " (title_id, book_series_visible,"
            "  shelfcode_id, doublecrap, review, book_comment)"
            " values (%s, %s, %s, %s, %s, %s) returning book_id",
            (
                title_id, 't' if e.series_visible else 'f',
                self.shelfcodes[e.shelfcode].shelfcode_id, e.double_info,
                review, comment),
            )

    def add(self, line, review=False, lost=False, c=None, comment=None):
        if c is None:
            c = self.cursor
        victim = self.get(line)
        if victim:
            codes = line.codes
            removed = {}
            added = {}

            for edition in codes.values():
                if edition.count < 0:
                    new_edition = copy.deepcopy(edition)
                    new_edition.count = 0 - new_edition.count
                    removed[edition.shelfcode] = new_edition
                elif edition.count > 0:
                    added[edition.shelfcode] = edition

            if removed:
                if added and (len(added) > 1 or int(added) != int(removed)):
                    raise Ambiguity('Please try a simpler operation for now.')
                count = len(removed)

                q = 'update book set'
                a = []

                if added:
                    edition = added(list(added.keys())[0])
                    q += (' shelfcode_id=%s, doublecrap=%s,'
                          ' book_series_visible=%s')
                    a += [
                        self.shelfcodes[edition.code].shelfcode_id,
                        edition.double_info or None,
                        't' if edition.series_visible else 'f']
                else:
                    q += ' withdrawn=true'

                q += ' where book_id in ('

                for (i, edition) in enumerate(removed.values()):
                    if i:
                        q += ' union '
                    q += ("(select book_id"
                          " from"
                          "  book"
                          "  natural join shelfcode"
                          " where"
                          "  title_id=%s and"
                          "  shelfcode=%s and"
                          "  book_series_visible=%s")
                    a += [victim.title_id, edition.shelfcode,
                          edition.series_visible]

                    if edition.double_info:
                        q += ' and doublecrap=%s'
                        a += [edition.double_info]
                    else:
                        q += ' and doublecrap is null'

                    q += ' and not withdrawn limit %s)'
                    a += [count]

                q += ')'
                c.execute(q, a)
                if lost and not (line.codes + victim.codes):
                    c.execute(
                        "update title"
                        " set title_lost=true"
                        " where title_id=%s",
                        (victim.title_id,))
            else:  # added
                for edition in added.values():
                    for i in range(0, edition.count):
                        self.newbook(
                            victim.title_id, edition.shelfcode, review, c=c,
                            comment=comment)
        else:
            victim = self.newtitle(
                [('=' if eq else '?', name) for (eq, name)
                 in uneq(line.authors)],
                [('=' if eq else 'T', name) for (eq, name)
                 in uneq(line.titles)],
                [munge_series(i) for i in line.series])
            for edition in line.codes.values():
                for i in range(0, edition.count):
                    self.newbook(
                        victim.title_id, edition.shelfcode, review,
                        c=c, comment=comment)
        self.db.commit()

    def merge(self, d):
        for i in d:
            self.add(i)

    def stats(self):
        return dict(self.cursor.execute(
            "select distinct shelfcode, count(shelfcode)"
            " from"
            "  book"
            "  natural join shelfcode"
            " where not withdrawn"
            " group by shelfcode"))

    _codes = None

    @property
    def codes(self):
        if self._codes is None:
            self._codes = dict(
                (
                    shelfcode,
                    utils.PropDict(description=description, type=type, id=id)
                    )
                for (id, shelfcode, description, type)
                in self.cursor.execute(
                    "select"
                    "  shelfcode_id,"
                    "  shelfcode,"
                    "  shelfcode_description,"
                    "  shelfcode_type"
                    " from shelfcode"))
        return self._codes

    def membook(self):
        return membership.MembershipBook(self)


SERIESINDEX_RE = re.compile(r'(?: (#)?([-.,\d]+B?))?$')


def munge_series(name):
    'name -> name, index, series_visisble, number_visible'
    if not name:
        return None
    series_visible = name[0] == '@'
    if series_visible:
        name = name[1:]
    number_visible, index = SERIESINDEX_RE.search(name).groups()
    name = SERIESINDEX_RE.sub('', name)
    return name, index, series_visible, bool(number_visible)


def diff(a, b):
    return [
        (i1, i2, j1, j2)
        for (op, i1, i2, j1, j2)
        in difflib.SequenceMatcher(None, a, b).get_opcodes()
        if op != 'equal']


def uneq(tup):
    # this function has become a crawling horror of corner cases.  I
    # hope to be able to stop using it someday.
    if not tup:
        return []
    first = tup[0]
    rest = list(zip([False] * (len(tup) - 1), tup[1:]))
    if not first and not rest:
        return []
    if first[0] == '=':
        return [(True, first[1:])] + rest
    if '=' in first:
        return list(zip([True, False], reversed(first.split('=')))) + rest
    else:
        return [(False, first)] + rest


class Title(dexfile.DexLine, db.Entry):
    def __init__(self, dex, title_id):
        db.Entry.__init__(self, 'title', 'title_id', dex, title_id)
        self.title_id = title_id

    @property
    def dex(self):
        return self.db

    _queries = {
        'authors':
        "select"
        "  responsibility_type, entity_name, entity_note"
        " from"
        "  title_responsibility"
        "  natural join entity"
        " where title_id = %s"
        " order by order_responsibility_by",
        'titles':
        "select"
        "  title_type, title_name"
        " from title_title"
        " where title_id = %s"
        " order by order_title_by",
        'series':
        "select"
        "  series_name, series_index, series_visible, number_visible"
        " from"
        "  title_series"
        "  natural join series"
        " where title_id = %s"
        " order by order_series_by",
        'codes':
        "select"
        "  book_series_visible, shelfcode, doublecrap, count(shelfcode)"
        " from"
        "  book"
        "  natural join shelfcode"
        " where"
        "  title_id = %s and"
        "  not withdrawn"
        " group by book_series_visible, shelfcode, doublecrap"
        " order by not book_series_visible, shelfcode, doublecrap",
        }

    def _cache_query(self, query):
        name = 'Q_' + query
        if name in self.cache:
            return self.cache[name]

        ret = list(self.cursor.execute(self._queries[query], (self.title_id,)))

        self.cache[name] = ret

        return ret

    @property
    @db.cached
    def authors(self):
        those = [
            (rtype, name + (' (' + note + ')' if note else ''))
            for (rtype, name, note) in self._cache_query('authors')]
        rtype, entity = those[0]
        if rtype == '=':
            sortby = entity
            rtype, entity = those[1]
            those = [(rtype, entity + '=' + sortby)] + those[2:]
        those = [_entity for (_rtype, _entity) in those]
        return dexfile.FieldTuple(those)

    @property
    @db.cached
    def titles(self):
        those = self._cache_query('titles')
        these = []
        sortby = ''
        notes = []
        # oh, the horrorifying
        for i in range(1, len(those)):
            if those[i][0] == 'N':
                those[i], those[i - 1] = those[i - 1], those[i]
        for (ttype, name) in those:
            if ttype == '=':
                sortby = name
            elif ttype == 'N':
                notes.append('(' + name + ')')
            else:
                these.append(
                    name +
                    (' ' + ' '.join(notes) if notes else '') +
                    ('=' + sortby if sortby else ''))
        return dexfile.FieldTuple(these)

    @property
    @db.cached
    def books(self):
        cursor = self.cursor
        # why is the following a subselect?
        cursor.execute(
            "select distinct book_id"
            " from ("
            "  select book_id"
            "  from"
            "   book"
            "   natural left join barcode"
            "  where"
            "   title_id=%s and"
            "   not withdrawn"
            "  order by shelfcode_id, barcode)"
            " as q",
            (self.title_id, ))
        return [Book(self, i) for i in cursor]

    @property
    @db.cached
    def series(self):
        those = (
            ('@' if series_visible else '') +
            series_name +
            (' ' + ('#' if number_visible else '') + series_index
             if series_index else '')
            for series_name, series_index,
            series_visible, number_visible in self._cache_query('series'))
        return dexfile.FieldTuple(those)

    @property
    @db.cached
    def codes(self):
        return Editions(
            ','.join(
                ('@' if series_visible else '') +
                shelfcode +
                (doublecrap if doublecrap else '') +
                (':' + str(count)
                 if count > 1 else '')
                for series_visible, shelfcode,
                doublecrap, count in self._cache_query('codes')))

    def __str__(self):
        result = dexfile.DexLine.__str__(self)
        return result

    def __repr__(self):
        return '#' + str(self.title_id) + ' ' + repr(str(self))

    def __eq__(self, other):
        if hasattr(other, 'title_id') and other.title_id == self.title_id:
            return True
        else:
            return False

    def __hash__(self):
        return self.title_id

    @db.cached
    def shelfkey(self, shelfcode):
        author = self._cache_query('authors')[0][1]
        title = self._cache_query('titles')[0][1]

        doublecrap, book_series_visible = [
            (doublecrap, book_series_visible)
            for (book_series_visible, qshelfcode, doublecrap, count)
            in self._cache_query('codes')
            if qshelfcode == shelfcode][0]

        if doublecrap:
            key = [doublecrap, author]
        else:
            key = [author]

        series_q = self._cache_query('series')
        if series_q:
            series, series_index, series_visible, index_visible = series_q[0]
            if series_visible:
                key += [series]
                if index_visible:
                    key += [series_index]
        key += [title]
        return tuple(dexfile.placefilter(i).strip() for i in key)

    @db.cached
    def nicetitle(self):
        def titlecase(s):
            return re.sub(
                '\'([SDT]|Ll|Re)([^A-Z]|$)',
                lambda m: m.group(0).lower(),
                s.title())
        series = [
            titlecase(i.replace(',', r'\,'))
            for i in self.series if i]
        titles = [
            titlecase('=' in i and i[:i.find('=')] or i)
            for i in self.titles]  # strip the sortbys
        if series:
            if len(series) == len(titles):
                titles = ['%s [%s]' % i for i in zip(titles, series)]
            elif len(titles) == 1:
                titles = ['%s [%s]' % (titles[0], '|'.join(series))]
            elif len(series) == 1:
                titles = ['%s [%s]' % (i, series[0]) for i in titles]
            else:  # this is apparently Officially Weird
                ntitles = ['%s [%s]' % i for i in zip(titles, series)]
                if len(self.series) < len(titles):
                    ntitles += titles[len(series):]
                titles = ntitles
        return '|'.join(titles)

    def delete(self):
        c = self.cursor or self.dex.cursor
        c.execute(
            'delete from book where title_id=%s and withdrawn',
            (self.id,))
        c.execute(
            'delete from title_title where title_id=%s',
            (self.id,))
        c.execute(
            'delete from title_responsibility where title_id=%s',
            (self.id,))
        c.execute(
            'delete from title where title_id=%s',
            (self.id,))
        self.db.commit()

    @property
    def checkedout(self):
        # if any of this title are checked out
        c = self.cursor or self.dex.cursor
        c.execute(
            'select count(title_id)'
            ' from'
            '  checkout'
            '  natural join book'
            ' where'
            '  checkin_stamp is null and'
            '  title_id = %s',
            (self.id,))

        return c.fetchone()[0] > 0

    created = db.ReadField('title_created')
    created_by = db.ReadField('title_created_by')
    created_with = db.ReadField('title_created_with')
    modified = db.ReadField('title_modified')
    modified_by = db.ReadField('title_modified_by')
    modified_with = db.ReadField('title_modified_with')

    comment = db.Field('title_comment')
    lang = db.Field('lang')
    lost = db.Field('title_lost')


def dg(d, q):
    lines = [str(i) for i in d.grep(q)]
    for i in lines:
        print(i)
    return len(lines)


def deeq(e):
    t0, s0 = e[0]
    if t0 == '=':
        t1, s1 = e[1]
        e = [(t1, s1 + '=' + s0)] + e[2:]
    return [s for (t, s) in e]


# class Shelfcode(db.Entry):
#     def __init__(self, selector, db):
#         if selector is None:
#             raise KeyError('There is no non-shelfcode [go find libcomm]')
#         try:
#             shelfcode_id = int(selector)
#         except ValueError:
#             shelfcode_id = None
#         if shelfcode_id is None:
#             try:
#                 c = db.cursor.execute(
#                     'select shelfcode_id from shelfcode'
#                     ' where shelfcode=upper(%s)',
#                     (str(selector).strip(),))
#                 shelfcode_result = c.fetchone()
#                 shelfcode_id = shelfcode_result[0]
#             except ValueError:
#                 raise KeyError('No such shelfcode')

#         super(Shelfcode, self).__init__(
#             'shelfcode', 'shelfcode_id', db, shelfcode_id)

#     name = db.ReadField('shelfcode')
#     description = db.ReadField('shelfcode_description')
#     type = db.ReadField('shelfcode_type')
#     replacement_cost = db.ReadField('replacement_cost')

#     def __str__(self):
#         return self.name

#     @staticmethod
#     def list(db):
#         return db.cursor.execute('select shelfcode from shelfcode')

# This was previously part of the DexDB class, but has been replaced with a
# shelfcode object
# def load_shelfcodes(self, force=False):
#     ShelfcodeTuple = collections.namedtuple(
#         'Shelfcode',
#         ['description', 'type', 'cost', 'class_',
# 'doublecode', 'hassle'])

#     def process(t):
#         desc, type, cost, class_, double, hcount, hwith = t
#         return ShelfcodeTuple(
#             desc, type, cost, class_, double,
#             ((tuple(hwith), hcount) if type == 'C' else ()))
#     # XXX this should really be a dict of Shelfcode objects?
#     self.shelfcodes = {
#         x[0]: process(x[1:])
#         for x in self.getcursor().execute(
#             'select'
#             '  a.shelfcode, a.shelfcode_description, a.shelfcode_type,'
#             '  a.replacement_cost, a.shelfcode_class,'
#             '  a.shelfcode_doublecode, sc.shelfcode_class_hassle,'
#             '  array_agg(b.shelfcode)'
#             ' from'
#             '  shelfcode a'
#             '  natural join shelfcode_class sc'
#             '  join shelfcode b using(shelfcode_type, shelfcode_class)'
#             ' group by'
#             '  a.shelfcode, a.shelfcode_description, a.shelfcode_type,'
#             '  a.replacement_cost, a.shelfcode_class,'
#             '  a.shelfcode_doublecode, sc.shelfcode_class_hassle')}
#     if force or DexDB.codere is None:
#         # we reverse the double codes so that the longer ones
#         # with matching stems come first
#         # yeah, yeah, yea
#         dcodes = [
#             code for code in self.shelfcodes
#             if self.shelfcodes[code].doublecode]
#         ncodes = list(set(self.shelfcodes) - set(dcodes))
#         DexDB.codere = re.compile(
#             '^(@?)(?:(' +
#             '|'.join(ncodes) +
#             ')|(' +
#             '|'.join(reversed(sorted(dcodes))) +
#             r')([-A-Z]?[\d.]+))$'
#             )
