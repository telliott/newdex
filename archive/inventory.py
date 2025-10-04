#!/usr/bin/python

import datetime
import optparse

from mitsfs.inventory import Inventory
from mitsfs.dexdb import DexDB
from mitsfs.dexfile import Dex, DexLine
from mitsfs.core.settings import DATABASE_DSN
from mitsfs.util.ui import tabulate
from mitsfs.dex.titles import Title

CLOSING_GLOSS = """
If you still need to check in the new shelf:

begin;
update checkout
 set checkin_stamp=current_timestamp
 from checkout_member
  natural join member
  natural join member_name
 where checkout.checkout_id = checkout_member.checkout_id
  and pseudo
  and member_name='NEWSHELF'
  and checkin_stamp is null;

"""


def main():
    parser = optparse.OptionParser(
        usage='usage: %prog [--dsn dsn] command [args ...]', version='%prog 0')
    parser.add_option(
        '--dsn', dest='dsn', help='database DSN', default=DATABASE_DSN)
    parser.add_option(
        '-I', '--inventory', dest='inventory', help='inventory code')

    options, args = parser.parse_args()

    d = DexDB(dsn=options.dsn)

    inventory = Inventory(d, options.inventory)

    inventory_code = inventory.code
    inventory_id = inventory.id
    inventory_desc = inventory.desc
    inventory_closed = inventory.closed

    c = d.getcursor()

    print('%s (%s)' % (inventory_desc, inventory_code))

    id_shelfcode = dict(c.execute(
        'select shelfcode_id, shelfcode from shelfcode'))

    if args and args[0] == 'commit' and len(args) == 1:
        if inventory_closed is not None:
            print('tooooo laaaaate')
            return

        leaving = compute_leaving(d, inventory_id, c, id_shelfcode)
        c.execute(
            'update book set withdrawn=true where book_id in %s',
            (tuple(leaving),))

        print(c.rowcount, 'books withdrawn')

        c.execute(
            'insert into book(shelfcode_id, title_id)'
            ' select shelfcode_id, title_id'
            '  from shelfcode'
            '   join inventory_found on resolving_id=shelfcode_id'
            '  where inventory_id=%s',
            (inventory_id,))

        print(c.rowcount, 'books added')

        c.execute(
            'update inventory'
            ' set inventory_closed=now() where inventory_id=%s',
            (inventory_id,))

        d.db.commit()
        print(CLOSING_GLOSS)
    elif args and args[0] == 'diff' and len(args) == 1:
        leaving = compute_leaving(d, inventory_id, c, id_shelfcode)
        if not leaving:
            print("No books scheduled to leave")
            exit(1)
        dex = Dex(zerok=True, source=(
            DexLine(Title(d, title_id), codes={shelfcode: -1})
            for (title_id, shelfcode) in
            c.execute(
                'select title_id, shelfcode'
                ' from book natural join shelfcode'
                ' where book_id in %s',
                (tuple(leaving),))))
        dex.merge(
            DexLine(Title(d, title_id), codes={shelfcode: 1})
            for (title_id, shelfcode) in
            c.execute(
                ' select title_id, shelfcode'
                '  from shelfcode'
                '   join inventory_found on resolving_id=shelfcode_id'
                '  where inventory_id=%s',
                (inventory_id,)))
        print(dex)
    elif args and args[0] == 'list':
        print(tabulate(
            [['CODE', 'DESCRIPTION', 'OPEN', 'CLOSE']] +
            list(c.execute(
                'select inventory_code, inventory_desc, inventory_stamp,'
                '  inventory_closed'
                ' from inventory order by inventory_stamp'))))
    elif args and args[0] == 'dropout':
        WEEKS = 12
        cutoff = datetime.datetime.now() - datetime.timedelta(weeks=WEEKS)
        if inventory.opened.replace(tzinfo=None) > cutoff:
            print('selected inventory date', inventory.opened, 'is more recent')
            print('than arbitrary cutoff', cutoff)
            exit(1)
        (count,) = c.execute(
            'select count(book_id)'
            ' from book'
            '  natural join checkout'
            '  join inventory'
            '  on inventory_id=%s'
            ' where not withdrawn'
            '  and checkin_stamp is null'
            '  and checkout_stamp < inventory_stamp',
            (inventory.id,))
        print('will withdraw', count, 'books that have been checked out since')
        print('before', inventory.opened)
        c.execute(
            'update book'
            ' set withdrawn=true'
            ' from checkout'
            '  join inventory on inventory_id=%s'
            ' where'
            '  book.book_id = checkout.book_id and'
            '  not withdrawn and'
            '  checkin_stamp is null and'
            '  checkout_stamp < inventory_stamp',
            (inventory.id,))
        if c.rowcount != count:
            print('updated', c.rowcount, 'which is not', count, 'rolling back')
            d.db.rollback()
        else:
            d.db.commit()
            print('done')
    else:
        print('''
        inventory commit
        inventory diff
        inventory list
        inventory -I old-inventory dropout
        inventory help
        ''')


def compute_leaving(d, inventory_id, c, id_shelfcode):
    missing = list(c.execute(
        'select'
        '  inventory_entry.inventory_entry_id,'
        '  inventory_entry.title_id, shelfcode_id, shelfcode, missing_count'
        ' from'
        '  inventory_missing'
        '  natural join inventory_entry'
        '  natural join shelfcode'
        '  left join inventory_found'
        '   on inventory_entry.inventory_entry_id = resolving_id'
        ' where'
        '  inventory_entry.inventory_id = %s'
        '  and missing_count > 0'
        ' group by'
        '  inventory_entry.inventory_entry_id, missing_count,'
        '  shelfcode_id, shelfcode'
        ' having count(resolving_id) < missing_count',
        (inventory_id,)))

    leaving = []

    for iei, title_id, shelfcode_id, shelfcode, count in missing:
        candidates = list(c.execute(
            'select book_id'
            ' from'
            '  book'
            ' where'
            '  title_id=%s and shelfcode_id=%s and not withdrawn'
            '  and book_id not in ('
            '   select book_id from checkout where checkin_stamp is null'
            '  )'
            ' limit %s',
            (title_id, shelfcode_id, count)))
        if len(candidates) < count:
            print('%d: %d missing, %d candidates %s' % (
                iei, count, len(candidates), DexLine(
                    Title(d, title_id), codes={
                        id_shelfcode[shelfcode_id]: count})))
        leaving += candidates

    return leaving


if __name__ == '__main__':
    main()
