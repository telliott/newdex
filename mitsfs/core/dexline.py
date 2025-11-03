import re
from functools import total_ordering

from mitsfs.util import utils
from mitsfs.dex.editions import Edition, Editions

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


@total_ordering
class DexLine(object):
    fieldtypes = (
        ('authors', utils.FieldTuple, utils.FieldTuple(), False),
        ('titles', utils.FieldTuple, utils.FieldTuple(), False),
        ('series', utils.FieldTuple, utils.FieldTuple(), False),
        ('codes', Editions, Editions(''), True),
        )
    fields = [name for (name, constructor, default, copy) in fieldtypes]
    # splits = ['authors', 'titles', 'series']
    # emptytuple = utils.FieldTuple()
    # emptycodes = Editions()

    def __init__(
            self, line=None, authors=None, titles=None, series=None,
            codes=None,
            ):
        if line is not None:
            if isinstance(line, self.__class__):
                for (name, constructor, default, copy) in DexLine.fieldtypes:
                    if not copy:
                        setattr(self, name, getattr(line, name))
                    else:
                        setattr(self, name, constructor(getattr(line, name)))
                # XXX kluuuuuuuuuuuudge
                if hasattr(line, 'title_id'):
                    self.title_id = line.title_id
            else:
                split = line.strip().split('<')
                assert len(split) == 4
                for ((name, constructor, default, copy), value) in \
                        zip(DexLine.fieldtypes, split):
                    setattr(self, name, constructor(value))
        else:
            for (name, construct, default, copy) in DexLine.fieldtypes:
                setattr(self, name, default)
        if authors is not None:
            self.authors = utils.FieldTuple(authors)
        if titles is not None:
            self.titles = utils.FieldTuple(titles)
        if series is not None:
            self.series = utils.FieldTuple(series)
        if codes is not None:
            if isinstance(codes, Editions):
                self.codes = codes
            else:
                self.codes = Editions(codes)

    def __str__(self):
        return '<'.join([
            str(getattr(self, field))
            for field in self.fields])

    def logstr(self):
        return '<'.join([
            getattr(self, field).logstr()
            for field in self.fields])

    def negate(self):
        line = self.__class__(self)
        line.codes = -line.codes
        return line

    def key(self):
        return self.authors, self.titles

    def __repr__(self):
        return 'DexLine(' + repr(str(self)) + ')'

    @property
    def authortxt(self):
        return str(self.authors)

    @property
    def titletxt(self):
        return str(self.titles)

    @property
    def seriestxt(self):
        return str(self.series)

    # These are the sort keys
    @property
    def placeauthor(self):
        return sanitize_sort_key(str(self.authors[0]))

    @property
    def placetitle(self):
        # handle the accidental blank title. Shouldn't happen any more
        if not self.titles[0]: 
            return ''
        
        # We want to sort on the alt title, as that's where the numbers are
        index = self.titles[0].find('=')
        if index != -1:
            return sanitize_sort_key(self.titles[0][index + 1:])
        else:
            return sanitize_sort_key(self.titles[0])

    TRAILING_NUMBER = re.compile(r' [0-9,]+$')
    @property
    def placeseries(self):
        if self.series:
            return sanitize_sort_key(
                self.TRAILING_NUMBER.sub('', str(self.series)))
        return ''

    def sortkey(self):
        self._sortkey = (
            (self.placeauthor, self.placetitle, self.authortxt,
             self.placetitle, self.titletxt),
            self)
        return self._sortkey

    VSRE = re.compile(r' #([-.,\d]+B?)$')
    def shelfkey(self, shelfcode):
        edition = Edition(shelfcode)

        if edition.double_info:
            key = [edition.double_info, self.placeauthor]
        else:
            key = [self.placeauthor]

        if self.series:
            series_visible = (edition.series_visible
                              or self.series[0][0] == '@')
            if series_visible:
                key += [self.placeseries]
                m = self.VSRE.search(self.series[0])
                if m:
                    key += [sanitize_sort_key(m.group(0))]
        key += [self.placetitle]
        self._shelfkey = tuple(key)
        return self._shelfkey

    def __eq__(self, other):
        return (self.authors, self.titles) == (other.authors, other.titles)

    def __lt__(self, other):
        return (self.authors, self.titles) < (other.authors, other.titles)
