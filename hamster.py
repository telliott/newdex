import os
import sys
import re
from datetime import datetime

from mitsfs import library
from mitsfs.core import settings
from mitsfs.dex.series import Series, munge_series, sanitize_series
from mitsfs.dex.titles import Title, sanitize_title
from mitsfs.dex.authors import Author, sanitize_author
from mitsfs.dex.books import Book
from mitsfs.util import utils, exceptions, selecters, tex, ui


title = None

'''
hamster is the book inventory system. It handles everything involving books -
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
    head = f'MITSFS Book Management System ({library.db.dsn})'
    print(f'{head:^{width}}')
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

def progress_meter(it, divisor=1000):
    count = 0
    for i in it:
        if count % divisor == 0:
            print('.', end='')
        count += 1
        yield i

def recursive_menu(*args, **kw):
    return ui.menu(*args, cleanup=library.db.rollback, **kw)


def main(args):
    global library  # all the information about the library.
    global title  # if a title is selected, it will be in here

    library = library.Library()
    if library.db.dsn != settings.DATABASE_DSN:
        library.log.warn(f'Using database: {library.db.dsn}')

    main_menu('')


def main_menu(line):

    def grep(line):
        no_book_header()
        while True:
            print('Enter a grep pattern.')
            print('Can search on sections using < notation.'
                  ' (blank line to exit)')
            grepstring = ui.read('> ')
            if not grepstring:
                break
            for title in library.catalog.grep(grepstring):
                print(str(title))
        no_book_header()

    def select(line):
        '''
        Select a title to work with in the title menus
        '''
        global title
        title = ui.specify(library)
        if title:
            book_menu(line)
        no_book_header()

    def new_title(line):
        '''
        Central function to quickly enter a new book. Will let you do basic
        creation all in one place.
        '''
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
            alt_name = ui.read('Alternate title?: ')

            titles.append((name.upper(),
                           alt_name.upper() if alt_name else None))

        series = selecters.select_series(library)

        shelfcode = selecters.select_shelfcode(library.shelfcodes,
                                               'Quick add shelfcode?: ')

        no_book_header()
        title = Title(library.db)
        title.create()
        for author in authors:
            title.add_author(author)
        for name, alt in titles:
            try: 
                title.add_title(name, alt.upper() if alt else None)
            except exceptions.DuplicateEntry:
                print(f'skipping {name}: already attached to this title')
        for (volume, series_index, series_visible, number_visible) in series:
            try: 
                title.add_series(volume, series_index,
                                 series_visible, number_visible)
            except exceptions.DuplicateEntry:
                print(f'skipping {volume.series_name}:'
                      ' already attached to this title')

        if shelfcode:
            book = Book(library.db, title=title.id,
                        shelfcode=shelfcode)
            book.create()

        library.db.commit()
        print(f'Created {title}')

    no_book_header()

    recursive_menu([
        ('S', 'Select Book', select),
        ('G', 'Grep for Books', grep),
        ('T', 'Create Title', new_title),
        ('C', 'Create/Edit Elements', edit_menu),
        ('E', 'Export Files', export_menu),
        ('Q', 'Quit', None),
        ], title='Main Menu')


def edit_menu(line):

    def new_author(line):
        no_book_header()
        print('Create an author:')
        name = sanitize_author(ui.read('Author name (last, first): ')).upper()
        if not name:
            return

        alt_name = sanitize_author(ui.read('Alternate name (blank if none): ')
                                   ).upper() or None
        author = Author(library.db, name=name, alt_name=alt_name)
        author.create()
        no_book_header()
        print(f'{author} created')

    def merge_authors(line):
        no_book_header()
        print('Select the author to keep')
        keep = selecters.select_author(library, create=False, single=True)
        print(f'Select the author to merge into {keep}')
        merge = selecters.select_author(library, create=False, single=True)
        merge_txt = str(merge)
        print(f'Merge {merge} into {keep}?')
        merge_txt = str(merge)
        if ui.readyes("Confirm? [yN]: "):
            keep.merge_author(merge)

        no_book_header()
        print(f'Merged {merge_txt} into {keep}')

    def new_series(line):
        no_book_header()
        print('Create a series:')
        name = sanitize_series(ui.read('Enter a series (blank to finish): ')
                               ).upper()
        if not name:
            no_book_header()
            return

        candidates = library.catalog.series.search(name)
        if candidates:
            print('The following series already exist.')
            for series in [Series(library.db, i) for i in candidates]:
                print(f'\t{series.series_name}')
            if not ui.readyes('Continue? [yN] '):
                no_book_header()
                return

        selection = Series(library.db, series_name=name)
        selection.create()
        no_book_header()
        print(f'{name} created')

    def merge_series(line):
        no_book_header()
        print('Select the series to keep')
        keep = selecters.select_series(library, create=False, single=True)
        print(f'Select the series to merge into {keep}')
        merge = selecters.select_series(library, create=False, single=True)
        print(f'Merge {merge} into {keep}?')
        merge_txt = str(merge)
        if ui.readyes("Confirm? [yN]: "):
            keep.merge_series(merge)

        no_book_header()
        print(f'Merged {merge_txt} into {keep}')

    no_book_header()

    recursive_menu([
        ('A', 'Create Author', new_author),
        ('M', 'Merge Authors', merge_authors),
        ('S', 'Create Series', new_series),
        ('N', 'Merge Series', merge_series),
        ('Q', 'Back to Main Menu', None),
        ], title='Edit Menu')


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
        '''
        Add a physical copy of this book to the title
        '''
        book_header()
        print("Adding a New Edition")
        shelfcode = selecters.select_shelfcode(library.shelfcodes,
                                               'Shelfcode for book: ')
        double = None
        series_visible = False
        if shelfcode.is_double:
            double = ui.read("Double value: ")

        if title.series:
            series_visible = ui.readyes(f'Is series ({title.series})'
                                        ' visible? [yN] ')

        review = ui.readyes('Review copy? [yN] ')
        book = Book(library.db, title=title.id,
                    shelfcode=shelfcode,
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

        new_title = sanitize_title(
            ui.read('Enter a new title: ', preload=old_title,
                    complete=library.catalog.titles.complete)).upper()
        if not title:
            book_header()
            print("Title can't be blank")
            return

        new_alt = sanitize_title(
            ui.read('Enter a new alternate title: ', preload=old_alt,
                    complete=library.catalog.titles.complete)).upper() \
            or None

        title.update_title(old_title, new_title, new_alt)
        library.db.commit()
        book_header()

    def add_series(line):
        '''Add a series to the title'''
        book_header()
        print('Add Series')
        series = selecters.select_series(library)
        for (volume, series_index, series_visible, number_visible) in series:
            try:
                title.add_series(volume, series_index,
                                 series_visible, number_visible)
            except exceptions.DuplicateEntry:
                print(f'{volume.series_name} is already attached')
                continue

        library.db.commit()

    def withdraw(line):
        '''withdraw this book from the library'''
        book = selecters.select_edition(title)
        if book:
            book.withdraw()
            book_header()
            print('Edition withdrawn')

    book_header()

    recursive_menu([
        ('E', 'Add Edition', add_edition),
        ('W', 'Withdraw Edition', withdraw),
        ('T', 'Edit Title', edit_title),
        ('A', 'Advanced Edit', advanced_edit),
        ('Q', 'Unselect Book', unselect),
        ], title='Edit Book')


def advanced_edit(line):

    def add_title(line):
        '''Add a title to this book'''
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

            alt_name = ui.read('Alternate title?: ')
            
            titles.append((name.upper(), alt_name.upper if alt_name else None))

        book_header()
        for name, alt in titles:
            try: 
                title.add_title(name, alt)
            except exceptions.DuplicateEntry:
                print(f'skipping {name}: already attached to this title')
        library.db.commit()


    def remove_title(line):
        '''Remove a title from this book. Can't remove the last one'''
        book_header()
        print('Remove Title')
        if len(title.titles) > 1:
            print('Select a title to remove:')
            old_title = selecters.select_generic(title.titles)
        else:
            book_header()
            print("Can't remove the only title")
            return

        old_alt = ''
        if '=' in old_title:
            (old_title, old_alt) = old_title.split('=')
        title.remove_title(old_title)
        library.db.commit()
        book_header()

    def add_author(line):
        '''Add an author to this book'''
        book_header()
        print('Add Author')
        authors = selecters.select_author(library)

        for author in authors:
            title.add_author(author)
        library.db.commit()

        book_header()

    def remove_author(line):
        book_header()
        print('Remove Author')

        author = selecters.select_generic(title.author_objects)
        title.remove_author(author)
        library.db.commit()
        book_header()

    def add_series(line):
        book_header()
        print('Add Series')
        series = selecters.select_series(library)

        book_header()
        for (selection, number, series_visible, number_visible) in series:
            try:
                title.add_series(selection, number,
                                 series_visible, number_visible)
            except exceptions.DuplicateEntry:
                print(f'{selection.series_name} is already attached')
                continue

        library.db.commit()


    def remove_series(line):
        book_header()
        print('Remove Series')

        series = selecters.select_generic(title.series)
        (name, _, _, _) = munge_series(series)

        title.remove_series(name)
        library.db.commit()
        book_header()

    def merge_title(line):
        book_header()
        print('Specify the title to merge')
        other_book = ui.specify(library)

        print(f'Merging {other_book} into this one')
        if ui.readyes("Confirm? [yN]: "):
            title.merge_title(other_book)
        book_header()

    def menu_options():
        menu = [('T', 'Add Title', add_title)]
        if len(title.titles) > 1:
            menu.append(('R', 'Remove Title', remove_title))
        menu.append(('A', 'Add Author', add_author))
        if len(title.authors) > 1:
            menu.append(('U', 'Remove Author', remove_author))
        menu.append(('S', 'Add Series', add_series))
        if title.series:
            menu.append(('V', 'Remove Series', remove_series))

        menu.append(('M', 'Merge Another Title', merge_title))
        menu.append(('Q', 'Back to Book Menu', None))
        return menu

    book_header()

    recursive_menu(menu_options, title='Advanced Title Edits')

    book_header()


