#!/usr/bin/python

from os import system
from mitsfs import DexDB


def main():
    d = DexDB()

    (n,) = d.cursor.execute(
        "select count(generation) from log"
        " where stamp > (timestamp 'now' - interval '5 minutes')")

    if not n:
        dexnames = d.save()
        titles = tuple(d.cursor.execute(
            'select count(distinct title_id)'
            ' from title natural join book where not withdrawn'))
        books = tuple(d.cursor.execute(
            'select count(distinct book_id) from book where not withdrawn'))

        if dexnames:
            system(
                'diff -U 0 %s %s'
                ' | zwrite -n -d -q -c mitsfs-auto -i pinkdex'
                ' -O AUTO -s "%d titles, %d books saved"'
                % (dexnames + titles + books))


if __name__ == '__main__':
    main()
