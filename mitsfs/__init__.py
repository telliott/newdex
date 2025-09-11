#!/usr/bin/python
"""
MITSFS package

"""

import logging
import os
from mitsfs import utils

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
