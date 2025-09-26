#!/usr/bin/python
'''

code for manipulating pinkdex-style files

'''

import os
import re

from mitsfs import utils
from io import open
from functools import total_ordering

from mitsfs.dex.editions import Edition, Editions
from mitsfs.utils import sanitize_sort_key

# pragma_validate_shelfcode = True

# CODESPLITRE = re.compile(r'[;:]')
# BOXRE = re.compile(r'([-A-Z0-9/.#]+){([A-Z/]+)}')


# def onecode(s, defcount=1, validate=None):
#     if validate is None:
#         validate = pragma_validate_shelfcode
#     box = ''
#     split = CODESPLITRE.split(s)
#     n = len(split)
#     if n == 0 or n > 2:
#         raise conf.InvalidShelfcode('Invalid code string', s)
#     if len(split) == 1:
#         code, count = split[0], defcount
#     else:
#         code, count = split
#         if not count:
#             count = defcount
#         try:
#             count = int(count)
#         except ValueError:
#             raise conf.InvalidShelfcode('Invalid count', count)
#     m = BOXRE.match(code)
#     if m:
#         box, code = m.groups(1)
#     if code and validate:
#         conf.splitcode(code)  # throws an exception on invalid code
#     return code, count, box


# AAAAAAAAAAAAAAAAAAAIIIIIIIIIIIIIIIIIIIIIIIIIIIIEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE


SERIES_VISIBLE = re.compile(r'^@')
SERIES_NUMBERED = re.compile(r' #?[-.,\d]+B?$')


def deseries(s):
    '''
    Parameters
    ----------
    s : string
        Remove the metadata tags (preceding @, trailing number) from a series.

    Returns
    -------
    s : string
        normalized series value

    '''
    s = SERIES_VISIBLE.sub('', s)
    s = SERIES_NUMBERED.sub('', s)
    return s


def deat(s):
    '''
    Parameters
    ----------
    s : string
        a shelfcode from a book

    Returns
    -------
    string
        The shelfcode with any starting @ (book series visible) removed.

    '''
    if len(s) < 1:
        return s
    if s[0] == '@':
        return s[1:]
    else:
        return s


@total_ordering
class DexLine(object):
    fieldtypes = (
        ('authors', utils.FieldTuple, utils.FieldTuple(), False),
        ('titles', utils.FieldTuple, utils.FieldTuple(), False),
        ('series', utils.FieldTuple, utils.FieldTuple(), False),
        ('codes', Editions, Editions(''), True),
        )
    fields = [name for (name, constructor, default, copy) in fieldtypes]
    splits = ['authors', 'titles', 'series']
    # emptytuple = utils.FieldTuple()
    # emptycodes = Editions()

    def __init__(
            self, line=None, authors=None, titles=None, series=None,
            codes=None,
            ):
        if line is not None:
            if isinstance(line, self.__class__):
                for (name, constructor, default, copy) in DexLine.fieldtypes:
                    if not copy:
                        setattr(self, name, getattr(line, name))
                    else:
                        setattr(self, name, constructor(getattr(line, name)))
                # XXX kluuuuuuuuuuuudge
                if hasattr(line, 'title_id'):
                    self.title_id = line.title_id
            else:
                split = line.strip().split('<')
                assert len(split) == 4
                for ((name, constructor, default, copy), value) in \
                        zip(DexLine.fieldtypes, split):
                    setattr(self, name, constructor(value))
        else:
            for (name, construct, default, copy) in DexLine.fieldtypes:
                setattr(self, name, default)
        if authors is not None:
            self.authors = utils.FieldTuple(authors)
        if titles is not None:
            self.titles = utils.FieldTuple(titles)
        if series is not None:
            self.series = utils.FieldTuple(series)
        if codes is not None:
            if isinstance(codes, Editions):
                self.codes = codes
            else:
                self.codes = Editions(codes)

    def __str__(self):
        return '<'.join([
            str(getattr(self, field))
            for field in self.fields])

    def logstr(self):
        return '<'.join([
            getattr(self, field).logstr()
            for field in self.fields])

    def negate(self):
        line = self.__class__(self)
        line.codes = -line.codes
        return line

    def key(self):
        return self.authors, self.titles

    def __repr__(self):
        return 'DexLine(' + repr(str(self)) + ')'

    authortxt = property(lambda self: str(self.authors))
    titletxt = property(lambda self: str(self.titles))
    seriestxt = property(lambda self: str(self.series))

    placeauthor = property(lambda self: sanitize_sort_key(self.authors[0]))
    placetitle = property(
        lambda self: sanitize_sort_key(self.titles[0].split('=')[-1]))
    TRAILING_NUMBER = re.compile(r' [0-9,]+$')
    placeseries = property(
        lambda self: len(self.series) and sanitize_sort_key(
            self.TRAILING_NUMBER.sub('', self.series[0])) or '')

    def sortkey(self):
        return (
            (self.placeauthor, self.placetitle, self.authortxt,
             self.placetitle, self.titletxt),
            self)

    VSRE = re.compile(r' #([-.,\d]+B?)$')

    def shelfkey(self, shelfcode):
        edition = Edition(shelfcode)

        if edition.double_info:
            key = [edition.double_info, self.placeauthor]
        else:
            key = [self.placeauthor]
        if self.series:
            series_visible = (edition.series_visible
                              or self.series[0][0] == '@')
            if series_visible:
                key += [self.placeseries]
                m = self.VSRE.search(self.series[0])
                if m:
                    key += [sanitize_sort_key(m.group(0))]
        key += [self.placetitle]
        return tuple(key)

    def __eq__(self, other):
        return (self.authors, self.titles) == (other.authors, other.titles)

    def __lt__(self, other):
        return (self.authors, self.titles) < (other.authors, other.titles)


