'''
Constants for the mitsfs package
'''

import os


__all__ = [
    'LOCKER', 'DEXBASE', 'CODEBASE', 'DATADEX_FILE',
    ]


'''
LOCKER = '/afs/athena.mit.edu/activity/m/mitsfs'
DEXBASE = os.path.join(LOCKER, 'dex')
if os.path.exists('/mitsfs/dexcode'):
    CODEBASE = '/mitsfs/dexcode'
else:
    CODEBASE = os.path.join(LOCKER, 'dexcode/dexcode')
DATADEX_FILE = os.path.join(DEXBASE, 'datadex')
'''

LOCKER = '/Users/telliott'
DEXBASE = os.path.join(LOCKER, 'dex')
if os.path.exists('/mitsfs/dexcode'):
    CODEBASE = '/mitsfs/dexcode'
else:
    CODEBASE = os.path.join(LOCKER, 'newdex')
DATADEX_FILE = os.path.join(DEXBASE, 'datadex')
