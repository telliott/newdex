#!/usr/bin/python
'''

Various TeX-output-related stuff.

'''

import os

from mitsfs import constants


__all__ = [
    'TEXBASE', 'dexheader', 'dexfooter', 'texquote',
    ]


TEXBASE = constants.CODEBASE

TEXHEADER = '''\\def\\dexname{%(shortname)s}
\\def\\Supple{%(longname)s}
\\def\\Shelf{3}
\\def\\Reverse{3}
\\def\\Period{3}
\\input %(texheader)s

'''

dextype = {
    'exodex': ('Hassledex', 'dextex-exodus.tex'),
    }


def dexheader(type, desc):
    shortname, header = dextype[type]

    return TEXHEADER % {
        'shortname': shortname,
        'texheader': os.path.join(TEXBASE, header),
        'longname': desc,
        }


def dexfooter():
    return '\n\\bye\n'


def texquote(s):
    s = ''.join(((i in '&$%#_') and ('\\' + i) or i for i in s))
    o = u''
    cjk = False
    for c in s:
        if ord(c) < 0x3000:
            if cjk:
                o += '}'
                cjk = False
        else:
            if not cjk:
                o += r'{\unifont '
                cjk = True
        o += c
    if cjk:
        o += '}'
    return o
