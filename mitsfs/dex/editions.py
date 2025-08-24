# -*- coding: utf-8 -*-
import re
import copy
from mitsfs.dex import shelfcodes


'''
Useful exception for when a shelfcode doesn't parse
'''


class InvalidShelfcode(Exception):
    def __init__(self, message, specific):
        Exception.__init__(self, message + ' ' + repr(specific))


'''
An edition is the association of a shelfcode with a book. It represents
a concrete volume that the library owns, and may encompass multiple copies
of that particular book.

If there is metainformation beyond the shelfcode (such as for a box or a
double) it keeps that information as well.

It also contains information about series visibility, though I have a
suspicion that this may be vestigial.

Editions contain the following fields:
    * series_visible
    * shelfcode - the shelfcode that belongs to this edition
    * double_info - any extra information for the code (for doubles, etc)
    * count - the number of copies of this edition
'''


class Edition(object):

    def __init__(self, code):
        self.count = 1
        # We can support single k/v pairs of code and count
        # Just turn the key into the string to parse and pre-set the count
        if isinstance(code, dict):
            code_string = next(iter(code))
            self.count = code[code_string]
        else:
            code_string = code

        # splitting on semicolon is not something I've seen anywhere, but
        # was in the code
        split = re.split('[;:]', code_string)

        # if we didn't split, that means we only had one copy in the library
        # which is represented by 'L' rather than 'L:1'. If we have more than
        # one, it'll split into 2 parts here. Anything else is weird.
        match len(split):
            case 1:
                self.series_visible, self.shelfcode, self.double_info = \
                    Edition.splitcode(split[0])
            case 2:
                self.series_visible, self.shelfcode, self.double_info = \
                    Edition.splitcode(split[0])
                self.count = int(split[1])
            case _:
                raise InvalidShelfcode('Invalid code string', code_string)

    '''
    int context means we want to know how many of this particular type

    @return: the count value
    '''

    def __int__(self):
        return self.count

    '''
    @return: the Dex string representing an edition, as it is on the textdex
    '''

    def __str__(self):
        if self.count == 1:
            return "%s%s%s" % ('@' if self.series_visible else '',
                               self.shelfcode, self.double_info or '')
        else:
            return "%s%s%s:%i" % ('@' if self.series_visible else '',
                                  self.shelfcode, self.double_info or '',
                                  self.count)

    '''
    @return: all the fields for debugging
    '''

    def __repr__(self):
        s = ', '.join(["%s: %s" % (x, str(getattr(self, x))) for x in
                       ['series_visible', 'shelfcode',
                        'double_info', 'count']])
        return "Edition(" + s + ")"

    '''
    Splits up a shelfcode into its component parts (everything but the count).

    Note that we use a global variable for the splitting regex. This is
    because we want to generate it from the list of shelfcodes. Those are
    stored in the db, and we will have loaded that separately (or possibly not
    at all yet). It also makes it possible to mock this up for testing of
    code sections that don't go down to the DB layer.

    @return an array in the order the Edition initializer takes them
    '''
    @staticmethod
    def splitcode(code_string):
        if shelfcodes.parse_shelfcodes is None:
            # TODO: Something better here. We haven't initialized DexDB (or
            # preset the field directly) yet
            raise Exception
        m = shelfcodes.parse_shelfcodes.match(code_string)
        if not m:
            raise InvalidShelfcode('Unknown shelfcode', code_string)
        at, shelfcode, doublecode, double_info = m.groups()
        return at == '@', shelfcode or doublecode, \
            double_info if double_info else None


'''
Editions are a collection of Edition objects, representing the different types
of volumes that we might have associated with a book. So, for example, if we
have an L and an S for a particular book, we would have two edition objects
in the collection.

They're keyed on the shelfcode for easy lookup, though the shelfcode is also
in the edition object. We also don't track the counts at this level. If you
need a count, grab it from the edition itself.

Implemented as a normal dictionary of shelfcode: Edition.
'''


