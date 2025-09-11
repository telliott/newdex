#!/usr/bin/python

import sys

from mitsfs.dexdb import DexDB
from mitsfs.library import DATABASE_DSN
from mitsfs.circulation import format_name


def main():
    d = DexDB(dsn=DATABASE_DSN)

    lst = list(d.cursor.execute(
        'select email from member natural join membership'
        ' where'
        ' membership_expires is null' 
        ' or membership_expires > current_timestamp'
        ' order by email'
        ))

    for i in lst:
        print(i[0])


def member_list_since(date):
    d = DexDB(dsn=DATABASE_DSN)

    lst = list(d.cursor.execute(
        """
        with m as (
           select member_id, membership_expires, membership_type, row_number()
              over (partition by member_id order by membership_expires desc)
           from membership
        )
        select first_name, last_name, membership_expires, 
         membership_description, membership_duration
        from member
        join  m on m.member_id = member.member_id
        natural join membership_type
        where row_number = 1
              and member.member_modified >= %s
        order by membership_expires desc
        """, (date ,)))

    for i in lst:
        print ("%s | %s | %s" % (
            '{0: <25}'.format(format_name(i[0], i[1])),
            '{0: <25}'.format(format_date(i[2])),
            '{0: <25}'.format(i[3])
            ))


def active_member_list():
    d = DexDB(dsn=DATABASE_DSN)

    lst = list(d.cursor.execute(
        """
        with m as (
           select member_id, membership_expires, membership_type, row_number()
              over (partition by member_id order by membership_expires desc)
           from membership
        )
        select first_name, last_name, email, membership_expires, 
         membership_description, membership_duration
        from member
        join  m on m.member_id = member.member_id
        natural join membership_type
        where row_number = 1
              and (membership_description = 'Life' 
                   or membership_expires > now())
        order by membership_expires desc, last_name, first_name
        """))

    for i in lst:
        print ("%s | %s | %s" % (
            '{0: <30}'.format(format_name(i[0], i[1])),
            '{0: <35}'.format(i[2]),
            '{0: <10}'.format(format_date(i[3]))))

    
def format_date(date):
    if date is None:
        return 'None'
    return date.strftime('%Y-%m-%d')

if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1] == 'current':
            active_member_list()
        else:
            member_list_since(sys.argv[1])
    else:
        main()
