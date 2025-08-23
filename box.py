#!/usr/bin/python

import sys
import itertools
from io import open

from mitsfs.dexdb import DexDB, Title
from mitsfs.dexfile import DexLine
from mitsfs.ui import read, readnumber, specify
from mitsfs.tex import TEXBASE, texquote

shelfcode_hint = {}
for shelfcodes, possible in \
    [(['VL', 'L', 'KBX/P', 'SR-H', 'D', 'C/D', 'BSFWA-P', 'S', 'KBX/H',
       'BSFWA', 'BP', 'VLH', 'SR-P'], ('S', 'L', 'VL',)),
     (['SR-PA', 'SR-HA', 'SA', 'LA', 'KBX/PA', 'KBX/HA'], ('SA', 'LA')),
     (['SR-S'], ('SR-S')),
     (['C/MM', 'SR-MM'], ('C/MM',)),
     (['R/REF-H', 'R/REF-P', 'C/REF-H', 'C/REF-P', 'R/XL-REF', 'R/VL-REF',
       'R/L-REF', 'R/S-REF', 'DICT', 'HASSLE/REF-P', 'HASSLE/REF-H', 'R/IND',
       'R/IND-F', 'SRL/IND', 'XL-REF', 'VL-REF', 'L-REF', 'S-REF', 'KBX/REF-H',
       'KBX/REF-P', 'KBX/H-REF', 'KBX/P-REF'],
      ('R/REF-H', 'R/REF-P', 'C/REF-H', 'C/REF-P', 'R/XL-REF', 'R/VL-REF',
       'R/L-REF', 'R/S-REF', 'DICT', 'XL-REF', 'VL-REF', 'L-REF', 'S-REF',)),
     (['SCX', 'CX', 'R/XL-CX', 'R/VL-CX', 'R/L-CX', 'R/S-CX', 'XL-CX', 'VL-CX',
       'L-CX', 'S-CX', 'KBX/H-CX', 'KBX/P-CX', ],
      ('R/XL-CX', 'R/VL-CX', 'R/L-CX', 'R/S-CX', 'XL-CX', 'VL-CX', 'L-CX',
       'S-CX',)), ]:
    for shelfcode in shelfcodes:
        shelfcode_hint[shelfcode] = set(possible)


def fmtcode(fmt):
    return fmt if fmt != '?' else 'WRD'


