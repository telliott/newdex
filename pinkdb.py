#!/usr/bin/python
'''Print a pinkdex.'''


import optparse
import os
import re
import sys
import time

from io import open
from functools import reduce

from mitsfs.core.settings import DATABASE_DSN
from mitsfs.constants import DEXBASE
from mitsfs.dexdb import DexDB
from mitsfs.inventory import Inventory, InventoryUnknown
from mitsfs.tex import TEXBASE, texquote
from mitsfs.dexfile import Dex, DexLine
from mitsfs.dex.editions import Edition, InvalidShelfcode
from mitsfs.dex.titles import Title

__version__ = '0'


parser = optparse.OptionParser(
    usage='usage: %prog [--datadex file]',
    version='%prog ' + __version__)
parser.add_option(
    '-p', '--predicate', dest='predicate',
    help='SQL predicate for dex', default=None)
parser.add_option(
    '-S', '--shelfcode', dest='shelfcodes', action='append',
    help='Make a shelfdex', default=[])
parser.add_option(
    '-s', '--supplement', dest='suppl',
    help='supplementary dex', default=None)
parser.add_option(
    '-o', '--outfile', dest='outfile',
    help='Output file', default=None)
parser.add_option(
    '-a', '--add', dest='add',
    help='Datadex format file to merge')
parser.add_option(
    '-H', '--hassle', action='store_true', dest='hassle',
    help="Stick other holdings in shelfdex for HassleComm's convenience")
parser.add_option(
    '-i', '--inventory', dest='inventory',
    help='Specify inventory tag')
parser.add_option(
    '-I', '--inventory-description', dest='inventory_desc',
    help='Specify inventory display name if initializing an inventory tag')
parser.add_option(
    '-d', '--directory', dest='directory',
    help='Specify target directory')
parser.add_option(
    '-D', '--downcase', action="store_true", dest='downcase', default=False,
    help='Attempt to downcase the dex')
parser.add_option(
    '-T', '--textdex', action="store_true", dest='textdex', default=False,
    help='print the searchable text dex')
parser.add_option('-K', '--boxdex', type='int', dest='boxdex')
parser.add_option(
    '--dsn', dest='dsn',
    default=os.environ.get('MITSFS_DSN') or DATABASE_DSN)
parser.add_option('--stop', dest='stop', action='store_true')
options, args = parser.parse_args()

noboxed = False

d = DexDB(dsn=options.dsn)

if options.inventory:
    try:
        inventory = Inventory(
            d, options.inventory, options.inventory_desc)
    except InventoryUnknown as e:
        print('Unknown inventory %s;' % e.code)
        print('Please supply a description with -I so we can initialize it.')
        sys.exit(1)
else:
    inventory = None

if options.stop:
    exit(0)

if options.directory:
    if not os.path.isdir(options.directory):
        os.mkdir(options.directory)
    os.chdir(options.directory)

if os.getcwd() == DEXBASE:
    print('Preemptively changing directory to /tmp;')
    print('look for your pinkdexen there.')
    os.chdir('/tmp')


def titlecase(s):
    if options.downcase:
        return re.sub(
            '\'([SDT]|Ll|Re)([^A-Z]|$)',
            lambda m: m.group(0).lower(),
            s.title())
    else:
        return s


def nicetitle(line):
    series = [titlecase(i.replace(',', r'\,')) for i in line.series if i]
    titles = [  # strip the sortbys
        titlecase('=' in i and i[:i.find('=')] or i) for i in line.titles]
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


def book(line):
    if noboxed:
        unboxed = [
            edition
            for edition in line.codes.values()
            if DexDB.codes[edition.shelfcode].get('box') not in ('all', 'kbx')]
        nboxed = [
            edition
            for edition in line.codes.values()
            if DexDB.codes[edition.shelfcode].get('box') == 'all']
        if unboxed:
            codes = ','.join((str(edition) for edition in unboxed))
        elif nboxed:
            codes = r'\[' + ','.join((str(edition)
                                      for edition in nboxed)) + r'\]'
        else:
            codes = '*'
    else:
        codes = str(line.codes).replace(':', r'\:')
    args = [
        texquote(i)
        for i in [titlecase(line.authortxt), nicetitle(line), codes]]
    return r'\Book' + ''.join(['{%s}' % i for i in args])


