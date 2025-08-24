#!/usr/bin/python
"""
MITSFS package

"""

import logging
import os

from mitsfs import constants
from mitsfs import utils
from mitsfs import dexfile
from mitsfs import ui
from mitsfs import tex
from mitsfs import db
from mitsfs import dexdb
from mitsfs import barcode
from mitsfs import inventory
from mitsfs import membership
from mitsfs import lock_file

__all__ = (
    constants.__all__ +
    utils.__all__ +
    dexfile.__all__ +
    ui.__all__ +
    tex.__all__ +
    db.__all__ +
    dexdb.__all__ +
    barcode.__all__ +
    inventory.__all__ +
    membership.__all__ +
    lock_file.__all__
    )


#mask = os.umask(0700)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(name)s: %(message)s',
    filename='/tmp/mitsfs.log.%d' % os.getuid(),
    filemode='a')
#os.umask(mask)
for filename in utils.get_logfiles():
    mode = os.stat(filename).st_mode & 0o777
    if mode & 0o77:
        os.chmod(filename, mode & 0o700)
