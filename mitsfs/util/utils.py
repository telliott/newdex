#!/usr/bin/python
import time
import logging


class FieldTuple(tuple):
    '''
    A pretty standard tuple class, but it splits the strings provided on
    | (the standard delimeter for most dex fields)
    '''

    def __new__(cls, x=None):
        if x is None:
            return super().__new__(cls)
        if isinstance(x, str):
            x = [i.strip() for i in x.split('|') if i.strip()]
        return super().__new__(cls, x)

    def __str__(self):
        return '|'.join(self)

    logstr = __str__

    def __repr__(self):
        return 'FieldTuple(' + super(FieldTuple, self).__repr__() + ')'


class PropDict(dict):
    '''
    A dictionary subclass that allows access through both keys and
    properties.
    '''

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

def get_logfiles():
    for handler in logging.getLogger().handlers:
        filename = getattr(handler, 'baseFilename', None)
        if filename is not None:
            yield filename

