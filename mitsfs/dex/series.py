from mitsfs.core import db
from mitsfs.dex import title


class Series(db.Entry):
    def __init__(self, db, series_id=None, **kw):
        super().__init__('series', 'series_id', db, series_id, **kw)

    name = db.Field('series_name')

    def __len__(self):
        c = self.db.getcursor()
        return c.selectvalue(
            'select count(title_id)' +
            ' from title' +
            '  natural join title_series' +
            '  natural join series' +
            ' where series_id=%s',
            (self.id,))

    def __iter__(self):
        # sort this properly 'cus it's convenient
        c = self.db.getcursor()
        c.execute(
            'select title_id' +
            ' from title' +
            '  natural join title_responsibility natural join entity' +
            '  natural join title_title' +
            '  natural join title_series' +
            '  natural join series' +
            ' where order_responsibility_by = 0 and order_title_by = 0' +
            '  and series_id = %s' +
            ' order by upper(entity_name), upper(title_name)',
            (self.id,))
        if c.rowcount == 0:
            return []

        return [title.Title(self.db, x[0]) for x in c.fetchall()]
