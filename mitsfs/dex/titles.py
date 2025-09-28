import re

from mitsfs import dexfile
from mitsfs.core import db
from mitsfs import utils
from mitsfs.util import exceptions
from mitsfs.dex.editions import Editions
from mitsfs.dex.books import Book


# this class is tested in test_indexes.py
class Titles(object):
    def __init__(self, db):
        self.db = db

    def keys(self):
        '''
        Returns
        -------
        list(str)
            A list of all the titles we have in the dex.

        '''
        c = self.db.getcursor()
        return c.fetchlist("select CONCAT_WS('=', title_name, alternate_name)"
                           " from title_title")

    def search(self, title):
        '''
        Search titles for a given substring and return all the IDs that
        match

        Parameters
        ----------
        series : str
            a string to search for. Will be matched
            against the start of the title

        Returns
        -------
        list(str)
            a list of title_ids.

        '''
        c = self.db.getcursor()
        return c.fetchlist(
            "select distinct title_id"
            " from title_title"
            " where"
            "  title_name ilike %s"
            "  or alternate_name ilike %s",
            (f'{title}%', f'{title}%'))

    def __getitem__(self, key):
        '''
        Allows for title retrieval by name. Requires exact match.

        If the full title string is passed in (with alt name), it ignores the
        alt name. However, if the alt name is provided as the string, it
        will find it.

        Parameters
        ----------
        key : TYPE
            DESCRIPTION.

        Returns
        -------
        TYPE
            DESCRIPTION.

        '''
        c = self.db.getcursor()
        # if they've passed in full title, including the alternate, strip it
        if '=' in key:
            key, _ = key.split('=')
        return (
            Title(self.db, title_id[0])
            for title_id
            in c.execute('select distinct title_id'
                         ' from title_title'
                         ' where title_name = %s'
                         ' or alternate_name = %s',
                         (key.upper(), key.upper())))

    def complete(self, title, author=None):
        '''
        Autocomplete for a title

        Parameters
        ----------
        title : string
            String to check against the start of titles.
        author : string (optional)
            Restrict the titles to just this author (partial match from the
                                                     beginning).

        Returns
        -------
        list(int)
            a list of titles to autocomplete with.

        '''
        author_query = ''
        args = []

        if author:
            args = [f'{author}%']
            author_query = " entity_name ilike %s and "

        args += [f'{title}%', f'{title}%']
        c = self.db.getcursor()
        return c.fetchlist(
            " select distinct title_name"
            "  from"
            "   title_title "
            "   natural join title_responsibility "
            "   natural join entity"
            "  where"
            f'{author_query}'
            "   (title_name ilike %s"
            "    or alternate_name ilike %s)",
            args)

    def complete_checkedout(self, title, author=''):
        '''
        Autocomplete for a title limited to books checked out

        Parameters
        ----------
        title : string
            String to check against the start of titles
        author : string (optional)
            Restrict the titles to just this author (partial match from the
                                                     beginning).

        Returns
        -------
        list(str)
            a list of titles for autocomplete.

        '''
        author_query = ''
        args = []

        if author:
            args = [f'{author}%']
            author_query = " entity_name ilike %s and "

        args += [f'{title}%', f'{title}%']
        c = self.db.getcursor()
        return c.fetchlist(
            "select distinct title_name"
            " from checkout "
            "  natural join book "
            "  natural join title_title"
            "  natural join title_responsibility"
            "  natural join entity"
            " where "
            f'{author_query}'
            "  checkin_stamp is null and"
            "  (title_name ilike %s or"
            "   alternate_name ilike %s)",
            args)

    # search by author only used in specify
    def search_by_author(self, author):
        '''
        Autocomplete for a title limited to a specific author substr

        Parameters
        ----------
        author : string (optional)
           Get titles for this author (partial match from the beginning).

        Returns
        -------
        list(str)
            a list of titles for autocomplete.

        '''
        c = self.db.getcursor()
        return c.fetchlist(
            "select distinct(CONCAT_WS('=', title_name, alternate_name))"
            " from title_title"
            " natural join title_responsibility"
            " natural join entity"
            " where"
            "  entity_name ilike %s"
            "  or alternate_entity_name ilike %s",
            (f'{author}%', f'{author}%'))

    def grep(self, s):
        '''
        Parameters
        ----------
        s : string
            A streng to match against the titles. Can be a
            regular expression.

        Returns
        -------
        list(title_ids)
            A list of title_ids where the title name patial-matches
            the submitted string.
        '''
        c = self.db.getcursor()
        return c.fetchlist(
            'select title_id'
            ' from title_title'
            ' where title_name ~ %s or alternate_name ~ %s',
            (s.upper(), s.upper()))


