#!/usr/bin/python

import sys

from mitsfs.ui import read, specify
from mitsfs.dexdb import DexDB
from mitsfs.core.settings import DATABASE_DSN


SHELFCODE_GLOSS = """
Inventory Actual will have handed you a stack of marked shelfdex
packets (shelfdexes).  This is the process of recording the books that
are missing.

In general in this program, leaving a prompt blank (counting
Author/Title as one prompt) will drop you up to the previous level.

All marks you make on the shelfdexes should be in green pen.

Take the first packet.  Put your initials in green pen  in the
"Panthercomm Intra-Inven" box.

Type the shelfcode marked on the packet at the upper right (the thing
in parentheses without a number.)
"""

SPECIFY_GLOSS = """
Type an author and a title as you would when checking out a book.
Tab-completion will limit itself to titles the system knows are listed
in the shelfdexes.

Once you're done with a packet, just hit return twice and it will ask
you for a shelcode again.  (If the new packet is in the same
shelfcode, you don't have to drop back, but it's a good habit because
if you change shelfcodes while the computer doesn't, things get
confusing.)

When you've finished a pile of packets, return them to Inventory Actual.
"""

COUNT_GLOSS = """
Type the number of things missing specified.  If there's no
number written but M is circled, that's one missing.
"""

POST_COUNT_GLOSS = """
If you realize at this point you made a mistake, you can fix it by
just entering a new number for a given title (remembering that it has
to be attributed to the same shelfcode, and that 0 is a number).
"""


def main():
    d = DexDB(dsn=DATABASE_DSN)

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

    first = True

    print(SHELFCODE_GLOSS)
    while True:
        shelfcode = read(
            'Shelfcode (q to quit)? ',
            callback=d.shelfcodes.keys,
            history='shelfcode',
            ).upper().strip()

        if not shelfcode or shelfcode == 'Q':
            break

        code = d.shelfcodes[shelfcode]
        if not code:
            print('Unknown shelfcode')
            continue

        print(code)

        title = None
        while True:
            if first:
                print(SPECIFY_GLOSS)
            print()
            title = specify(d, title)

            if not title:
                break

            print(title)

            if first:
                print(COUNT_GLOSS)

            try:
                mstr = read(
                    'How many missing? ', history='count').strip()
                if mstr == '':
                    missing = 1
                else:
                    missing = int(mstr)
            except (ValueError, KeyboardInterrupt):
                print('?')
                continue

            if first:
                print(POST_COUNT_GLOSS)

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
                title = None

            first = False


if __name__ == '__main__':
    main()
