import re

from mitsfs.core import db, dexline
from mitsfs.util import exceptions, utils
from mitsfs.dex.editions import Editions
from mitsfs.dex.books import Book
from mitsfs.dex.series import munge_series


class Titles(object):
    # this class is tested in test_indexes.py
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
            ' select distinct title_name'
            '  from'
            '   title_title '
            '   natural join title_responsibility'
            '   natural join entity'
            '  where'
            f'{author_query}'
            '   (title_name ilike %s'
            '    or alternate_name ilike %s)'
            'order by title_name',
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

    def book_titles(self, shelfcode=None):
        '''
        A list of titles for which we have a book

        Parameters
        ----------
        shelfcode : Shelfcode (optional)
           Limit this to books of a specific shelfcode

        Returns
        -------
        list(str)
            a list of title objects for autocomplete.

        '''
        c = self.db.getcursor()
        if shelfcode:
            return [Title(self.db, i) for i in c.fetchlist(
                'select distinct title_id'
                ' from title natural join book'
                ' where not withdrawn and shelfcode_id = %s', (shelfcode.id,))]
        else:
            return [Title(self.db, i) for i in c.fetchlist(
                'select distinct title_id'
                ' from title natural join book'
                ' where not withdrawn')]

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


TITLE_FORBIDDEN = re.compile(r'[\\|=<]')
def sanitize_title(field, db=None):
    '''
    Clean out characters that would cause a Dexline problem. Also uppercases
    everything

    Parameters
    ----------
    field : string
        the field to be sanitized.
    db : Database
        Unnexessary here, but this is used as a coercer, which
        sends it. The default is None.

    Returns
    -------
    string
        the sanitized string.

    '''
    if field is None:
        return None
    field = re.sub(TITLE_FORBIDDEN, '', field)
    return field.upper()

def check_for_leading_article(t):
    '''
    

    Parameters
    ----------
    t : string
        The title to check.

    Returns
    -------
    Boolean
        True if the title starts with an article, which is probably 
        unintentional.
    '''
    return t.upper().startswith(('A ', 'AN ', 'THE '))
    