nwords = {
    '0': 'zero', '1': 'one', '2': 'two', '3': 'three',
    '4': 'four', '5': 'five', '6': 'six', '7': 'seven',
    '8': 'eight', '9': 'nine'}


def dobar(n):
    return r'\barA' + ''.join([r'\bar' + nwords[i] for i in str(n)]) + r'\barA'


def progress_meter(it, divisor=1000):
    count = 0
    for i in it:
        if count % divisor == 0:
            print(count)
        count += 1
        yield i


def mungedex(query=None, args=[], add=None):
    # select distinct title_id from title natural join book where not withdrawn
    print('constructing subset:')
    print(query) 
    dl = list(progress_meter(d.iter(query, args)))
    lines = []
    
    for i in progress_meter(dl):
        try:
            lines.append(DexLine(i))
        except InvalidShelfcode as e:
            print(str(e) + '-' + str(i.title_id))
            continue
        
    #dl = [DexLine(i) for i in progress_meter(dl)]
    if add:
        dex = Dex(dl)            
        print('adding %s...' % add)
        sys.stdout.flush()
        dex.merge(Dex(add))
        dl = list(dex)
        print('done.')

    return dl


def mungeshelf(shelfcodes):
    # select distinct title_id, count(book_id) from title natural join book
    # where not withdrawn ... group by title_id
    query = (
        'select title_id, book_series_visible, doublecrap, count(book.book_id)'
        ' from book natural join shelfcode'
        '  left join checkout on book.book_id = checkout.book_id'
        ' and checkin_stamp is null'
        ' where not withdrawn'
        '  and (' + ' or '.join(['shelfcode=%s'] * len(shelfcodes)) + ')'
        '  and checkout_stamp is null'
        ' group by title_id, book_series_visible, doublecrap')
    query = (
        'select title_id, book_series_visible, doublecrap, count(book.book_id)'
        ' from book natural join shelfcode'
        ' where not withdrawn'
        '  and (' + ' or '.join(['shelfcode=%s'] * len(shelfcodes)) + ')'
        ' group by title_id, book_series_visible, doublecrap')
    args = shelfcodes
    print('mungeshelf', query)

    def constructor(id, bsv, dc, c):
        es = ('@' if bsv else '') + shelfcodes[0] + (dc if dc else '')
        t = Title(d, id)
        dl = DexLine(
            authors=t.authors_tuple, titles=t.titles, series=t.series_tuple, codes={es: c})
        dl.othercount = sum(t.codes[i] for i in shelfcodes[1:])
        return dl.shelfkey(es), dl

    print('constructing subset:')
    dl = list(progress_meter(
        constructor(id, bsv, dc, c)
        for id, bsv, dc, c in d.getcursor().execute(query, args)))
    print('sorting:')
    dl.sort(key=lambda x: x[0])
    print('done.')

    return [i[1] for i in dl]


def writetext(outfile, books):
    if outfile is None:
        outfile = 'pinkdex.txt'
    fp = open(outfile, 'w')

    for line in books:
        try:
            fp.write(str(line) + "\n")
        except InvalidShelfcode:
            continue
    fp.close()
    print('done.')
    

