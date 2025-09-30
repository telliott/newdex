import sys

from mitsfs import ui
from mitsfs import library
from mitsfs.core import settings
from mitsfs.dex.titles import Title
from mitsfs.dex.authors import Author
from mitsfs.dex.books import Book
from mitsfs.util import selecters

title = None

'''
hamster is the book tracking system. It handles everything involving books -
adding/deleting titles, authors, series, editions, etc

Hamster is built around a set of menus, each of which contains
its own functions. In general, when you return from one of those functions,
it will print the menu again. So if you want to clear the screen, generate
a header, and write some stuff before the menu prints, you need to do it
before you return from the function. Otherwise, something else would
clear the screen and the user never seens your very important message.

This is the case with going back up the menu stack. If your menu's function
pointer is None, the menu will return control back to your method, at which
point you likely want to print the header for the menu that's being
returned to.
'''


def no_book_header():
    '''
    Clears the screen and prints the header when there's no title selected'
    '''

    ui.clear_screen()
    width = min(ui.termwidth(), 80) - 1
    print('-' * width)
    print(f'{"MITSFS Book Management System":^{width}}')
    print('-' * width)


def book_header(header='Book Menu'):
    '''
    Clears the screen and prints the header for the selected book'
    '''
    ui.clear_screen()
    width = min(ui.termwidth(), 80) - 1
    header = f'  {header}  '

    print(f'{header:-^{width}}')

    # first row contains author and editions
    #

    name = str(title.titles)
    outlist = []

    for book in sorted(title.books, key=lambda x: x.shelfcode.code):
        if book.out:
            outlist += [ui.Color.warning(f'{book.shelfcode.code}'
                                         f' ({book.outto})')]
        else:
            outlist += [ui.Color.good(book.shelfcode.code)]
    shelfcodes = ', '.join(outlist)

    spaces = ' ' * max(1, width - len(name) - ui.len_color_str(shelfcodes))
    print(f'{name}{spaces}{shelfcodes}')

    # second row contains the author and the series.
    author = str(title.authors)
    series = str(title.series)
    spaces = ' ' * max(1, width - len(author) - len(series))
    print(f'{author}{spaces}{series}')

    print('-' * width)


def recursive_menu(*args, **kw):
    return ui.menu(*args, cleanup=library.db.rollback, **kw)


def main(args):
    global library  # all the information about the library.
    global title  # if a title is selected, it will be in here

    library = library.Library()
    print("Hello")
    if library.db.dsn != settings.DATABASE_DSN:
        library.log.warn(f'Using database: {library.db.dsn}')
        exit()

    main_menu('')


def main_menu(line):

    def new_author(line):
        no_book_header()
        print('Create an author:')
        name = ui.read('Author name (last, first): ').upper()
        if not name:
            return

        alt_name = ui.read('Alternate name (blank if none): ').upper()
        author = Author(library.db, name=name, alt_name=alt_name)
        author.create()
        no_book_header()
        print(f'{author} created')

    def new_title(line):
        no_book_header()
        print("Create a new title")

        authors = selecters.select_author(library)

        titles = []
        while True:
            blank = ''
            if titles:
                blank = ' (blank to finish)'
            name = ui.read(f'Enter a title{blank}: ',
                           complete=library.catalog.titles.complete).upper()
            if not name:
                break

            candidates = library.catalog.titles.complete(name,
                                                         authors[0].name)
            if name in candidates:
                if not ui.readyes(f'{name} already exists. Continue? [yN] '):
                    continue
            alt_name = ui.read('Alternate title?: ') or None

            titles.append(name, alt_name)

        series = selecters.select_series(library)

        shelfcode = ui.readshelfcode('Quick add shelfcode?: ',
                                     library.shelfcodes)

        title = Title(library.db)
        title.create()
        for author in authors:
            title.add_author(author)
        for name, alt in titles:
            title.add_title(name, alt)
        for (volume, series_index, series_visible, number_visible) in series:
            title.add_series(volume, series_index,
                             series_visible, number_visible)

        if shelfcode:
            book = Book(library.db, title=title.id,
                        shelfcode=library.shelfcodes[shelfcode])
            book.create()

        library.db.commit()
        no_book_header()
        print(f'Created {title}')

    def select(line):
        '''
        Select a user to work with in the user menus
        '''
        global title
        title = ui.specify(library)
        if title:
            book_menu(line)
        no_book_header()

    no_book_header()
    print('Main Menu')
    print()

    recursive_menu([
        ('S', 'Select Book', select),
        ('A', 'Create Author', new_author),
        # ('V', 'Create Series', new_series),
        ('T', 'Create Title', new_title),
        ('Q', 'Quit', None),
        ])