class Editions(dict):

    '''
    We support initializing through multiple methods:
        * Nothing - creates an empty dictionary
        * Another editions object - copy it all to this one (as a deep copy)
        * A dictionary of shelfcodes and counts - create sparse editions (be
            careful using this one, as it may be lossy if you need doubles)
        * A dexstring of shelfcodes (e.g. 'L:2,S,SR-L'). It will parse each
            type into an edition.
    '''

    def __init__(self, s=None):
        super().__init__()
        if s is None:
            pass
        # If it's another Editions, copy it over
        elif isinstance(s, Editions):
            for k, v in s.items():
                super().__setitem__(k, copy.deepcopy(v))
        # If it's a string, we need to do the full parse, including count
        elif isinstance(s, str):
            s = s.upper().strip()
            if s:
                for c in re.split(r'\s*,\s*', s):
                    e = Edition(c)
                    super().__setitem__(e.shelfcode, e)
        # This is kind of hacky for backwards compatibility
        # Takes a dict of (shelfcode: count) pairs
        elif isinstance(s, dict):
            for (k, v) in s.items():
                e = Edition({k: v})
                super().__setitem__(e.shelfcode, e)
        else:
            raise InvalidShelfcode('Bad input to editions', s)

    '''
    Helper method to give you a joinable list of editions.

    For now, I've made the editorial decision to leave out the double info
    from the generic export. This might be wrong, but is pretty easy to put
    back. If you want the full shelfcode string, use the str representation
    from the Edition directly.

    @return: list of editions in dex format ('L:2', 'D' etc)
    '''

    def list(self):
        return [
            code + ':' + str(edition.count) if edition.count != 1 else code
            for (code, edition) in sorted(self.items())]

    '''
    The method that you're actually calling that uses the list. Joins them
    with a comma.

    @return: the dex representation of editions
    '''

    def __str__(self):
        return ','.join(self.list())

    '''
    More detailsed string for logging. Maybe this should just be __repr__?

    @return: logging string with all edition data.
    '''

    def logstr(self):
        return ','.join(
            code + ':' + repr(edition)
            for (code, edition) in sorted(self.items()))

    '''
    @return: the full edition object keyed by the edition code
    '''

    def __getitem__(self, k):
        if k in self:
            return super().__getitem__(k)
        else:
            return None

    '''
    Test to see if any of the edition objects in the collection have actual
    numbers associated with them (as opposed to being 0)

    @return: boolean. True if there's at least one edition with a count
    '''

    def __nonzero__(self):
        return sum(abs(i.count) for i in self.values()) > 0

    '''
    Take two Edition objects and mash them together. This means summing the
    counts associated with each shelfcode. Often used when one edition set has
    negative counts to remove stuff (though __sub__ may be a better way.

    Removes any editions entirely that no longer have a positive count of books

    @return: a new Editions object summing the previous two. Uses deepcopy, so
    will be a completely fresh object.
    '''

    def __add__(self, other):
        if not isinstance(other, Editions):
            other = Editions(other)
        new = copy.deepcopy(self)
        for i in other.keys():
            if i in new:
                new[i].count += other[i].count
            else:
                new[i] = other[i]
            if new[i].count <= 0:
                del new[i]
        return new

    '''
    Returns a new Editions object with all the counts inverted from the
    starting object. Uses a deep copy, so leaves the original Editions
    object intact

    @return: Editions object with inverted counts
    '''

    def __neg__(self):
        new = copy.deepcopy(self)
        for code in new.keys():
            new[code].count = -(new[code].count)
        return new

    '''
    The inverse of __add__. Takes the second Editions object and subtracts all
    the counts from the first Editions object. Removes any editions that now
    have zero or fewer copies. Leaves the original objects intact

    @return: a new Editions object with counts reflecting X - Y
    '''

    def __sub__(self, other):
        if not isinstance(other, Editions):
            other = Editions(other)
        new = copy.deepcopy(self)
        for i in other.keys():
            if i in new:
                new[i].count -= other[i].count
        for i in list(new.keys()):
            if new[i].count <= 0:
                del new[i]
        return new

    '''
    @return: the total number of physical volumes associated with this book
    '''

    def __int__(self):
        return sum(i.count for i in self.values())

    # This is code I did not implement from the old code. Looks like you
    # used to be able to encode as 'PANTS: C/P:2,P' and it did something for
    # inventory. But I don't understand what, and it may be vestigial
    #
    # INVENRE = re.compile(r'^([A-Z]+): ')
    # m = self.INVENRE.match(s)
    # if m is not None:
    #     self.inven_type = m.group(1)
    #     s = self.INVENRE.sub('', s)
    # else:
    #     self.inven_type = None
