from mitsfs import db
from mitsfs.dex.coercers import coerce_datetime_no_timezone


class Timewarp(db.Entry):
    def __init__(self, db, timewarp_id=None, **kw):
        '''
        This class defines a set of start-end time periods that are ignored
        for the purpose of calculating fine. So if you have a book that falls
        due during a timewarp, it's due on the end date of the timewarps'

        Parameters
        ----------
        db : DB object
            DESCRIPTION.
        timewarp_id : int. optional
            DESCRIPTION. The timewarp to retrieve from the db. If this is none
                it will build a new timewarp that you can create into the db
        **kw : dict
            keyword arguments to set start and end.

        Returns
        -------
        None.

        '''
        super(Timewarp, self).__init__(
            'timewarp', 'timewarp_id', db, timewarp_id, **kw)

    timewarp_id = db.ReadField('timewarp_id')
    start = db.Field('timewarp_start', coerce_datetime_no_timezone)
    end = db.Field('timewarp_end', coerce_datetime_no_timezone)

    def __str__(self):
        return f'Timewarp({self.start} - {self.end})'


class Timewarps(list):

    def __init__(self, db):
        '''
        A list of all historical timewarps, sorted by end date.
        
        Primarily used to figure out the new date after a timewarp

        Parameters
        ----------
        db : Database
            The database to read from.

        Returns
        -------
        None.

        '''
        super().__init__()
        for row in self.load_from_db(db):
            (t_id, start, end) = row
            self.append(Timewarp(db, t_id, start=start, end=end))
        self.sort(key=lambda x: x.end)
        self.db = db
        
    def load_from_db(self, db):
        c = db.getcursor()
        c.execute('select timewarp_id, timewarp_start, timewarp_end'
                  ' from timewarp')
        return c.fetchall()

    def __repr__(self):
        return "\n".join(["%s" % str(t) for t in self])

    def add(self, start, end):
        t = Timewarp(
            self.db, None,
            start=start,
            end=end,
            )
        t.create()
        self.append(t)
        self.sort(key=lambda x: x.end)

    def warp_date(self, date):
        '''
        Given a due date, warps aheads to a new future date where the book is
        now due.

        Needs to loop through rather than find the first match because there
        might be overlapping end dates, and one warp might put you into
        another warp.

        Parameters
        ----------
        date : date
            The initial due date of the book.

        Returns
        -------
        date : date
            the new due date of the book.

        '''
        for warp in self:
            if date >= warp.start and date <= warp.end:
                date = warp.end
        return coerce_datetime_no_timezone(date)