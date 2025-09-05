# -*- coding: utf-8 -*-

import datetime

from mitsfs import db
from mitsfs import ui

'''
Basic foundational information about available memberships 
'''


class MembershipInfo(db.Entry):
    def __init__(self, db, membership_type_id=None, **kw):
        super().__init__('membership_type', 'membership_type_id', db,
                         membership_type_id, **kw)

    membership_type_id = db.InfoField('membership_type_id')

    code = db.InfoField('membership_type')
    cost = db.InfoField('membership_cost')
    description = db.InfoField('membership_description')
    duration = db.InfoField('membership_duration')
    active = db.InfoField('membership_type_active')


class MembershipOptions(dict):

    def __init__(self, db):
        # keep track of these two lists to build the matching regex
        super().__init__()
        for row in self.load_from_db(db):
            (m_id, code, description, duration, cost) = row
            m = MembershipInfo(db, m_id, code=code, description=description,
                               duration=duration, cost=cost, active=True)
            super().__setitem__(m.code, m)

    def load_from_db(self, db):
        c = db.getcursor()
        c.execute('select membership_type_id, membership_type,'
                  ' membership_description, membership_duration,'
                  ' membership_type_cost'
                  ' from membership_type'
                  " where membership_type_active = 't'"
                  )
        return c.fetchall()

    def __repr__(self):
        return "\n".join(["%s => %s (%s)" %
                          (key,
                           super().__getitem__(key).description,
                           super().__getitem__(key).membership_type_id)
                          for key in self.keys()])
