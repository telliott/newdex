from mitsfs.dex.shelfcodes import Shelfcode, Shelfcodes

'''
Coercers are helper functions that take a value from the database (which
is usually a string) and turn it into the correct format that the model needs.

Passed in as a function to Field, and called with consistent parameters

@param field: the value of the field to be coerced
@param db: a pointer to the database (optional)

@return: the transformed value
'''


'''
Remove the timezone from a datetime object
'''


def coerce_datetime_no_timezone(field, db=None):
    if field is None:
        return field
    return field.replace(tzinfo=None)


'''
Turn a string into a boolean.

'''


def coerce_boolean(field, db=None):
    if field == 'f':
        return False
    return bool(field)


'''
Turn a shelfcode ID into a shelfcode object

Really should figure out how to cache this
'''


def coerce_shelfcode(field, db):
    shelfcodes = Shelfcodes(db)
    for code in shelfcodes.values():
        if code.shelfcode_id == field:
            return code
    return None


'''
Get the shelfcode_id from a shelfcode object
'''


def uncoerce_shelfcode(field, db=None):
    if type(field) is Shelfcode:
        return int(field)
    return field


'''
Turn a boolean into t/f
'''


def uncoerce_boolean(field, db=None):
    if field is False:
        return 'f'
    return 't'
