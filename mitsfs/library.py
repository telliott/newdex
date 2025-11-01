import os
import logging

from mitsfs.core.db import Database
from mitsfs.core import settings

from mitsfs.dex.shelfcodes import Shelfcodes
from mitsfs.dex.catalog import Catalog

from mitsfs.circulation.membership_types import MembershipTypes
from mitsfs.circulation.timewarps import Timewarps
from mitsfs.circulation.members import Members
from mitsfs.dex.inventory import Inventories

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
    def catalog(self):
        return Catalog(self.db)

    @property
    def log(self):
        return logging.getLogger('mitsfs.error')

    # set to false because inventory can be none and we want to cache that
    _inventory = False
    
    @property
    def inventory(self):
        if self._inventory is False:
            i = Inventories(self.db)
            self._inventory = i.get_open()
        return self._inventory

    def reset_inventory(self):
        self._inventory = False