class Main(object):
    def __init__(self):
        self.d = DexDB()

        ((self.inventory_code, self.inventory_id, self.inventory_desc),) = \
            self.d.cursor.execute(
                'select inventory_code, inventory_id, inventory_desc'
                ' from inventory order by inventory_stamp desc limit 1')

    def commit(self):
        if True:
            self.d.db.commit()

    def tags(self):
        return list(self.d.getcursor().execute(
            'select distinct found_tag from inventory_found'
            ' where inventory_id=%s order by found_tag',
            (self.inventory_id,)))

    def contents(self, tag):
        return list(sorted(
            DexLine(
                Title(self.d, title_id),
                codes={fmtcode(fmt): count})
            for title_id, fmt, count in self.d.getcursor().execute(
                'select title_id, format, count(format)'
                ' from inventory_found natural join format'
                ' where inventory_id=%s and found_tag=%s'
                '  and resolving_id is null'
                ' group by title_id, format',
                (self.inventory_id, tag))))

    def argtags(self, tags=[]):
        if not tags:
            tags = self.tags()
        return tags

    def __call__(self):
        cmd = None
        if len(sys.argv) > 1:
            cmd = sys.argv[1]

        if cmd == 'list':
            print('\n'.join(self.tags()))
        elif cmd == 'show':
            tags = self.argtags(sys.argv[2:])
            for tag in tags:
                contents = self.contents(tag)
                if len(tags) > 1 and contents:
                    print(tag)
                    print()
                for line in contents:
                    print(line)
                if len(tags) > 1:
                    print()
        elif cmd == 'tags':
            first = True
            for tag in self.argtags():
                contents = list(self.d.getcursor().execute(
                    'select title_id, format'
                    ' from inventory_found natural join format'
                    ' where inventory_id=%s and found_tag=%s'
                    '  and resolving_id is null',
                    (self.inventory_id, tag)))
                if not contents:
                    continue
                contents = [
                    (fmt, DexLine(Title(self.d, title_id)))
                    for (title_id, fmt) in contents]
                contents.sort(key=lambda x: x[1])
                if first:
                    first = False
                else:
                    print(chr(12))
                print(tag)
                print()
                for title_id, line in contents:
                    print(fmt, line)
                    print()
        elif cmd == 'dex':
            for tag in self.argtags(sys.argv[2:]):
                writedex(
                    '%s.%s' % (self.inventory_code, tag),
                    'Found box %s (%s)' % (tag, self.inventory_code),
                    self.contents(tag),
                    )
        elif cmd == 'merge':
            target = sys.argv[2]
            tags = self.argtags(sys.argv[3:])
            self.d.cursor.execute(
                'update inventory_found set found_tag=%s'
                ' where inventory_id=%s'
                '  and resolving_id is null'
                '  and found_tag in %s',
                (target, self.inventory_id, tuple(tags)))
            self.commit()
        elif cmd == 'edit':
            if len(sys.argv) < 2:
                print('You must specify a box')
            elif len(sys.argv) > 3:
                print('You can only edit one box at a time, sorry')
            else:
                self.edit(sys.argv[2])
        elif cmd == 'disambiguate':
            if len(sys.argv) < 3:
                print('you must specify a target box')
                return
            target = sys.argv[2]
            tags = self.argtags(sys.argv[3:])
            self.disambiguate(target, tags)
        elif cmd == 'resolve':
            self.resolve(sys.argv[2], self.argtags(sys.argv[3:]))
        elif cmd == 'matches':
            self.matches(sys.argv[2], self.argtags(sys.argv[3:]))
        else:
            print('first argument must be one of')
            print(' list, show, tags, dex, merge, edit,')
            print(' disambiguate, resolve, matches, help')
            if cmd != 'help':
                exit(1)

    def disambiguate(self, target, tags):
        c = self.d.getcursor()
        ifis = tuple(c.execute(
            'select inventory_found_id'
            ' from'
            '  inventory_found'
            '  natural join ('
            '   select title_id, format_id'
            '    from inventory_found where'
            '     inventory_id = %s and found_tag in %s'
            '      and resolving_id is null'
            '     group by title_id, format_id having count(title_id) > 1'
            '   ) aggro'
            ' where inventory_id=%s and found_tag in %s',
            (self.inventory_id, tuple(tags), self.inventory_id, tuple(tags))))
        fromtags = list(c.execute(
            'select distinct found_tag from inventory_found'
            ' where inventory_found_id in %s',
            (ifis,)))
        for tag in fromtags:
            writedex(
                '%s.dis.%s' % (self.inventory_code, tag),
                'Duplicate books from %s (%s)' % (tag, self.inventory_code),
                [
                    DexLine(
                        Title(
                            self.d, title_id), codes={fmtcode(fmt): count})
                    for title_id, fmt, count in c.execute(
                        'select title_id, format, count(format)'
                        ' from inventory_found natural join format'
                        ' where inventory_found_id in %s and found_tag=%s'
                        ' group by title_id, format',
                        (ifis, tag,))])
        c.execute(
            'update inventory_found set found_tag=%s'
            ' where inventory_found_id in %s',
            (target, ifis))
        self.commit()

    def candidates(self, tags, title_id, shelfcode_id):
        c = self.d.getcursor()
        return list(c.execute(
            'select inventory_found_id, format, found_tag'
            ' from inventory_found natural join format'
            ' where'
            '  inventory_id = %s'
            '  and found_tag in %s'
            '  and title_id = %s'
            '  and format_id in'
            '    (select format_id from shelfcode_format'
            '     where shelfcode_id=%s)'
            '  and resolving_id is null',
            (self.inventory_id, tuple(tags), title_id, shelfcode_id)))

    def missing(self, shelfcode_types):
        c = self.d.getcursor()
        return list(c.execute(
            'select'
            '  inventory_entry.inventory_entry_id, inventory_entry.title_id,'
            '  shelfcode_id, shelfcode, missing_count'
            ' from'
            '  inventory_missing'
            '  natural join inventory_entry'
            '  natural join shelfcode'
            '  left join inventory_found'
            '   on inventory_entry.inventory_entry_id = resolving_id'
            ' where'
            '  inventory_entry.inventory_id = %s'
            '  and missing_count > 0'
            '  and shelfcode_type in %s'
            ' group by'
            '  inventory_entry.inventory_entry_id, missing_count,'
            '  shelfcode_id, shelfcode'
            ' having count(resolving_id) < missing_count',
            (self.inventory_id, tuple(shelfcode_types))))

    def matches(self, types, tags):
        print('matches for', types, 'shelfcodes from', tags)
        for ied, title_id, shelfcode_id, shelfcode, count \
                in self.missing(t.upper() for t in types.split(',')):
            candles = self.candidates(tags, title_id, shelfcode_id)
            if not candles:
                continue
            candles = [
                list(g) for (k, g) in itertools.groupby(
                    y[1:] for y in candles)]
            candles = [(len(x), x[0][0], x[0][1]) for x in candles]
            print(DexLine(
                Title(self.d, title_id),
                codes={shelfcode: -count}))
            for (n, fmt, tag) in candles:
                print(' ', n, fmt, tag)

    def resolve(self, shelfcode_types, tags):
        c = self.d.getcursor()

        unserved_shelfcodes = list(c.execute(
            'select distinct shelfcode'
            ' from inventory_entry'
            '  natural join inventory_missing'
            '  natural join shelfcode'
            '  natural left join shelfcode_format'
            ' where inventory_id=%s and format_id is null'
            ' order by shelfcode',
            (self.inventory_id,)
            ))

        if unserved_shelfcodes:
            print('SHELFCODES WITHOUT SPECIFIED FORMATS DETECTED')
            print()
            print("(Go tell the avatar of libcomm if you ain't they)")
            print("((If you are they, what are you standing there for?))")
            print()
            print(' '.join(sorted(unserved_shelfcodes)))
            raise Exception('Eldritch Horror detected, bailing...')

        format_shelfcode = {
            fmt: set(shelfcodes)
            for (fmt, shelfcodes) in c.execute(
                'select format, array_agg(shelfcode)'
                ' from format'
                '  natural join shelfcode_format'
                '  natural join shelfcode'
                ' group by format'
                )}

        shelfcode_ids = dict(c.execute(
            'select shelfcode, shelfcode_id from shelfcode'))

        missing = self.missing(shelfcode_types)

        pulls = {}

        for shelfcode_type in shelfcode_types:  # in order
            for iei, title_id, shelfcode_id, shelfcode, count in missing:
                candidates = self.candidates(tags, title_id, shelfcode_id)
                elect = candidates[:count]
                if not elect:
                    continue
                print('missing', count, 'of', title_id, 'in', shelfcode)
                print('found', len(elect))
                for ifi, fmt, tag in elect:
                    c.execute(
                        'update inventory_found set resolving_id=%s'
                        ' where inventory_found_id=%s',
                        (iei, ifi))
                    pulls.setdefault(tag, []).append(
                        DexLine(
                            Title(self.d, title_id),
                            codes={shelfcode: 1}))

        print('looking for strays')
        # XXX horriblifying kludge
        # This doesn't currently do anything with books that have previously
        # entirely fallen out of the library; it really should.
        if 'C' in shelfcode_types:
            missing = self.missing(('C'))
            limit_set = tuple(c.execute(
                'select title_id from inventory_found'
                ' where inventory_id=%s and resolving_id is null',
                (self.inventory_id,)))
            needy = list(c.execute(
                'select title_id, c - coalesce(s, 0) as t'
                ' from ('
                'select title_id, count(book_id) as c'
                ' from book natural join shelfcode'
                ' where'
                "  shelfcode_type='C' and title_id in %s and not withdrawn"
                ' group by title_id'
                ') currently natural left join ('
                'select title_id, sum(missing_count) as s'
                ' from inventory_entry'
                '  natural join inventory_missing'
                ' where title_id in %s'
                '  and inventory_id=%s'
                ' group by title_id'
                ') inventoried'
                ' where (c - coalesce(s,0)) < 2',
                (limit_set, limit_set, self.inventory_id)))

            for title_id, have in needy:
                candidates = list(c.execute(
                    'select inventory_found_id, format, found_tag'
                    ' from inventory_found natural join format'
                    ' where inventory_id=%s'
                    '  and title_id=%s and resolving_id is null'
                    ' limit %s',
                    (self.inventory_id, title_id, max(2 - have, 0))))
                sniff_shelfcodes = list(c.execute(
                    'select distinct shelfcode from'
                    ' shelfcode'
                    ' natural join book'
                    ' where title_id=%s', (title_id,)))
                for shelfcode in sniff_shelfcodes:
                    target_shelfcodes = None
                    if shelfcode in shelfcode_hint:
                        target_shelfcodes = shelfcode_hint[shelfcode]
                    else:
                        print(shelfcode, '?')
                if target_shelfcodes is None:
                    print("Can't pick targets for", title_id, sniff_shelfcodes)
                    # continue
                for ifi, fmt, tag in candidates:
                    try:
                        shelfcode_set = (
                            format_shelfcode[fmt] & target_shelfcodes)
                    except:
                        print('format_shelfcode[fmt]', format_shelfcode[fmt])
                        print('target_shelfcodes', target_shelfcodes)
                        raise
                    if not shelfcode_set:
                        print("can't", ifi, fmt, target_shelfcodes)
                        continue
                    shelfcode = list(shelfcode_set)[0]
                    c.execute(
                        'update inventory_found'
                        ' set resolving_id=%s'
                        ' where inventory_found_id=%s',
                        (shelfcode_ids[shelfcode], ifi))
                    pulls.setdefault(tag, []).append(
                        DexLine(
                            Title(self.d, title_id),
                            codes={shelfcode: 1}))

        for tag in pulls:
            writedex(
                '%s.shelve.%s' % (self.inventory_code, tag),
                'Books to shelve from %s (%s)' % (tag, self.inventory_code),
                sorted(pulls[tag]))

        self.commit()

    def editor_state(self, tag):
        return list(sorted((
            DexLine(
                Title(self.d, title_id),
                codes={fmtcode(fmt): 1}),
            fmt,
            inventory_found_id,
            ) for inventory_found_id, title_id, fmt in
            self.d.getcursor().execute(
                'select inventory_found_id, title_id, format'
                ' from inventory_found natural join format'
                ' where inventory_id=%s and found_tag=%s'
                '  and resolving_id is null',
                (self.inventory_id, tag))))

    def editor_print(self, state):
        for (n, (line, fmt, _)) in state:
            print('%d. %s %s' % (n, fmt, line))

    def editor_help(self):
        print("""
        ? print this
        a add a book
        d delete a book
        o print contents in insertion order
        p print contents
        r resolve a book to a missing entry
        s shelve a book without resolving
        q quit""")

    def edit(self, tag):
        formats = dict(self.d.cursor.execute(
            'select format, format_id from format'))
        shelfcodes = dict(self.d.cursor.execute(
            'select shelfcode, shelfcode_id from shelfcode'))
        state = None
        warned = False

        while True:
            c = read(
                'action [?adopqrs]: ', history='cmd').strip().lower()

            if c == 'q':
                break
            elif c == 'p':
                state = self.editor_state(tag)
                self.editor_print(enumerate(state))
            elif c == 'o':
                state = self.editor_state(tag)
                self.editor_print(
                    sorted(enumerate(state), key=lambda x: x[1][2]))
            elif c == 'a':
                title = specify(self.d)
                if not title:
                    continue
                title = DexLine(title, codes={})
                print(title)
                fmt = read(
                    'Format? ',
                    callback=formats.iterkeys,
                    history='format',
                    ).strip().upper()
                if not fmt:
                    continue
                self.d.getcursor().execute(
                    'insert into inventory_found('
                    ' inventory_id, title_id, format_id, found_tag'
                    ') values (%s, %s, %s, %s)',
                    (self.inventory_id, title.title_id, formats[fmt], tag))
                self.commit()
                print('added', fmt, title)
            elif c == 'd':
                if state is None:
                    print("Don't delete things blind.")
                    continue
                count = len(state)
                if not count:
                    print('Nothing to delete')
                    continue
                n = readnumber(
                    'Delete (0-%d)? ' % (count - 1,), 0, count, history='n')
                if n is None:
                    continue
                c = self.d.getcursor()
                c.execute(
                    'delete from inventory_found where inventory_found_id=%s',
                    (state[n][2],))
                if c.rowcount:
                    print('deleted', n, state[n][0])
                self.commit()
                if not warned:
                    print("warning, we don't renumber until you print")
                    warned = True
            elif c == 'r':
                if state is None:
                    print("Don't resolve things blind.")
                    continue
                count = len(state)
                if not state:
                    print('Nothing to resolve')
                    continue
                n = readnumber(
                    'Resolve (0-%d)? ' % (count - 1,), 0, count, history='n')
                if n is None:
                    continue
                line, fmt, found_id = state[n]
                c = self.d.getcursor()
                positions = list(c.execute(
                    'select distinct'
                    '  inventory_entry.inventory_entry_id, '
                    '  shelfcode,'
                    '  missing_count'
                    ' from'
                    '  inventory_entry'
                    '  natural join inventory_missing'
                    '  natural join shelfcode'
                    '  natural join shelfcode_format'
                    '  natural join format'
                    ' where'
                    '  inventory_id = %s'
                    '  and format = %s'
                    '  and title_id = %s',
                    (self.inventory_id, fmt, line.title_id)))
                count = len(positions)
                if not positions:
                    print('no matches')
                    continue
                for (m, (iei, shelfcode, missing_count)) \
                        in enumerate(positions):
                    print('%d. %s %d' % (n, shelfcode, missing_count))
                m = readnumber(
                    'Entry (0-%d)? ' % (count - 1,), 0, count, history='m')
                if m is None:
                    continue
                c.execute(
                    'update inventory_found set resolving_id=%s'
                    ' where inventory_found_id=%s',
                    (positions[m][0], found_id))
                self.commit()
            elif c == 's':
                if state is None:
                    print("Don't shelve things blind.")
                    continue
                count = len(state)
                if not state:
                    print('Nothing to shelve')
                    continue
                n = readnumber(
                    'Shelve (0-%d)? ' % (count - 1,), 0, count, history='n')
                if n is None:
                    continue
                line, fmt, found_id = state[n]
                c = self.d.getcursor()
                shelfcode = read(
                    'Shelfcode? ', callback=shelfcodes.iterkeys,
                    history='shelfcode',
                    ).strip().upper()
                if not shelfcode:
                    continue
                if shelfcode not in shelfcodes:
                    print('Unknown shelfcode', shelfcode)
                    continue
                c.execute(
                    'update inventory_found set resolving_id=%s'
                    ' where inventory_found_id=%s',
                    (shelfcodes[shelfcode], found_id))
                self.commit()
            else:
                self.editor_help()