def book_menu(line):

    def unselect(line):
        '''
        Stop working with this title
        '''
        global title
        title = None
        no_book_header()
        print('Main Menu')
        print()
        # returning an explicit False lets us go up a menu level
        return False

    def add_edition(line):
        book_header()
        print("Adding a New Edition")
        shelfcode = ui.readshelfcode('Shelfcode for book: ',
                                     library.shelfcodes)
        double = None
        series_visible = False
        if library.shelfcodes[shelfcode].is_double:
            double = ui.read("Double value: ")

        if title.series:
            series_visible = ui.readyes(f'Is series ({title.series})'
                                        ' visible? [yN] ')

        review = ui.readyes('Review copy? [yN] ')
        book = Book(library.db, title=title.id,
                    shelfcode=library.shelfcodes[shelfcode],
                    doublecrap=double, review=review, visible=series_visible)
        book.create()

        book_header()
        print(f'Added {shelfcode}')

    def edit_title(line):
        ''' change the title'''
        book_header()
        print('Change Title')
        if len(title.titles) > 1:
            print('Select a title to update:')
            old_title = selecters.select_generic(title.titles)
        else:
            old_title = title.titles[0]

        old_alt = ''
        if '=' in old_title:
            (old_title, old_alt) = old_title.split('=')

        new_title = ui.read('Enter a new title: ', preload=old_title,
                            complete=library.catalog.titles.complete).upper()
        new_alt = ui.read('Enter a new alternate title: ', preload=old_alt,
                          complete=library.catalog.titles.complete).upper() \
            or None
        title.update_title(old_title, new_title, new_alt)
        library.db.commit()
        book_header()

    def add_title(line):
        book_header()
        print('Add Title')
        titles = []
        while True:
            name = ui.read('Enter a title (blank to finish): ',
                           complete=library.catalog.titles.complete).upper()
            if not name:
                break

            candidates = library.catalog.titles.complete(name)
            if name in candidates:
                if not ui.readyes(f'{name} already exists. Continue? [yN] '):
                    continue

            alt_name = ui.read('Alternate title?: ') or None

            titles.append((name, alt_name))

        for name, alt in titles:
            title.add_title(name, alt)
        library.db.commit()

        book_header()

    def add_series(line):
        book_header()
        print('Add Series')
        series = selecters.select_series(library)
        for (volume, series_index, series_visible, number_visible) in series:
            title.add_series(volume, series_index,
                             series_visible, number_visible)
        library.db.commit()

    def withdraw(line):
        book = selecters.select_edition(title)
        if book:
            book.withdraw()
            book_header()
            print('Edition withdrawn')

    book_header()

    print('Main Menu')
    print()

    recursive_menu([
        ('E', 'Add Edition', add_edition),
        ('W', 'Withdraw Edition', withdraw),
        ('T', 'Edit Title', edit_title),
        ('A', 'Add Title', add_title),
        ('P', 'Put Entry into Series', add_series),
        ('Q', 'Unselect Book', unselect),
        ])


if __name__ == '__main__':
    main(sys.argv)
