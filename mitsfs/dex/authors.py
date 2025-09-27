from mitsfs.core import db


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
            ' or alternate_entity_name ilike %s',
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


class Author(db.Entry):
    '''
    Titles tend to grab authors directly, so this class isn't used much. But,
    it's useful for creating them.
    '''

    def __init__(self, db, author_id=None, **kw):
        super().__init__('entity', 'entity_id', db, author_id, **kw)

    name = db.Field('entity_name')
    alt_name = db.Field('alternate_entity_name')

    def __str__(self):
        if self.alt_name:
            return f'{self.name}={self.alt_name}'
        return self.name
