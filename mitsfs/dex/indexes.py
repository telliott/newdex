from mitsfs.dex.editions import Edition, InvalidShelfcode
from mitsfs.dex.title import Title


class SeriesIndex(object):
    def __init__(self, db):
        self.db = db

    def keys(self):
        c = self.db.getcursor()
        return c.fetchlist(
            'select distinct upper(series_name)'
            ' from series'
            '  natural join title_series'
            '  natural join title'
            '  natural join book'
            ' where not withdrawn order by upper(series_name)')

    def search(self, series):
        c = self.db.getcursor()
        return c.fetchlist(
            "select distinct series_id"
            " from series"
            " where"
            "  series_name ilike %s",
            (f'{series}%',))

    def __getitem__(self, key):
        c = self.db.getcursor()
        # sort this properly 'cus it's convenient
        return (
            Title(self.db, title_id[0])
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

    def complete(self, s):
        c = self.db.getcursor()
        return c.fetchlist(
            'select series_name from series'
            ' where position(%s in upper(series_name)) = 1'
            ' order by series_name',
            (s.strip().upper(),))


class TitleIndex(object):
    def __init__(self, db):
        self.db = db

    def keys(self):
        c = self.db.getcursor()
        return c.fetchlist("select CONCAT_WS('=', title_name, alternate_name)"
                           " from title_title")

    def search(self, title):
        c = self.db.getcursor()
        return c.fetchlist(
            "select distinct title_id"
            " from title_title"
            " where"
            "  title_name ilike %s",
            (f'{title}%',))

    def __getitem__(self, key):
        c = self.db.getcursor()
        # if they've passed in full title, including the alternate, strip it
        if '=' in key:
            key, _ = key.split('=')
        return (
            Title(self.db, title_id[0])
            for title_id
            in c.execute('select distinct title_id'
                         ' from title_title'
                         ' where upper(title_name) = upper(%s)',
                         (key,)))

    def complete(self, title, author=''):
        c = self.db.getcursor()
        return c.fetchlist(
            " select distinct(CONCAT_WS('=', title_name, alternate_name))"
            "  from"
            "   title_title "
            "   natural join title_responsibility "
            "   natural join entity"
            "  where"
            "   position(upper(%s) in entity_name) = 1 and"
            "   (position(upper(%s) in title_name) = 1"
            "    or position(upper(%s) in alternate_name) = 1)",
            (author, title, title))

    def complete_checkedout(self, title, author=''):
        c = self.db.getcursor()
        return c.fetchlist(
            "select distinct(CONCAT_WS('=', title_name, alternate_name))"
            " from checkout "
            "  natural join book "
            "  natural join title_title"
            "  natural join title_responsibility"
            "  natural join entity"
            " where "
            "  checkin_stamp is null and"
            "  position(upper(%s) in entity_name) = 1 and"
            "  (position(upper(%s) in title_name) = 1 or"
            "   position(upper(%s) in alternate_name) = 1)",
            (author, title, title))

    # search by author only used in specify
    def search_by_author(self, author):
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


class AuthorIndex(object):
    def __init__(self, db):
        self.db = db

    def keys(self):
        c = self.db.getcursor()
        return c.fetchlist(
                "select CONCAT_WS('=', entity_name, alternate_entity_name)"
                ' from entity'
                ' order by upper(entity_name)')

    def search(self, author):
        c = self.db.getcursor()
        return c.fetchlist(
            "select distinct entity_id"
            " from entity"
            " where"
            "  entity_name ilike %s",
            (f'{author}%',))

    def __getitem__(self, key):
        c = self.db.getcursor()
        return (
            Title(self.db, title_id[0])
            for title_id
            in c.execute(
                'select distinct title_id'
                ' from title_responsibility'
                '  natural join entity'
                ' where'
                ' entity_name ilike %s'
                ' or alternate_entity_name ilike %s',
                (f'{key}%', f'{key}%')))

    def complete(self, key):
        c = self.db.getcursor()
        return c.fetchlist(
            'select entity_name'
            ' from entity'
            ' where'
            ' entity_name ilike %s'
            ' or alternate_entity_name ilike %s',
            (f'{key}%', f'{key}%'))

    def complete_checkedout(self, key):
        c = self.db.getcursor()
        return c.fetchlist(
            'select entity_name'
            ' from'
            '  entity'
            '  natural join title_responsibility'
            '  natural join book'
            '  natural join checkout'
            ' where'
            '  checkin_stamp is null and'
            ' (entity_name ilike %s'
            ' or alternate_entity_name ilike %s)',
            (f'{key}%', f'{key}%'))


class ShelfcodeIndex(object):
    def __init__(self, db):
        self.db = db

    def keys(self):
        c = self.db.getcursor()
        return c.fetchlist(
                'select distinct shelfcode, doublecrap'
                ' from book natural join shelfcode')

    def __getitem__(self, key):
        c = self.db.getcursor()
        try:
            e = Edition(key)
            code = e.shelfcode
            doublecrap = e.double_info
        except InvalidShelfcode:
            code, doublecrap = key, None
        # sort this properly 'cus we sort of need it
        q = (
            'select title_id'
            ' from title'
            '  natural join title_responsibility'
            '  natural join entity'
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
            Title(self.db, title_id[0])
            for title_id
            in c.execute(q, a))

    def stats(self):
        c = self.db.getcursor()
        return dict(c.execute(
            "select distinct shelfcode, count(shelfcode)"
            " from"
            "  book"
            "  natural join shelfcode"
            " where not withdrawn"
            " group by shelfcode"))
