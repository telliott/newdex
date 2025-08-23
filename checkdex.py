#!/usr/bin/python

import sys
import time

from mitsfs.dexdb import DexDB, Title
from mitsfs.dexfile import DexLine
from mitsfs.tex import TEXBASE, texquote
from io import open


def main():
    d = DexDB()
    c = d.getcursor()
    for member in sys.argv[1:]:
        c.execute(
            'select member_id from member_name where member_name=%s',
            (member.upper(),))
        if c.rowcount == 0:
            print ("Didn't find an entry for %s\n" % member)
            continue
        member_id = c.fetchone()[0]  
        c.execute(
            'select title_id, shelfcode'
            ' from'
            '  checkout'
            '  natural join checkout_member'
            '  natural join book'
            '  natural join shelfcode'
            ' where member_id=%s and checkin_stamp is null',
            (member_id,))
        titles = c.fetchall()
        
        books = sorted([
            DexLine(Title(d, title_id), codes={shelfcode: 1})
            for (title_id, shelfcode) in titles])
        writedex(
            'checkouts.%s' % (member,),
            'Checkout out books to %s as of %s' % (
                member, time.strftime('%Y%m%d')),
            books)


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
        fp.write(r'\input %s/dextex-current.tex' % (TEXBASE))
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


if __name__ == '__main__':
    main()
