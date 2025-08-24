#!/usr/bin/python

import sys
import csv

from mitsfs.dexdb import DexDB


def main():
    _, code = sys.argv
    dumpcode(code)


def dumpcode(code):
    d = DexDB()

    titles = list(d.iter(
        '''select title_id
           from title
            natural join title_responsibility natural join entity
            natural join title_title
            natural join book natural join shelfcode
           where order_responsibility_by = 0 and order_title_by = 0
            and not withdrawn and shelfcode=%s
           order by upper(entity_name), upper(title_name)''',
        (code,),
        ))

    o = csv.writer(sys.stdout)
    for title in titles:
        o.writerow([
            title.title_id,
            '|'.join(
                type_ + ':' + name
                for (type_, name) in
                d.getcursor().execute(
                    '''select responsibility_type, entity_name
                       from title_responsibility natural join entity
                       where title_id=%s
                       order by order_responsibility_by''',
                    (title.title_id,),
                    )
                ),
            '|'.join(
                type_ + ':' + name
                for (type_, name) in
                d.getcursor().execute(
                    '''select title_type, title_name
                       from title_title
                       where title_id=%s
                       order by order_title_by''',
                    (title.title_id,),
                    )
                ),
            '|'.join(title.series),
            str(title.codes),
            ])


if __name__ == '__main__':
    main()