def writedex(
        outfile, books, shelfcode=None, suppl=None, hassle=None, reverse=False,
        dexname='Pinkdex', letterfield='placeauthor', blob=None, kbx=None):
    if suppl:
        if shelfcode:
            suppl += ' (%s)' % shelfcode
        elif kbx:
            suppl += ' (KBX%s)' % kbx
    elif shelfcode:
        suppl = shelfcode
    elif kbx:
        suppl = 'KBX%s' % kbx
    print('writing', suppl, '...')
    sys.stdout.flush()
    if outfile is None:
        outfile = 'pinkdex.tex'
    fp = open(outfile, 'w')
    fp.write(r'\def\dexname{%s}' % dexname)
    fp.write("\n")
    if kbx:
        fp.write(r'\def\Box{1}' + "\n")
    if shelfcode or kbx:
        fp.write(r'\def\Reverse{1}' + "\n")
        fp.write(r'\def\Shelf{1}' + "\n")
    elif reverse:
        fp.write(r'\def\Reverse{}' + "\n")
    if suppl:
        fp.write(r'\def\Supple{%s}' % suppl)
        fp.write("\n")
        fp.write(r'\def\Period{3}' + "\n")
    else:
        fp.write(r'\def\Period{0}' + "\n")
    fp.write(r'\input %s/dextex-current.tex' % TEXBASE)
    fp.write("\n")

    if blob:
        fp.write(blob)
        fp.write("\n")
    letter = None

    for line in books:        
        newletter = None
        if (len(getattr(line, letterfield)) > 0): 
            newletter = getattr(line, letterfield).upper()[0]
            
        if letter != newletter:
            if letter is not None and not suppl:
                fp.write(r'\NextLetter' + "\n")
            letter = newletter
            print(letter)
            sys.stdout.flush()
        if shelfcode or kbx:
            if hassle:
                codes = ' [%s]' % str(line.codes).replace(':', r'\:')
            else:
                codes = ''
            if kbx is None:
                count = line.codes[shelfcode]
            else:
                # bleah
                count = sum([
                    line.codes[i].count
                    for i in line.codes
                    if i.shelfcode == str(kbx)])
            if inventory:
                inventory.add(line, count)

            fp.write('\\Book{%s}{%s}{%s} %% %s' % (
                texquote(titlecase(line.authortxt)),
                texquote(nicetitle(line)) + codes,
                count, str(line)))
            fp.write("\n")
        else:
            fp.write(book(line) + "\n")
    fp.write(r'\vfill \eject \bye' + "\n")
    fp.close()
    print('done.')

print ("INVENTORY: %s" % inventory)
if (not inventory) or options.shelfcodes:
    args = []
    query = ''

    if options.predicate:
        query += ' and ' + options.predicate

    if options.boxdex is not None:
        print('boxdex #', options.boxdex)
        query += " and shelfcode like 'KBX%%' and doublecrap=%s"
        args.append(str(options.boxdex))
    elif options.shelfcodes:
        shelfqueries = []
        shelfargs = []
        for code in options.shelfcodes:
            edition = Edition(code)
            q = 'shelfcode = %s'
            shelfargs.append(edition.shelfcode)
            if edition.series_visible:
                q += ' and book_series_visible'
            if edition.double_info:
                q += ' and doublecrap=%s'
                shelfargs.append(edition.double_info)
            shelfqueries.append('(' + q + ')')
        query += ' and (' + ' or '.join(shelfqueries) + ') '
        args += shelfargs
    else:
        query += " and position('KBX' in shelfcode) = 0"  # filter out KBXen

    if options.predicate:
        query += ' and ' + options.predicate

    if options.shelfcodes and False:
        books = mungeshelf(options.shelfcodes)
    else:
        query = (
            'select distinct title_id'
            ' from title natural join book natural join shelfcode'
            ' where not withdrawn' + query)
        books = mungedex(query, args, options.add)
        print('sorting dex for pinkdex...')
        sys.stdout.flush()
        books.sort(key=lambda line: (line.placeauthor, line.placetitle))
        print('done.')

    if options.textdex:
        writetext(options.outfile, books)
    else:
        writedex(
            options.outfile, books,
            options.shelfcodes[0] if options.shelfcodes else None,
            options.suppl, options.hassle, kbx=options.boxdex)

    if not options.outfile and not options.shelfcodes \
        and not options.textdex and not options.boxdex:
        print('sorting dex for titledex...')
        sys.stdout.flush()
        books.sort(key=lambda line: (line.placetitle, line.placeauthor))
        print('done.')
        writedex(
            'titledex.tex', books, reverse=True, dexname='Titledex',
            letterfield='placetitle')

        print('filtering for seriesdex...')
        books = [i for i in books if i.series]
        print('done. (%d entries)' % len(books))
        print('sorting for seriesdex...')
        books.sort(
            key=lambda line: (
                line.placeseries, line.placetitle, line.placeauthor))
        print('done.')

        print('generating serieslist...')
        sl = [r'\beginserieslist']
        for s in d.indices.series.iterkeys():
            dl = [DexLine(i) for i in d.indices.series[s]]
            sl.append(r'  \Series{%s}{%s}{%d}' % (
                texquote(s),
                texquote(
                    reduce(
                        lambda a, b: a and b,
                        # are all the authors the same?
                        [line.authors == dl[0].authors for line in dl]) and
                    dl[0].authortxt or 'authorship varies'),
                len(dl)
                ))
        sl.append(r'\endserieslist')
        print('done')

        writedex(
            'seriesdex.tex', books, reverse=True, dexname='Seriesdex',
            letterfield='placeseries', blob='\n'.join(sl))
