import os
from mitsfs.core.db import Database
from mitsfs.core import settings

from mitsfs.dex.shelfcodes import Shelfcodes

from mitsfs.circulation.membership_types import MembershipTypes
from mitsfs.circulation.timewarps import Timewarps
from mitsfs.circulation.members import Members



class Library():
    def __init__(self, db=None, client='mitsfs.dexdb',
                 dsn=os.environ.get('MITSFS_DSN') or settings.DATABASE_DSN):
        # this is a hack to prevent multiple db connections in unit tests
        # while dexdb is still around
        if db:
            self.db = db
        else:
            self.db = Database(client, dsn)

        settings.shelfcodes_global = Shelfcodes(self.db)
        settings.membership_types_global = MembershipTypes(self.db)
        settings.timewarps_global = Timewarps(self.db)

    @property
    def shelfcodes(self):
        return settings.shelfcodes_global

    @property
    def membership_types(self):
        return settings.membership_types_global

    @property
    def timewarps(self):
        return settings.timewarps_global

    @property
    def members(self):
        return Members(self.db)

    @property
    def books(self):
        pass
