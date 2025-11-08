import re
from mitsfs.core import db

def responsibility_types(db):
    '''
    Parameters
    ----------
    db : Database
        database handle.

    Returns
    -------
    types : dict
        k/v pairs for the abbreviation and the responsibility (author,
        editor, etc).

    '''
    types = {}
    c = db.getcursor()
    c.execute(
        'select responsibility_type, description'
        ' from title_responsibility_type'
        )
    for row in c.fetchall():
        types[row[0]] = row[1]
    
    return types

# tested in test_indexes.py
class Authors(object):
    def __init__(self, db):
        self.db = db

    def keys(self):
        '''
        Returns
        -------
        list(str)
            A list of all the authors we have in the catalog.

        '''
        c = self.db.getcursor()
        return c.fetchlist(
                "select CONCAT_WS('=', entity_name, alternate_entity_name)"
                ' from entity'
                ' order by entity_name')

    def __contains__(self, author):
        '''
        Do we have this author in the dex? Requires an exact match

        Parameters
        ----------
        author : str
            a string to search for.

        Returns
        -------
        bool - if the author exists

        '''
        val = self.db.getcursor().selectvalue(
            "select entity_id"
            " from entity"
            " where"
            "  entity_name = %s or alternate_entity_name = %s",
            (author, author))
        return val is not None

    def search(self, author):
        '''
        Search author name for a given substring and return all the IDs that
        match

        Parameters
        ----------
        authors : str
            a string to search for.

        Returns
        -------
        list(str)
            a list of entity_ids (author_ids).

        '''
        c = self.db.getcursor()
        return c.fetchlist(
            "select distinct entity_id"
            " from entity"
            " where"
            "  entity_name ilike %s or alternate_entity_name ilike %s",
            (f'{author}%', f'{author}%'))

    def __getitem__(self, key):
        '''
        Allows for author retrieval by name. Requires exact match
        and returns the title

        Parameters
        ----------
        key : TYPE
            DESCRIPTION.

        Returns
        -------
        TYPE
            DESCRIPTION.

        '''
        from mitsfs.dex.titles import Title
        c = self.db.getcursor()
        return (
            Title(self.db, title_id[0])
            for title_id
            in c.execute(
                'select distinct title_id'
                ' from title_responsibility'
                '  natural join entity'
                ' where'
                ' entity_name ilike %s'
                ' or alternate_entity_name ilike %s',
                (f'{key}%', f'{key}%')))

    def complete(self, key):
        '''
        Autocomplete for an author name

        Parameters
        ----------
        s : string
            String to check against the start of author names.

        Returns
        -------
        list(str)
            a list of author names.

        '''
        c = self.db.getcursor()
        return c.fetchlist(
            'select entity_name'
            ' from entity'
            ' where'
            ' entity_name ilike %s'
            ' or alternate_entity_name ilike %s'
            ' order by entity_name',
            (f'{key}%', f'{key}%'))

    def complete_checkedout(self, key):
        '''
        Autocomplete for an author name limited to authors with books
        checked out

        Parameters
        ----------
        s : string
            String to check against the start of author names.

        Returns
        -------
        list(str)
            a list of author names.

        '''
        c = self.db.getcursor()
        return c.fetchlist(
            'select entity_name'
            ' from'
            '  entity'
            '  natural join title_responsibility'
            '  natural join book'
            '  natural join checkout'
            ' where'
            '  checkin_stamp is null and'
            ' (entity_name ilike %s'
            ' or alternate_entity_name ilike %s)',
            (f'{key}%', f'{key}%'))

    def grep(self, s):
        '''
        Parameters
        ----------
        s : string
            A streng to match against the author names. Can be a
            regular expression.

        Returns
        -------
        list(title_ids)
            A list of title_ids where the author name patial-matches
            the submitted string.

        '''
        c = self.db.getcursor()
        return c.fetchlist(
            'select title_id'
            ' from entity'
            ' natural join title_responsibility'
            ' where entity_name ~ %s or alternate_entity_name ~ %s',
            (s.upper(), s.upper()))


AUTHOR_FORBIDDEN = re.compile(r'[\|=<]')
def sanitize_author(field, db=None):
    '''
    Clean out characters that would cause a Dexline problem

    Parameters
    ----------
    field : string
        the field to be sanitized.
    db : Database
        Unnexessary here, but this is used as a coercer, which
        sends it. The default is None.

    Returns
    -------
    string
        the sanitized string.

    '''
    if field is None:
        return None
    field = re.sub(AUTHOR_FORBIDDEN, '', field)
    return field.upper()


class Author(db.EntryDeletable):
    '''
    Titles tend to grab authors directly, so this class isn't used much. But,
    it's useful for sorting, creating and deleting them.
    '''

    def __init__(self, db, author_id=None, **kw):
        super().__init__('entity', 'entity_id', db, author_id, **kw)

    name = db.Field('entity_name', coercer=sanitize_author)
    alt_name = db.Field('alternate_entity_name', coercer=sanitize_author)

    def __str__(self):
        if self.alt_name:
            return f'{self.name}={self.alt_name}'
        return self.name

    def merge_author(self, other):
        '''
        Takes another author and deletes it, replacing it with this author

        Parameters
        ----------
        other : Author
            The author object to merge in and delete.

        Returns
        -------
        None.

        '''
        self.db.getcursor().execute(
            'update title_responsibility'
            ' set entity_id = %s'
            ' where entity_id = %s',
            (self.id, other.id))

        self.db.getcursor().execute(
            'delete from entity'
            ' where entity_id = %s',
            (other.id,))

        self.db.commit()
        