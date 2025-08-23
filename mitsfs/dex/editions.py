# -*- coding: utf-8 -*-
import re

import mitsfs.dex.shelfcodes



class InvalidShelfcode(Exception):
    def __init__(self, message, specific):
        Exception.__init__(self, message + ' ' + repr(specific))


def splitcode(code_string):
    if mitsfs.dex.shelfcodes.parse_shelfcodes is None:
        #TODO: Something better here. We haven't initialized DexDB yet
        raise Exception
    m = mitsfs.dex.shelfcodes.parse_shelfcodes.match(code_string)
    if not m:
        raise InvalidShelfcode('Unknown shelfcode', code_string)
    at, shelfcode, doublecode, double_info = m.groups()
    return at == '@', shelfcode or doublecode, double_info if double_info else None

pragma_validate_shelfcode = True

CODESPLITRE = re.compile(r'[;:]')
BOXRE = re.compile(r'([-A-Z0-9/.#]+){([A-Z/]+)}')


def onecode(s, defcount=1, validate=None):
    if validate is None:
        validate = pragma_validate_shelfcode
    box = ''
    split = CODESPLITRE.split(s)
    n = len(split)
    if n == 0 or n > 2:
        raise InvalidShelfcode('Invalid code string', s)
    if len(split) == 1:
        code, count = split[0], defcount
    else:
        code, count = split
        if not count:
            count = defcount
        try:
            count = int(count)
        except ValueError:
            raise InvalidShelfcode('Invalid count', count)
    m = BOXRE.match(code)
    if m:
        box, code = m.groups(1)
    if code and validate:
        splitcode(code)  # throws an exception on invalid code
    return code, count, box


class Editions(dict):
    SPLITRE = re.compile(r'\s*,\s*')
    INVENRE = re.compile(r'^([A-Z]+): ')   

    def __init__(self, s=None, inven_type=None):
        if s is None:
            self.inven_type = inven_type
            super().__init__()
        elif isinstance(s, str):
            s = s.upper().strip()
            if s:
                m = self.INVENRE.match(s)
                if m is not None:
                    self.inven_type = m.group(1)
                    s = self.INVENRE.sub('', s)
                else:
                    self.inven_type = None
                y = [onecode(i) for i in self.SPLITRE.split(s)]
                x = [(code, count) for (code, count, box) in y]
                super().__init__(x)
            else:
                super().__init__()
        else:
            self.inven_type = getattr(s, 'inven_type', inven_type)
            super().__init__(s)

    def list(self):
        return [
            code + ':' + str(count) if count != 1 else code
            for (code, count) in sorted(self.items())]

    def __str__(self):
        return ','.join(self.list())

    def __repr__(self):
        return 'Editions(' + repr(str(self)) + ')'

    def logstr(self):
        return ','.join(
            code + ':' + str(count)
            for (code, count) in sorted(self.items()))

    def __getitem__(self, k):
        if k in self:
            return super().__getitem__(k)
        else:
            return 0

    def __nonzero__(self):
        return sum(abs(i) for i in self.values()) > 0

    def __add__(self, other):
        if not isinstance(other, Editions):
            other = Editions(other)
        result = Editions(self)
        for i in other:
            result[i] += other[i]
            if result[i] == 0:
                del result[i]
        return result

    def __neg__(self):
        return Editions((code, -count) for (code, count) in self.items())

    def __sub__(self, other):
        if not isinstance(other, Editions):
            other = Editions(other)
        return self + -other

    def __int__(self):
        return sum(self.values())

