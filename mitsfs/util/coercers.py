
'''
Coercers are helper functions that take a value from the database (which
is usually a string) and turn it into the correct format that the model needs.

Passed in as a function to Field, and called with consistent parameters

@param field: the value of the field to be coerced
@param db: a pointer to the database (usually optional)

@return: the transformed value
'''


def coerce_datetime_no_timezone(field, db=None):
    '''
    Remove the timezone from a datetime object
    '''
    if field is None:
        return field
    return field.replace(tzinfo=None)


def coerce_boolean(field, db=None):
    '''
    Turn a string into a boolean.
    '''
    if field == 'f':
        return False
    return bool(field)


def uncoerce_boolean(field, db=None):
    '''
    Turn a boolean into t/f
    '''
    if field is False:
        return 'f'
    return 't'


def coerce_shelfcode(field, db):
    '''
    Turn a shelfcode ID into a shelfcode object
    '''
    from mitsfs.dex.shelfcodes import Shelfcodes
    shelfcodes = Shelfcodes(db)
    for code in shelfcodes.values():
        if code.id == field:
            return code
    return None


def uncoerce_shelfcode(field, db=None):
    '''
    Get the shelfcode_id from a shelfcode object
    '''
    from mitsfs.dex.shelfcodes import Shelfcode
    if type(field) is Shelfcode:
        return int(field)
    return field


def coerce_title(field, db):
    '''
    Turn a title ID into a title object
    '''
    from mitsfs.dex.titles import Title
    return Title(db, field)


def uncoerce_title(field, db=None):
    '''
    Get the title_id from a title object
    '''
    from mitsfs.dex.titles import Title
    if type(field) is Title:
        return field.id
    return field