class Title(dexfile.DexLine, db.Entry):
    def __init__(self, database, title_id=None):
        db.Entry.__init__(self, 'title', 'title_id', database, title_id)
        self.title_id = title_id

    # neither of these two is doing anything interesting. Can probably drop
    # them
    comment = db.Field('title_comment')
    lost = db.Field('title_lost')

    def _cache_query(self, key, sql):
        name = 'Q_' + key
        if name in self.cache:
            return self.cache[key]

        ret = list(self.cursor.execute(sql, (self.id,)))
        self.cache[key] = ret

        return ret

    @property
    @db.cached
    def authors(self):
        '''
        Returns
        -------
        FieldTuple (string)
            Tuple of the authors attached to this title, in order.
        '''
        # TODO: Figure out what to do with responsibility_types
        authors = self.cursor.fetchlist(
            "select"
            "  concat_ws('=', entity_name, alternate_entity_name)"
            " from"
            "  title_responsibility"
            "  natural join entity"
            " where title_id = %s"
            " order by order_responsibility_by", (self.id,))

        return utils.FieldTuple(authors)

    def add_author(self, author, responsibility_type='?'):
        for a in self.authors:
            if str(author) == a:
                raise exceptions.DuplicateEntry(
                    f'{a} is already attached to this title')

        order = self.cursor.selectvalue(
            'select max(order_responsibility_by) + 1'
            ' from title_responsibility'
            ' where title_id = %s', (self.id,))
        if order is None:
            order = 0

        self.cursor.execute(
            'insert into title_responsibility'
            ' (title_id, entity_id, order_responsibility_by,'
            ' responsibility_type)'
            ' values (%s, %s, %s, %s)',
            (self.id, author.id, order, responsibility_type))
        self.cache_reset()

    @property
    @db.cached
    def titles(self):
        '''
        Returns
        -------
        FieldTuple (string)
            Tuple of the titles attached to this title, in order.
        '''
        sql = ("select"
               "  concat_ws('=', title_name, alternate_name)"
               " from title_title"
               " where title_id = %s"
               " order by order_title_by")

        titles = self._cache_query('titles', sql)
        return utils.FieldTuple([t[0] for t in titles])

    def add_title(self, title_name, alt_name=None):
        for title in self.titles:
            if title == title_name or (title.startswith(title_name + '=')
                                       or title.endswith('=' + title_name)):
                raise exceptions.DuplicateEntry(
                    f'{title} is already attached to this title')

        order = self.cursor.selectvalue(
            'select max(order_title_by) + 1'
            ' from title_title'
            ' where title_id = %s', (self.id,))
        if order is None:
            order = 0

        self.cursor.execute(
            'insert into title_title'
            ' (title_id, title_name, alternate_name, order_title_by)'
            ' values (%s, %s, %s, %s)',
            (self.id, title_name, alt_name, order))
        self.cache_reset()

    @property
    @db.cached
    def series(self):
        '''
        Returns
        -------
        FieldTuple (string)
            Tuple of the series attached to this title, in order.
        '''
        sql = ("select"
               "  series_name, series_index, series_visible, number_visible"
               " from"
               "  title_series"
               "  natural join series"
               " where title_id = %s"
               " order by order_series_by")

        series_list = (
            ('@' if series_visible else '') + series_name +
            (' ' + ('#' if number_visible else '') + series_index
             if series_index else '')
            for series_name, series_index, series_visible, number_visible
            in self._cache_query('series_tuple', sql))
        return utils.FieldTuple(series_list)

    def add_series(self, series, series_index=None,
                   series_visible=False, number_visible=False):

        for s in self.series:
            s = dexfile.SERIES_VISIBLE.sub('', s)
            s = dexfile.SERIES_NUMBERED.sub('', s)
            if s == str(series):
                raise exceptions.DuplicateEntry(
                    f'{s} is already attached to this title')

        order = self.cursor.selectvalue(
            'select max(order_series_by) + 1'
            ' from title_series'
            ' where title_id = %s', (self.id,))
        if order is None:
            order = 0

        self.cursor.execute(
            'insert into title_series'
            ' (title_id, series_id, series_index, order_series_by, '
            ' series_visible, number_visible)'
            ' values (%s, %s, %s, %s, %s, %s)',
            (self.id, series.id, series_index, order,
             series_visible, number_visible))
        self.cache_reset()

    @property
    def books(self):
        '''
        Returns
        -------
        list(Book)
            List of the books we own in the library associated with this title
        '''
        cursor = self.cursor
        # This is a subselect so we can sort by shelcode_Id
        book_list = cursor.fetchlist(
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
            (self.id, ))
        return [Book(self.db, book_id) for book_id in book_list]

    @property
    def withdrawn_books(self):
        '''
        Returns
        -------
        list(Book)
            List of the books we used to own in the library
            associated with this title
        '''
        return [Book(self.db, book_id) for book_id in
                self.cursor.fetchlist(
                    "select book_id from book where title_id=%s and withdrawn",
                    (self.id, ))]

    @property
    def codes(self):
        '''
        Returns
        -------
        Editions
            Returns an Editions object with the information about the
            shelfcodes of books associated with this title
        '''
        count = {}
        for book in self.books:
            shelfcode = (('@' if book.visible else '')
                         + book.shelfcode.code +
                         (book.doublecrap if book.doublecrap else ''))
            count.setdefault(shelfcode, 0)
            count[shelfcode] += 1
        return Editions(','.join(f'{k}:{v}' for k, v in count.items()))

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
    def nicetitle(self):
        '''
        prints out a pretty looking title/series string (I think).
        Does not seem to be used anywhere, though the code is repeated in a
        few places
        '''
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

    @property
    def checkedout(self):
        '''
        Returns
        -------
        bool
            true if there's a copy checked out.

        '''
        c = self.cursor or self.dex.cursor
        return c.selectvalue(
            'select count(title_id)'
            ' from'
            '  checkout'
            '  natural join book'
            ' where'
            '  checkin_stamp is null and'
            '  title_id = %s',
            (self.id,))