def export_menu(line):

    def backup_db(line):
        print('Backup Database')
        match = re.search('dbname=([^ ]+)', library.db.dsn)
        database = match.group(1)

        path = settings.BACKUP_DIRECTORY
        filename = f'Dexdb_{utils.timestamp()}.sql'

        os.system(f'pg_dump -d {database} -f {path}/{filename}')
        no_book_header()
        print(f'Exported the db to {path}/{filename}')

    def export_text(line):
        no_book_header()
        print('Export to Text')
        path = selecters.select_safe_filename(preload='pinkdex.txt')
        fp = open(path, 'w')

        print("Fetching...")
        titles = library.catalog.titles.book_titles()
        print('Sorting...')
        titles.sort(key=lambda x: x.sortkey())
        print('Writing...')
        for title in titles:
            try:
                fp.write(str(title) + "\n")
            except exceptions.InvalidShelfcode:
                print(f'BAD SHELFCODE: {title.titles}')
                continue
            except Exception:
                print(f'Problematic: {title.titles}')
                continue

        fp.close()
        print(f'Exported the text dex to {path}')

    def export_dex(line):
        no_book_header()
        print('Export to Dex')
        path = selecters.select_safe_filename('pinkdex.tex')
        fp = open(path, 'w')

        fp.write(r'\def\dexname{Pinkdex}')
        fp.write("\n")
        fp.write(r'\def\Period{0}' + "\n")
        fp.write(r'\input %s/dextex-current.tex' % settings.TEXBASE)
        fp.write("\n")

        print("Fetching...")
        titles = library.catalog.titles.book_titles()
        print('Sorting...')
        titles.sort(key=lambda x: x.sortkey())
        print('Writing...')

        letter = None

        for title in titles:
            newletter = None
            if (len(getattr(title, 'placeauthor')) > 0):
                newletter = getattr(title, 'placeauthor').upper()[0]

            if letter != newletter:
                if letter is not None:
                    fp.write(r'\NextLetter' + "\n")
                letter = newletter
                print(letter)
                sys.stdout.flush()
            try:
                fp.write('\\Book{%s}{%s}{%s}\n' % (
                    tex.texquote(title.authortxt),
                    tex.texquote(tex.nicetitle(title)),
                    tex.texquote(str(title.codes).replace(':', r'\:'))))
            except Exception:
                print(f'Problematic: {title.titles}')
                continue

        fp.write(r'\vfill \eject \bye' + "\n")
        fp.close()
        print('done.')

    def export_shelf(line):
        no_book_header()
        print('Export to Dex')
        shelfcode = selecters.select_shelfcode(library.shelfcodes)

        file_code = re.sub('/', '_', shelfcode.code)
        path = selecters.select_safe_filename(
            preload=f'pinkdex_{file_code}.tex')
        fp = open(path, 'w')

        print("Fetching...")
        titles = library.catalog.titles.book_titles(
            shelfcode=shelfcode)
        print('Sorting...')
        titles.sort(key=lambda x: x.sortkey())
        print('Writing...')

        fp.write(r'\def\dexname{Pinkdex}')
        fp.write("\n")
        fp.write(r'\def\Reverse{1}' + "\n")
        fp.write(r'\def\Shelf{1}' + "\n")
        fp.write(r'\def\Supple{%s}' % shelfcode.code)
        fp.write("\n")
        fp.write(r'\def\Period{3}' + "\n")
        fp.write(r'\input %s/dextex-current.tex' % settings.TEXBASE)
        fp.write("\n")

        for title in titles:
            count = title.codes[shelfcode.code]

            fp.write('\\Book{%s}{%s}{%s} %% %s' % (
                tex.texquote(title.authortxt),
                tex.texquote(tex.nicetitle(title)),
                count, str(title)))
            fp.write("\n")
        fp.write(r'\vfill \eject \bye' + "\n")
        fp.close()
        print('done.')

    no_book_header()

    recursive_menu([
        ('B', 'Backup Database', backup_db),
        ('T', 'Export Text Dex', export_text),
        ('D', 'Export Full Dex', export_dex),
        ('S', 'Export Shelfcode', export_shelf),
        ('Q', 'Back to Main Menu', None),
        ], title='Edit Book')


if __name__ == '__main__':
    main(sys.argv)
