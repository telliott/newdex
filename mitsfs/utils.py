#!/usr/bin/python
'''
assorted utility functions

'''


import re
import time
import logging


__all__ = [
    'PropDict', 'timestamp', 'sort_key', 'get_logfiles',
    ]


class PropDict(dict):
    "strongly inspired by web.py's Storage"
    def __getattr__(self, k):
        return self[k]

    def __setattr__(self, k, v):
        self[k] = v

    def __delattr__(self, k):
        try:
            del self[k]
        except KeyError as e:
            raise AttributeError(str(e))

    def __repr__(self):
        return 'PropDict(' + dict.__repr__(self) + ')'


def timestamp():
    return time.strftime('%Y%m%d%H%M%S')


SPLITTER = re.compile(r'(\D+)')
DIGITS = re.compile(r'^(\d+)$')


def sort_key(s):
    return tuple(
        int(t) if DIGITS.match(t) else t.strip()
        for t in [_f for _f in SPLITTER.split(s) if _f])


def get_logfiles():
    for handler in logging.getLogger().handlers:
        filename = getattr(handler, 'baseFilename', None)
        if filename is not None:
            yield filename
