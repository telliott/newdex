from mitsfs.dex import titles, authors, series, shelfcodes, books
from mitsfs.core import settings, dexline
from mitsfs.util import ui

class Catalog(object):
    def __init__(self, db):
        self.db = db

        self.titles = titles.Titles(db)
        self.authors = authors.Authors(db)
        self.series = series.SeriesIndex(db)
        self.shelfcodes = settings.shelfcodes_global \
            or shelfcodes.Shelfcodes(self.db)

    def grep(self, candidate):
        if '<' in candidate:
            # we need to check against each section and only return ones
            # that match everything specified
            candidates = candidate.split('<')
            ids = {}
            ids_filled = False

            # start with author
            if candidates[0]:
                ids = set(self.authors.grep(candidates[0]))
                ids_filled = True

            # remove anything that doesn't also match title
            if candidates[1]:
                title_ids = set(self.titles.grep(candidates[1]))
                if ids_filled:
                    ids = ids.intersection(title_ids)
                else:
                    ids = title_ids
                    ids_filled = True

            # remove anything that doesn't also match series
            if len(candidates) > 2 and candidates[2]:
                series_ids = set(self.series.grep(candidates[2]))
                if ids_filled:
                    ids = ids.intersection(series_ids)
                else:
                    ids = set(series_ids)
                    ids_filled = True

            # remove anything that isn't in a specified shelfcode
            if len(candidates) > 3 and candidates[3]:
                code_ids = []
                for shelfcode in candidates[3].split(','):
                    code_ids += self.shelfcodes.grep(shelfcode.upper())
                if ids_filled:
                    ids = ids.intersection(code_ids)
                else:
                    ids = set(code_ids)
        else:
            # single value, so just look for it everywhere
            ids = set(self.titles.grep(candidate)
                      + self.authors.grep(candidate)
                      + self.series.grep(candidate))
        if not ids:
            return [ui.Color.warning('No titles found')]
        title_list = [titles.Title(self.db, id) for id in ids]
        title_list.sort(key=lambda x: x.sortkey())
        return title_list

    def add_from_dexline(self, line):
        # primarily a helper function for testing. takes a dexline string and
        # writes it into the db
        title = titles.Title(self.db)
        title.create()

        if type(line) is str:
            line = dexline.DexLine(line)

        for author in line.authors:
            alt = None
            if '=' in author:
                author, alt = '='.split(author)
            if author not in self.authors:
                author = authors.Author(self.db, name=author, alt_name=alt)
                author.create(commit=False)
            else:
                authorid = self.authors.search(author)[0]
                author = authors.Author(self.db, authorid)
            title.add_author(author)

        for title_name in line.titles:
            alt = None
            if '=' in title_name:
                title_name, alt = '='.split(title_name)
            title.add_title(title_name, alt, commit=False)

        for seriesval in line.series:
            (name, index, series_visible,
             number_visible) = series.munge_series(seriesval)
        if name not in self.series:
            seriesval = series.Series(self.db, series_name=name)
            seriesval.create(commit=False)
        else:
            seriesid = self.series.search(name)[0]
            seriesval = series.Series(self.db, seriesid)
        title.add_series(seriesval, index, series_visible, number_visible)

        for v in line.codes.values():
            for i in range(0, v.count):
                book = books.Book(self.db, title=title.id,
                                  shelfcode=self.shelfcodes[v.shelfcode].id)
                book.create(commit=False)

        self.db.commit()
