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
#from mitsfs import constants
from mitsfs.core import db
from mitsfs import dexfile
from mitsfs import lock_file
from mitsfs.dex.shelfcodes import Shelfcodes
from mitsfs.dex.editions import Edition, Editions, InvalidShelfcode
from mitsfs.util.coercers import coerce_shelfcode, uncoerce_shelfcode
from mitsfs.util import utils, exceptions
from mitsfs.circulation.checkouts import Checkouts, Checkout
from mitsfs.circulation.members import Member
from mitsfs.dex.titles import Titles, Title
from mitsfs.dex.books import Book
from mitsfs.dex.series import SeriesIndex, Series, munge_series
from mitsfs.dex.authors import Authors

from io import open


__all__ = [
    'DexDB',
    ]


# hacktackular!
gensym_seed = itertools.count()


def gensym():
    return ('G%04d' % next(gensym_seed))

# appears to be entriely unused.
# NOTERE = re.compile(r'(.*)\((.*)\)')
# def notesplit(s):
#     if s[-1] == ')':
#         m = NOTERE.match(s)
#         if m:
#             name, note = m.groups()
#             return name.strip(), note.strip()
#     return s, ''


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
            titles=Titles(self),
            authors=Authors(self),
            codes=Shelfcodes(self))
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
            # patterns anchored at the other end will ce weird results.
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
        return Book(self, book_id, title=title_id)

    def exdex(self, c, callback=lambda: None):
        authors = {}
        for (title_id, responsibility_type, entity_name, alt) in c.execute(
                'select title_id, responsibility_type, '
                "  concat_ws('=', entity_name, alternate_entity_name)"
                ' from'
                '  title_responsibility'
                '  natural join entity'
                '  order by title_id, order_responsibility_by'):
            authors.setdefault(title_id, []).append(
                (responsibility_type, entity_name, alt))

        titles = {}
        for (title_id, title_name) in c.execute(
                "select title_id, concat_ws('=', title_name, alternate_name)"
                ' from title_title'
                ' order by title_id, order_title_by'):
            titles.setdefault(title_id, []).append(title_name)

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
                authors=authors[title_id],
                titles=titles[title_id],
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
                        row[fields.titles]),
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
        for name in author.split('|'):
            if not name:
                continue
            t_r = gensym()
            ent = gensym()
            if not ts:
                ts += ('title_responsibility %s natural join entity %s'
                       % (t_r, ent))
            else:
                ts += (' join title_responsibility %s natural join '
                       'entity %s using (title_id)' % (t_r, ent))

            ps.append(
                f'({ent}.entity_name ilike %s'
                f' or {ent}.alternate_entity_name ilike %s)')
            args += [f'%{name}%', f'%{name}%']

        for title in titlename.split('|'):
            if not title:
                continue
            ttl = gensym()
            ts += (
                (' join %s using (title_id)' if ts else '%s') %
                ('title_title %s' % ttl))
            ps.append(
                f'({ttl}.title_name ilike %s'
                f' or {ttl}.alternate_name ilike %s)')
            args += [f'%{title}%', f'%{title}%']

        q = (
            'select distinct title_id from ' + ts +
            ' where ' + ' and '.join(ps))
        return sorted(
            (Title(self, title_id) for title_id in c.fetchlist(q, args)),
            key=lambda x: x.sortkey())

    # replaced by library.catalog.titles.search
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
                "  order_responsibility_by = %s",
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
                "  order_title_by = %s",
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
                "insert into entity(entity_name)"
                " values (%s)",
                (name.upper(),))
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

    # def get_shelfcode(self, name, c=None):
    #     if c is None:
    #         c = self.cursor
    #     try:
    #         (code_id,) = list(c.execute(
    #             'select shelfcode_id from shelfcode where shelfcode=upper(%s)',
    #             (name,)))
    #     except ValueError:
    #         raise KeyError(name)
    #     return code_id

    def replace(self, line, replacement):
        # TODO: This doesn't handle alternate title names? The whole things is
        # going to need a lot of work
        victim = self[line]
        title_id = victim.title_id
        # now figure out what changed and fiddle it
        # we "know" that we don't have to worry about shelfcodes

        vdata = victim.authors
        rdata = replacement.authors

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

        vdata = victim.titles
        rdata = replacement.titles

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
                    "  (title_id, title_name, alternate_name, order_title_by)"
                    " values (%s, %s, %s, %s)",
                    [(title_id, *equal_split(name), i1 + off + i)
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
        # TODO: We don't support responsibility types here (or in general)
        c.executemany(
            "insert into title_responsibility"
            "  (title_id, entity_id, order_responsibility_by)"
            " values (%s, %s, %s)",
            [(title_id, self.get_entity(name, c), order)
             for (order, name) in enumerate(authors)])
        c.executemany(
            "insert into title_title"
            " (title_id, title_name, alternate_name, order_title_by)"
            " values (%s, %s, %s, %s)",
            [(title_id, *equal_split(name.upper()), order)
             for (order, name) in enumerate(titles)])
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
                self.shelfcodes[e.shelfcode].id, e.double_info,
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
                    raise exceptions.Ambiguity('Please try a simpler '
                                               'operation for now.')
                count = len(removed)

                q = 'update book set'
                a = []

                if added:
                    edition = added(list(added.keys())[0])
                    q += (' shelfcode_id=%s, doublecrap=%s,'
                          ' book_series_visible=%s')
                    a += [
                        self.shelfcodes[edition.code].id,
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
                line.authors,
                line.titles,
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

    # replaced by library.catalog.shelfcodes.stats()
    def stats(self):
        return dict(self.cursor.execute(
            "select distinct shelfcode, count(shelfcode)"
            " from"
            "  book"
            "  natural join shelfcode"
            " where not withdrawn"
            " group by shelfcode"))

    _codes = None

    # replaced by library.shelfcodes
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


def diff(a, b):
    return [
        (i1, i2, j1, j2)
        for (op, i1, i2, j1, j2)
        in difflib.SequenceMatcher(None, a, b).get_opcodes()
        if op != 'equal']


# def uneq(tup):
#     # this function has become a crawling horror of corner cases.  I
#     # hope to be able to stop using it someday.
#     if not tup:
#         return []
    
#     first = tup[0]
#     rest = list(zip([False] * (len(tup) - 1), tup[1:]))
#     if not first and not rest:
#         return []
#     if first[0] == '=':
#         return [(True, first[1:])] + rest
#     if '=' in first:
#         return list(zip([True, False], reversed(first.split('=')))) + rest
#     else:
#         return [(False, first)] + rest



def equal_split(string):
    '''
    splits a string into parts on either side of an = sign. But if there's
    no = sign, forces an empty string

    Parameters
    ----------
    string : str
        title/author string to be splt.

    Returns
    -------
    list (str):
        a list with minimum two elements

    '''
    result = string.split('=')
    if len(result) == 1:
        result.append(None)
    return result

# Can't find anywhere this is used. Looks like it was a helper function
# where you could give it a dex and a grep and it would print lines for you
# def dg(d, q):
#     lines = [str(i) for i in d.grep(q)]
#     for i in lines:
#         print(i)
#     return len(lines)


# def parse_dex_equals(elements):
#     '''
#     Take the list of type-string tuples pulled out of the db, merge the lines
#     with '=' as the type and return the resulting list of strings. Used to do
#     title and author equivalency.

#     Note that this is barely used for authors and probably not worth
#     maintaining

#     Parameters
#     ----------
#     elements : list[(type, string)]
#         a list of tuples containing a type (we only care about '=') and the
#         associated string (a title or an author)

#     Returns
#     -------
#     list(string)
#         A list of all the titles/authors with the = rows merged.

#     '''

#     element_type, element_string = elements[0]

#     # if it's the = type, that means that there's a second row to follow
#     # that should be merged in with the first as an equivalent
#     if element_type == '=':
#         second_element_type, second_element_string = elements[1]
#         elements = [(second_element_type, second_element_string +
#                      '=' + element_string)] + elements[2:]

#     # ditch the types and return a list of the titles/authors
#     return [s for (t, s) in elements]


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
