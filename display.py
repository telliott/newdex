#!/usr/bin/python

from mitsfs.dexdb import DexDB
from mitsfs.ui import specify, read


d = DexDB()

sql = d.cursor.execute

title = None
while True:
    title = specify(d, title)
    if not title:
        break

    print(title)
    print('#%s' % title.id)
    print()
    print('HOLDINGS')
    for book in title.books:
        print(book)

    checkouts = list(sql(
        'select'
        '  checkout_user, checkout_stamp, checkin_stamp,'
        '  member_name, shelfcode'
        ' from book natural join checkout natural left join checkout_member'
        '  natural join member natural join shelfcode'
        '  join member_name on member_name_default = member_name_id'
        ' where title_id=%s'
        ' order by checkout_stamp',
        (title.title_id,)))
    if checkouts:
        print()
        print('CIRCULATION')
        for key, checkout, checkin, member, shelfcode in checkouts:
            print('%-9.9s %-32s %-32s %s' % (
                key, checkout, (checkin or member), shelfcode))

    found = list(sql(
        'select'
        '  inventory_code, format, found_tag,'
        '  inventory_reshelved, inventory_found_id'
        ' from inventory_found natural join inventory natural join format'
        ' where title_id=%s'
        ' order by inventory_code, format, found_tag, inventory_reshelved',
        (title.title_id,)))
    if found:
        print()
        print('FOUND')
        for (n, (inventory, format, box, reshelved, id)) in enumerate(found):
            print('%-2d %4s %1s %-10s %s' % (
                n + 1, inventory, format, box, 'SHELVED' if reshelved else ''))

    missing = list(sql(
        'select'
        '  inventory_code, shelfcode, inventory_packet_name, missing_count,'
        '  missing, inventory_entry_id'
        ' from inventory natural join inventory_entry natural join shelfcode'
        '  natural join inventory_missing natural join inventory_packet'
        ' where title_id=%s'
        ' order by inventory_code, shelfcode',
        (title.title_id,)))
    if missing:
        print()
        print('MISSING')
        for (n, (inventory, shelfcode, packet, count, xmissing, id)) in \
                enumerate(missing):
            print('%-2d %4s %-12s %-10s %d%s' % (
                n + 1, inventory, shelfcode, packet, count,
                '' if xmissing else ' FOUND'))

    print()
    if False:
        c = read('? ').strip()
        if c:
            if c[0] == 's':
                try:
                    n = int(c[1:].strip())
                except ValueError:
                    print('??', repr(c[1:]))
                    continue
                print(n)
                if n < 1:
                    if len(found) == 1:
                        n = 1
                    else:
                        continue
                (inventory, format, box, reshelved, id) = found[n - 1]
                print('marking', id, 'as shelved')
                sql('update inventory_found set inventory_reshelved=true'
                    ' where inventory_found_id=%s', (id,))
                d.db.commit()
                continue
            if c[0] == 'f':
                try:
                    n = int(c[1:].strip())
                except ValueError:
                    print('??', repr(c[1:]))
                    continue
                print(n)
                if n < 1:
                    if len(missing) == 1:
                        n = 1
                    else:
                        continue
                (inventory, shelfcode, packet, count, xmissing, id) = \
                    missing[n - 1]
                print('marking', id, 'as found')
                sql('update inventory_missing set missing=false'
                    ' where inventory_entry_id=%s', (id,))
                d.db.commit()
                continue
    title = None
