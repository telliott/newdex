#!/usr/bin/python

import sys

from mitsfs.ui import read
from mitsfs.dexdb import DexDB, Title
from mitsfs.dexfile import DexLine
from mitsfs.library import DATABASE_DSN
from mitsfs.dex.Shelfcodes import Shelfcodes




def main():
    d = DexDB(dsn=DATABASE_DSN)
    shelfcodes = Shelfcodes(d)

    if len(sys.argv) == 1:
        ((inventory_code, inventory_id, inventory_desc),) = d.cursor.execute(
            'select inventory_code, inventory_id, inventory_desc'
            ' from inventory order by inventory_stamp desc limit 1')
    else:
        _, inventory_code = sys.argv
        ((inventory_id, inventory_desc),) = d.cursor.execute(
            'select inventory_id, inventory_desc'
            ' from inventory where inventory_code = %s',
            (inventory_code,))

    print('%s (%s)' % (inventory_desc, inventory_code))

    while True:
        shelfcode = read(
            'Shelfcode (q to quit)? ',
            callback=d.codes.keys,
            history='shelfcode',
            ).upper().strip()

        if not shelfcode or shelfcode.strip().lower() == 'q':
            break

        code = shelfcodes[shelfcode].code
        if not code:
            print('Unknown shelfcode')
            continue

        print(code)

        title = None
        print()
        c = d.cursor.execute(
            'select title_id, count(*) from title natural join book'
            ' natural join shelfcode where not withdrawn '
            'and shelfcode = %s group by title_id having count(*) > 1',
            (shelfcode,))

        books = [Title(d, x) for (x, _) in c.fetchall()]
        books.sort(key=lambda line: (line.placeauthor, line.placetitle))
        for (title) in books:
            print(title)

            try:
                mstr = read(
                    'How many culled? ', history='count').strip()
                if mstr in ('','0'):
                    continue
                missing = int(mstr)
            except (ValueError, KeyboardInterrupt):
                print('?')
                continue

            print("removing 1")

            if missing >= 0:
                print(title.title_id, missing, title)
                ieds = d.cursor.execute(
                    'select inventory_entry_id from inventory_entry'
                    ' where shelfcode_id = %s'
                    '  and inventory_id = %s and title_id = %s',
                    (code.id, inventory_id, title.title_id))
                ieds = list(ieds)
                try:
                    (inventory_entry_id,) = ieds
                except ValueError:
                    if ieds:
                        print('too many titles', ieds)
                    else:
                        print('Title not found in shelf packet')
                    continue
                d.cursor.execute(
                    'delete from inventory_missing'
                    ' where inventory_entry_id = %s',
                    (inventory_entry_id,))
                d.cursor.execute(
                    'insert into inventory_missing('
                    ' inventory_entry_id, missing_count)'
                    ' values (%s, %s)',
                    (inventory_entry_id, missing))
                d.db.commit()

if __name__ == '__main__':
    main()
