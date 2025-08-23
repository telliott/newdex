#!/usr/bin/python

import sys

from mitsfs.dexdb import DexDB
from mitsfs.constants import DATABASE_DSN

def main():
    d = DexDB(dsn=DATABASE_DSN)

    sql = d.cursor.execute

    lst = list(sql(
        'select member_email'
        ' from member_email'
        ' where member_email_id in ('
        '  select'
        '   distinct member.member_email_default'
        '   from membership'
        '    natural join member'
        '    join member_email on (member_email_default=member_email_id)'
        '   where'
        '   membership_expires is null'
        ' or membership_expires > current_timestamp)'))

    lst.sort()
    for i in lst:
        print(i[0])


def member_list_since(date):
    d = DexDB(dsn=DATABASE_DSN)

    sql = d.cursor.execute

    lst = list(sql(
        """
        with m as (
           select member_id, membership_expires, membership_type, row_number()
              over (partition by member_id order by membership_expires desc)
           from membership
        )
        select member_name, member_email, membership_expires, membership_description, membership_duration
        from member
        join member_name on member_name_id = member_name_default
        join member_email on member_email_id = member_email_default
        join  m on m.member_id = member.member_id
        natural join membership_type
        where row_number = 1
              and member.member_modified >= %s
        order by membership_expires desc
        """, (date ,)))

    for i in lst:
        print ("%s | %s | %s" % (
            '{0: <25}'.format(i[0]),
            '{0: <25}'.format(i[1]),
            '{0: <25}'.format(format_date(i[2]))))


def active_member_list():
    d = DexDB(dsn=DATABASE_DSN)

    sql = d.cursor.execute

    lst = list(sql(
        """
        with m as (
           select member_id, membership_expires, membership_type, row_number()
              over (partition by member_id order by membership_expires desc)
           from membership
        )
        select member_name, member_email, membership_expires, membership_description, membership_duration
        from member
        join member_name on member_name_id = member_name_default
        join member_email on member_email_id = member_email_default
        join  m on m.member_id = member.member_id
        natural join membership_type
        where row_number = 1
              and (membership_description = 'Life' 
                   or membership_expires > now())
        order by membership_expires desc, member_name
        """))

    for i in lst:
        print ("%s | %s | %s" % (
            '{0: <30}'.format(i[0]),
            '{0: <35}'.format(i[1]),
            '{0: <10}'.format(format_date(i[2]))))



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