# should really be factored into DexLine
def nicetitle(line):
    series = [i.replace(',', r'\,') for i in line.series if i]

    # strip the sortbys
    titles = [('=' in i and i[:i.find('=')] or i) for i in line.titles]

    if series:
        if len(series) == len(titles):
            titles = ['%s [%s]' % i for i in zip(titles, series)]
        elif len(titles) == 1:
            titles = ['%s [%s]' % (titles[0], '|'.join(series))]
        elif len(series) == 1:
            titles = ['%s [%s]' % (i, series[0]) for i in titles]
        else:  # this is apparently Officially Weird
            print('Wacky title/series match: ', str(line))
            ntitles = ['%s [%s]' % i for i in zip(titles, series)]
            if len(line.series) < len(titles):
                ntitles += titles[len(series):]
            titles = ntitles
    return '|'.join(titles)


def writedex(dexname, longname, books):
    fname = dexname + '.tex'
    print('Writing', fname)
    with open(fname, 'w') as fp:
        fp.write(r'\def\dexname{%s}' % (dexname))
        fp.write("\n")
        fp.write(r'\def\Reverse{1}')
        fp.write("\n")
        fp.write(r'\def\Shelf{1}')
        fp.write("\n")
        fp.write(r'\def\Supple{%s}' % (longname))
        fp.write("\n")
        fp.write(r'\def\Period{3}')
        fp.write("\n")
        fp.write(r'\input %s/dextex-current.tex' % (
            TEXBASE))
        fp.write("\n")
        for line in books:
            code = r' {\bf %s}' % (list(line.codes.keys())[0])
            count = list(line.codes.values())[0]
            fp.write(r'\Book{%s}{%s}{%s}' % (
                texquote(line.authortxt),
                texquote(nicetitle(line)) + code,
                count))
            fp.write("\n")

        fp.write(r'\vfill \eject \bye')
        fp.write("\n")


if __name__ == '__main__':
    Main()()
