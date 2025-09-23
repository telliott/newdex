from mitsfs.dex import indexes

class Catalog(object):
    def __init__(self, db):
        self.db = db
        
        self.titles = indexes.TitleIndex(db)
        self.authors = indexes.AuthorIndex(db)
        self.series = indexes.SeriesIndex(db)
        self.editions = indexes.ShelfcodeIndex(db)
