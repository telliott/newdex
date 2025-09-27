from mitsfs.core import db


# tested in test_indexes.py
# It is very annoying that the plural of series is series
class SeriesIndex(object):
    def __init__(self, db):
        self.db = db

    def keys(self):
        '''
        Returns
        -------
        list(str)
            A list of all the series in the dex.

        '''
        c = self.db.getcursor()
        return c.fetchlist('select series_name from series'
                           ' order by series_name')

    def search(self, series):
        '''
        Search series name for a given substring and return all the IDs that
        match

        Parameters
        ----------
        series : str
            a string to search for. Will be matched
            against the start of the name

        Returns
        -------
        list(int)
            a list of series_ids.

        '''
        c = self.db.getcursor()
        return c.fetchlist(
            "select distinct series_id"
            " from series"
            " where"
            "  series_name ilike %s",
            (f'{series}%',))

    def __getitem__(self, key):
        '''
        Allows for series retrieval by name. Requires exact match
        and returns the titles of the series sorted by the series number

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
        titles = (
            Title(self.db, title_id[0])
            for title_id
            in c.execute(
                'select title_id'
                ' from title_series'
                '  natural join series'
                ' where upper(series_name) = upper(%s)',
                (key,)))
        # titles.sort()
        return titles

    def complete(self, s):
        '''
        Autocomplete for a series name

        Parameters
        ----------
        s : string
            String to check against the start of series names.

        Returns
        -------
        list(str)
            a list of series names.

        '''
        c = self.db.getcursor()
        return c.fetchlist(
            'select series_name from series'
            ' where position(%s in upper(series_name)) = 1'
            ' order by series_name',
            (s.strip().upper(),))

    def grep(self, s):
        '''
        Parameters
        ----------
        s : string
            A streng to match against the series name. Can be a
            regular expression.

        Returns
        -------
        list(title_ids)
            A list of title_ids where the series name patial-matches
            the submitted string.
        '''
        c = self.db.getcursor()
        return c.fetchlist(
            'select title_id'
            ' from series natural join title_series'
            ' where series_name ~ %s',
            (s.upper(),))


class Series(db.Entry):
    def __init__(self, db, series_id=None, **kw):
        super().__init__('series', 'series_id', db, series_id, **kw)

    series_name = db.Field('series_name')

    def __str__(self):
        return self.series_name

    def __len__(self):
        '''
        Returns
        -------
        int
            The number of titles in this series.

        '''
        c = self.db.getcursor()
        return c.selectvalue(
            'select count(title_id) from title_series where series_id=%s',
            (self.id,))

    def __iter__(self):
        '''
        Returns
        -------
        iterator
            An iterator of Title objects representing titles in this series.
            They are ordered by series index, but that'll produce some odd
            results if there's multiple (e.g. 1,2,3)

        '''
        from mitsfs.dex.titles import Title
        c = self.db.getcursor()
        return (
            Title(self.db, title_id[0])
            for title_id
            in c.execute(
                'select title_id'
                ' from title_series'
                '  natural join series'
                ' where series_id = %s'
                ' order by order_series_by',
                (self.id,)))
