#!/usr/bin/python

import sys

from mitsfs.ui import read, specify
from mitsfs.dexdb import DexDB
from mitsfs.library import DATABASE_DSN

d = DexDB(dsn=DATABASE_DSN)

if len(sys.argv) == 1:
    ((inventory_code, inventory_id, inventory_desc),) = \
        d.cursor.execute(
            'select inventory_code, inventory_id, inventory_desc'
            ' from inventory order by inventory_stamp desc limit 1')
else:
    _, inventory_code = sys.argv
    ((inventory_id, inventory_desc),) = \
        d.cursor.execute(
            'select inventory_id, inventory_desc'
            ' from inventory where inventory_code=%s',
            (inventory_code,))

print('%s (%s)' % (inventory_desc, inventory_code))

while True:
    shelfcode = read(
        'shelfcode: ').upper().strip()
    if not shelfcode:
        break
    try:
        (shelfcode_id,) = d.cursor.execute(
            'select shelfcode_id from shelfcode where shelfcode=%s',
            (shelfcode,))
    except ValueError:
        print('No such shelfcode')
        continue

    print(shelfcode, d.codes[shelfcode].get('name', ''))
    print()
    while True:
        title = specify(d)
        if not title:
            break
        print(title.title_id, title)
        comment = read('comment? ')
        d.cursor.execute(
            'insert into shelf_divisions(title_id, inventory_id,'
            ' shelfcode_id, division_comment)'
            ' values (%s,%s,%s,%s)',
            (title.title_id, inventory_id, shelfcode_id, comment))
        d.db.commit()

        print('(%s)' % shelfcode)
