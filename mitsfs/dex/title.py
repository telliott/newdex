import re

from mitsfs import dexfile
from mitsfs.core import db
from mitsfs import utils
from mitsfs.dex.editions import Editions
from mitsfs.dex.book import Book


class Title(dexfile.DexLine, db.Entry):
    def __init__(self, database, title_id):
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

        ret = list(self.cursor.execute(sql, (self.title_id,)))
        self.cache[key] = ret

        return ret

    @property
    @db.cached
    def authors(self):
        # TODO: Figure out what to do with responsibility_types
        sql = ("select"
               "  concat_ws('=', entity_name, alternate_entity_name)"
               " from"
               "  title_responsibility"
               "  natural join entity"
               " where title_id = %s"
               " order by order_responsibility_by")

        authors = self._cache_query('authors', sql)
        return utils.FieldTuple([a[0] for a in authors])

    @property
    @db.cached
    def titles(self):
        sql = ("select"
               "  concat_ws('=', title_name, alternate_name)"
               " from title_title"
               " where title_id = %s"
               " order by order_title_by")

        titles = self._cache_query('titles', sql)
        return utils.FieldTuple([t[0] for t in titles])

    @property
    @db.cached
    def books(self):
        cursor = self.cursor
        # This is a subselect so we can sort by shelcode_Id
        books = cursor.fetchlist(
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
        return [Book(self, i) for i in books]

    @property
    @db.cached
    def series(self):
        sql = ("select"
               "  series_name, series_index, series_visible, number_visible"
               " from"
               "  title_series"
               "  natural join series"
               " where title_id = %s"
               " order by order_series_by")

        those = (
            ('@' if series_visible else '') +
            series_name +
            (' ' + ('#' if number_visible else '') + series_index
             if series_index else '')
            for series_name, series_index,
            series_visible, number_visible in self._cache_query('series', sql))
        return utils.FieldTuple(those)

    @property
    @db.cached
    def codes(self):
        sql = ("select"
               "  book_series_visible, shelfcode, doublecrap, count(shelfcode)"
               " from"
               "  book"
               "  natural join shelfcode"
               " where"
               "  title_id = %s and"
               "  not withdrawn"
               " group by book_series_visible, shelfcode, doublecrap"
               " order by not book_series_visible, shelfcode, doublecrap")

        return Editions(
            ','.join(
                ('@' if series_visible else '') +
                shelfcode +
                (doublecrap if doublecrap else '') +
                (':' + str(count)
                 if count > 1 else '')
                for series_visible, shelfcode,
                doublecrap, count in self._cache_query('codes', sql)))

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
        author = self.authors[0][1]
        title = self.titles[0][1]

        doublecrap, book_series_visible = [
            (doublecrap, book_series_visible)
            for (book_series_visible, qshelfcode, doublecrap, count)
            in self.codes
            if qshelfcode == shelfcode][0]

        if doublecrap:
            key = [doublecrap, author]
        else:
            key = [author]

        if self.series:
            series, series_index, series_visible, index_visible \
                = self.series[0]
            if series_visible:
                key += [series]
                if index_visible:
                    key += [series_index]
        key += [title]
        return tuple(dexfile.sanitize_sort_key(i).strip() for i in key)

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
        return c.selectvalue(
            'select count(title_id)'
            ' from'
            '  checkout'
            '  natural join book'
            ' where'
            '  checkin_stamp is null and'
            '  title_id = %s',
            (self.id,))

    # created = db.ReadField('title_created')
    # created_by = db.ReadField('title_created_by')
    # created_with = db.ReadField('title_created_with')
    # modified = db.ReadField('title_modified')
    # modified_by = db.ReadField('title_modified_by')
    # modified_with = db.ReadField('title_modified_with')