class Dex(object):
    def __init__(self, source=None, zerok=False):
        self.indexdata = [('authors', {}, None),
                          ('titles', {}, None),
                          ('series', {}, deseries),
                          ('codes', {}, deat)]
        self.indices = utils.PropDict([
            (field, index)
            for (field, index, filt) in self.indexdata])
        self.indexfilt = dict([
            (field, filt)
            for (field, index, filt) in self.indexdata
            if filt is not None])
        self.authors = self.indices.authors
        self.titles = self.indices.titles
        self.series = self.indices.series

        self.list = []
        self.dict = {}

        self.zerok = zerok

        self.filename = None

        if source is not None:
            opened = False
            if hasattr(source, 'isupper'):
                # likely a string, which means a filename
                self.filename = source
                try:
                    source = open(self.filename)
                    opened = True
                except IOError as e:
                    if e.errno != 2:
                        raise
                    source = []
            elif hasattr(source, 'filename'):
                # copy it
                self.filename = source.filename
            for i in source:
                self.add(DexLine(i))
            if opened:
                source.close()

    def add(self, line, review=False):
        if not isinstance(line, DexLine):
            line = DexLine(line)
        k = line.key()
        if k not in self.dict:
            if not self.zerok:
                for edition in list(line.codes.values()):
                    if edition.count < 1:
                        del line.codes[edition.shelfcode]
            if line.codes or self.zerok:
                self.dict[k] = line
                self.list.append(line)
                for field, index in self.indices.items():
                    for i in getattr(line, field):
                        f = self.indexfilt.get(field)
                        if f is not None:
                            i = f(i)
                        index.setdefault(i, []).append(line)
        else:
            o = self.dict[line.key()]
            assert line is not o, 'Attempted merge of DexLine already in dex'
            old = set(o.codes.keys())
            o.codes = o.codes + line.codes
            new = set(o.codes.keys())
            # fix up index
            for i in new - old:
                # shelfcodes we weren't in before
                self.indices['codes'].setdefault(i, []).append(o)
            for i in old - new:
                # shelfcodes we aren't in anymore
                self.indices['codes'][i].remove(o)
            if not self.zerok and not o.codes:
                self.remove(o)

    def replace(self, line, m):
        # just in case, look l up
        line = self.dict[(line.authors, line.titles)]
        self.add(line.negate())
        self.add(m)

    def merge(self, d):
        for i in d:
            self.add(i)

    def remove(self, line):
        k = line.key()
        line = self.dict[k]
        del self.dict[k]
        self.list.remove(line)

        for (field, index, filt) in self.indexdata:
            for val in getattr(line, field):
                if filt is not None:
                    val = filt(val)
                self.indices[field][val].remove(line)

    def __sub__(self, other):
        # first make a copy of myself
        result = Dex(self)
        result.filename = None
        for i in other:
            result.add(i.negate())
        return result

    def __len__(self):
        return len(self.list)

    def __iter__(self):
        for i in self.list:
            yield i

    def __contains__(self, key):
        if not isinstance(key, DexLine):
            key = DexLine(key)
        return key.key() in self.dict

    def __getitem__(self, key):
        if not isinstance(key, DexLine):
            key = DexLine(key)
        return self.dict[key.key()]

    def sorted(self):
        for v in sorted(self.list, key=lambda v: v.sortkey()):
            yield v

    def sortcode(self, code):
        self.indices['codes'][code].sort(key=lambda v: v.sortkey())

    def sort(self):
        self.list.sort(key=lambda v: v.sortkey())
        for index in self.indices.values():
            for dexlist in index.values():
                dexlist.sort(key=lambda v: v.sortkey())

    def save(self, filename, callback=lambda: None):
        direct, base = os.path.split(filename)
        tempname = os.path.join(direct, '#' + base + '#')
        fp = open(tempname, 'w')
        count = 0
        callback()
        self.list.sort(key=lambda v: v.sortkey())
        callback()
        for i in self.list:
            fp.write(str(i) + "\n")
            count += 1
            if (count % 1000) == 0:
                callback()
        fp.close()
        os.rename(tempname, filename)

    def stats(self):
        d = {}
        for line in self:
            for incode, edition in line.codes.items():
                if edition.shelfcode not in d:
                    d[edition.shelfcode] = edition.count
                else:
                    d[edition.shelfcode] += edition.count
        return d

    # dexdb version replaced with library.catalog.title.search. I don't
    # think this one is used
    def titlesearch(self, frag):
        for bucket in (
                self.indices['titles'][i]
                for i in self.indices['titles'] if i.startswith(frag)
                ):
            for item in bucket:
                yield item

    GREPSPLIT = re.compile(r'[<`]')

    def grep(self, s):
        pats = [
            i and re.compile(i, re.IGNORECASE) or None
            for i in Dex.GREPSPLIT.split(s)]

        if len(pats) == 1:
            def predicate(line):
                return pats[0].search(str(line))
        else:
            pats += [None] * (4 - len(pats))

            def predicate(line):
                return all([
                    any([pat.search(value) for value in field])
                    for (pat, field)
                    in zip(pats, [
                        line.authors,
                        line.titles,
                        line.series,
                        line.codes.list()])
                    if pat])
        return (line for line in self if predicate(line))

    def __str__(self):
        return '\n'.join([str(i) for i in self.sorted()])

    def __repr__(self):
        s = object.__repr__(self)[:-1]
        if self.filename:
            s += ' ' + repr(self.filename)
        s += ' %d entries' % len(self.dict)
        s += ' %d books>' % sum(self.stats().values())
        return s

    def __nonzero__(self):
        return bool(self.list)
