#!/usr/bin/python
'''

barcode utilities

'''

__all__ = [
    'valifrob', 'validate_barcode',
    ]


def checkdigit(s):
    s = s.replace(' ', '')
    t = (sum([int(i) for i in s[1::2]]) +
         sum([((2 * int(i)) % 9) for i in s[::2]])) % 10
    return 10 - t if t != 0 else t


def valifrob(s):
    try:
        s = s.strip('-$:/.+*ABCDTNEabcdtnex')
        return s
    except (ValueError, TypeError):
        return None


# This needs to be correct
def validate_barcode(barcode):
    if len(barcode) != 10:
        return False
    for c in barcode:
        if c not in [str(s) for s in range(10)]:
            return False
    return True
