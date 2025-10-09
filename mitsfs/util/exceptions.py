
class CirculationException(Exception):
    pass


class Ambiguity(Exception):
    pass


class InvalidShelfcode(Exception):
    def __init__(self, message, specific):
        '''
        Useful exception for when a shelfcode doesn't parse
        '''
        Exception.__init__(self, message + ' ' + repr(specific))


class DuplicateEntry(Exception):
    pass

class NotFoundException(Exception):
    pass