class Title(dexline.DexLine, db.Entry):
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
        Author strings. This is for backwards compatibility with the dex, so
        long term we should migrate to the right objects

        Returns
        -------
        FieldTuple (string)
            Tuple of the authors attached to this title, in order.
        '''
        authors = self.cursor.fetchlist(
            "select"
            "  concat_ws('=', entity_name, alternate_entity_name)"
            " from"
            "  title_responsibility"
            "  natural join entity"
            " where title_id = %s"
            " order by order_responsibility_by", (self.id,))

        return utils.FieldTuple(authors)

    @property
    @db.cached
    def author_objects(self):
        '''
        Returns
        -------
        List (Author)
            List of the authors attached to this title, in order.
        '''
        from mitsfs.dex.authors import Author
        # TODO: Figure out what to do with responsibility_types
        authors = self.cursor.fetchlist(
            "select"
            "  entity_id"
            " from"
            "  title_responsibility"
            "  natural join entity"
            " where title_id = %s"
            " order by order_responsibility_by", (self.id,))

        return [Author(self.db, i) for i in authors]

    def add_author(self, author, responsibility_type='?'):
        '''
        Adds an author to this title

        Parameters
        ----------
        author : Author
            The author object to add.
        responsibility_type : str, optional
            Need to work on this. The default is '?'.

        Raises
        ------
        DuplicateEntry
            The author is already attached to this title.

        Returns
        -------
        None.

        '''
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

    def remove_author(self, author):
        '''
        Remove the author association from the title. If there are
        subsequent authors, bump them up a notch in the order

        Parameters
        ----------
        author : Author
            Author object describing the author to be removed.

        Returns
        -------
        None.

        '''
        order = self.cursor.selectvalue(
            'select order_responsibility_by from title_responsibility'
            ' where title_id = %s and entity_id = %s',
            (self.id, author.id))

        if order is None:
            raise exceptions.NotFoundException("No author with this id")

        self.cursor.execute(
            'delete from title_responsibility'
            ' where title_id = %s and entity_id = %s',
            (self.id, author.id))

        self.cursor.execute(
            'update title_responsibility'
            ' set order_responsibility_by = order_responsibility_by - 1'
            ' where title_id = %s and order_responsibility_by > %s',
            (self.id, order))

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

    def add_title(self, title_name, alt_name=None, commit=True):
        '''
        Add a title (name of book) to this title (title)

        Parameters
        ----------
        title_name : string
            The title to add.
        alt_name : string, optional
            Any alternate title, usually the one to sort by.
            The default is None.
        commit : bool, optional
            Whether to commit the added title to the db. The default is True.

        Raises
        ------
        exceptions.DuplicateEntry
            Raised when this title_name is already on the book.

        Returns
        -------
        None.

        '''
        title_name = sanitize_title(title_name)
        alt_name = sanitize_title(alt_name)
        for title in self.titles:
            if title == title_name or (title.startswith(title_name + '=')
                                       or title.endswith('=' + title_name)):
                raise exceptions.DuplicateEntry(
                    f'{title} is already attached to this title')

        # get the current position of the last title, so we can order this
        # after it
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
        if commit:
            self.db.commit()

        self.cache_reset()

    def update_title(self, old_title, new_title, new_alt=None):
        '''
        Update one of the titles associated with a title

        Parameters
        ----------
        old_title : string
            The title to replace.
        new_title : string
            The title to rplace it with.
        new_alt : string, optional
            The new alternate (sort) title to replace the ond one with.
            Can be none

        Returns
        -------
        None.

        '''
        new_title = sanitize_title(new_title)
        new_alt = sanitize_title(new_alt)
        self.cursor.execute(
            'update title_title'
            ' set title_name = %s, alternate_name = %s'
            ' where title_id = %s and title_name = %s',
            (new_title, new_alt, self.id, old_title))

        self.cache_reset()

    def remove_title(self, old_title):
        order = self.cursor.selectvalue(
            'select order_title_by from title_title'
            ' where title_id = %s and title_name = %s',
            (self.id, old_title))

        if order is None:
            raise exceptions.NotFoundException(f'No title {old_title}')

        self.cursor.execute(
            'delete from title_title'
            ' where title_id = %s and title_name = %s',
            (self.id, old_title))

        self.cursor.execute(
            'update title_title'
            ' set order_title_by = order_title_by - 1'
            ' where title_id = %s and order_title_by > %s',
            (self.id, order))

        self.cache_reset()

    def merge_title(self, other_book):
        '''
        Take another title object and merge it with this one. This is done by
        moving all the books associated with the other title over to this
        title, then deleting the title, author and series associations of the
        book being merged, followed by deleting the title entirely.

        Parameters
        ----------
        other_book : Title object
            The title object to merge into this title.

        Returns
        -------
        None.

        '''

        self.cursor.execute(
            'update book'
            ' set title_id = %s'
            ' where title_id = %s',
            (self.id, other_book.id))

        self.cursor.execute(
            'delete from title_responsibility'
            ' where title_id = %s',
            (other_book.id,))

        self.cursor.execute(
            'delete from title_series'
            ' where title_id = %s',
            (other_book.id,))

        self.cursor.execute(
            'delete from title_title'
            ' where title_id = %s',
            (other_book.id,))

        self.cursor.execute(
            'delete from title'
            ' where title_id = %s',
            (other_book.id,))

        self.db.commit()

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
            if munge_series(s)[0] == series.series_name:
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

    def remove_series(self, series):
        '''
        Removes the series association from a title. Someday, we will replace
        this with a series object, but for current Dexline compatibility,
        still identified by string.

        Parameters
        ----------
        series : string
            The series to remove from the title.

        Raises
        ------
        exceptions.NotFoundException
            The series name provided doesn't exist.

        Returns
        -------
        None.

        '''
        series_id = self.cursor.selectvalue(
            'select series_id from series'
            ' where series_name = %s',
            (series,))

        if series_id is None:
            raise exceptions.NotFoundException("No series with this name")

        order = self.cursor.selectvalue(
            'select order_series_by from title_series'
            ' where title_id = %s and series_id = %s',
            (self.id, series_id))

        self.cursor.execute(
            'delete from title_series'
            ' where title_id = %s and series_id = %s',
            (self.id, series_id))

        self.cursor.execute(
            'update title_series'
            ' set order_series_by = order_series_by - 1'
            ' where title_id = %s and order_series_by > %s',
            (self.id, order))

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
            "select book_id"
            " from book"
            " where title_id=%s and not withdrawn"
            " order by shelfcode_id",
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
            if book.shelfcode is None:
                print(f'Problematic shelfcode for {book.title.titles}')
                continue
            shelfcode = (('@' if book.visible else '')
                         + book.shelfcode.code +
                         (book.doublecrap if book.doublecrap else ''))
            count.setdefault(shelfcode, 0)
            count[shelfcode] += 1
        return Editions(','.join(f'{k}:{v}' for k, v in count.items()))

    def __str__(self):
        result = dexline.DexLine.__str__(self)
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
