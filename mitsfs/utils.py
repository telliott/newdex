#!/usr/bin/python
import time
import logging
import re


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

# appears to be unused
# SPLITTER = re.compile(r'(\D+)')
# DIGITS = re.compile(r'^(\d+)$')


# def sort_key(s):
#     return tuple(
#         int(t) if t.isdigit() else t.strip()
#         for t in [_f for _f in SPLITTER.split(s) if _f])


def get_logfiles():
    for handler in logging.getLogger().handlers:
        filename = getattr(handler, 'baseFilename', None)
        if filename is not None:
            yield filename


NUMBER = re.compile(r'(\d+)')
TRAILING_ARTICLE = re.compile(', (?:A|AN|THE)$')
PUNCTUATION_WHITESPACE = re.compile('[-/,: ]+')
REMOVE_OTHER = re.compile(r'[^A-Z0-9\(\) ]')
START_PAREN = re.compile(r'^\(')
START_NUMBER = re.compile(r'^(\d\S+) ?(.*)')


def sanitize_sort_key(s):
    '''
    Sortkeys are used to order books on the shelf, so we do a little bit
    of title/author/series munging to get them ordered appropriately. This
    function strips down the strings for easier sorting.

    Parameters
    ----------
    s : string
        A string (usually author, title or series)

    Returns
    -------
    string
        the string with a bunch of stuff removed so that it can be sorted

    '''
    # remove any extraneous newlines and spaces
    s = s.strip()

    # uppercase the string
    s = s.upper()

    # remove any training articles (a, an, the)
    s = TRAILING_ARTICLE.sub('', s)

    # replace punctuation and multiple witespaces with a single one
    s = PUNCTUATION_WHITESPACE.sub(' ', s)

    # remove everything that isn't a letter, number, space or parens
    s = REMOVE_OTHER.sub('', s)

    # remove an paren at the start. I don't think this is a thing
    s = START_PAREN.sub('', s)

    # Swap any opening number to the end
    s = START_NUMBER.sub(r'\2 \1', s)

    def pad_numbers(s):
        try:
            n = int(s)
        except ValueError:
            return s
        return '%06d' % n

    # expand any number to 6 digits by prepending zeroes
    s = ''.join([pad_numbers(i) for i in NUMBER.split(s)])

    # swap parens for <>. I suspect this is just to make regexes on it easier
    s = s.replace('(', '<')
    s = s.replace(')', '>')

    return s
