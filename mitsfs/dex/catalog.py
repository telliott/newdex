from mitsfs.dex import titles, authors, series, shelfcodes
from mitsfs.core import settings


class Catalog(object):
    def __init__(self, db):
        self.db = db

        self.titles = titles.Titles(db)
        self.authors = authors.Authors(db)
        self.series = series.SeriesIndex(db)
        self.editions = settings.shelfcodes_global or shelfcodes.Shelfcodes(db)

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
                    code_ids += self.editions.grep(shelfcode.upper())
                if ids_filled:
                    ids = ids.intersection(code_ids)
                else:
                    ids = set(code_ids)
        else:
            # single value, so just look for it everywhere
            ids = set(self.titles.grep(candidate)
                      + self.authors.grep(candidate)
                      + self.series.grep(candidate))
        title_list = [titles.Title(self.db, id) for id in ids]
        title_list.sort(key=lambda x: x.sortkey())
        return title_list