else:  # inventory
    timestart = time.time()
    print('; inventory', inventory.code, 'run begins', time.ctime(timestart))
    try:
        print('computing', inventory.code, '...',)
        sys.stdout.flush()
        inventory.compute()
        print('done. (%.2f sec)' % (time.time() - timestart))
        codes = list(inventory.codes())
        print ("CODES: %s" % str(codes)) 
        print('Generating shelfdexes for', ' '.join(codes))
        for shelfcode in codes:
            print()
            print('Generating shelfdex for', shelfcode)
            divisions = list(d.cursor.execute(
                'select title_id'
                ' from shelf_divisions natural join shelfcode'
                '  natural join title_responsibility natural join entity '
                ' where inventory_id=%s and shelfcode=%s'
                '  and order_responsibility_by = 0 order by entity_name',
                (inventory.id, shelfcode)))
            if divisions:
                print('Shelf divisions:')
                divisions = [Title(d, i) for i in divisions]
                for number, line in enumerate(divisions):
                    print(line)
                    divisions[number] = \
                        DexLine(line).shelfkey(shelfcode)
                slices = list(zip([None] + divisions, divisions + [None]))

            shelf = list(progress_meter(inventory.shelf(shelfcode)))

            if not shelf:
                print('empty shelfcode; punting')
                continue

            print('sorting %s...' % shelfcode,)
            sys.stdout.flush()
            shelf.sort(key=lambda tup: tup[0])
            print('done.')

            slices = []
            if divisions:
                diviter = iter(divisions)
                terminus = next(diviter)
                print('slicing:')
                for (coordinate, (key, line)) in enumerate(
                        progress_meter(shelf)):
                    if key > terminus:
                        slices.append(coordinate)
                        try:
                            terminus = next(diviter)
                        except StopIteration:
                            break

            if slices:
                slices = [('%s.%02d' % (shelfcode, count + 1), rng)
                          for (count, rng)
                          in enumerate(
                              zip([0] + slices, slices + [len(shelf)]))]
            else:
                slices = [(shelfcode, (0, len(shelf)))]

            slices = [(packet, (start, end))
                      for (packet, (start, end)) in slices
                      if start != end]

            for (packet, (start, end)) in slices:
                inventory.packet(packet, shelfcode)
                print('shelfdex:', packet)
                print(start, shelf[start][1])
                print(end, shelf[end - 1][1])

                outfile = 'shelfdex-%s.%s.tex' % (
                    inventory.code, packet.replace('/', '-'))

                writedex(
                    outfile, (shelf[i][1] for i in range(start, end)),
                    shelfcode, inventory.desc + ' ' + packet, None)
            print('writing packet order')
            inventory.click()
    finally:
        timeend = time.time()
        print(';')
        print('; inventory', inventory.code, 'run ends', time.ctime(timeend))
        print('; duration %.2f seconds' % (timeend - timestart))
        print(';')
