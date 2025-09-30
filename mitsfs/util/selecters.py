from mitsfs import ui


def select_generic(candidates):
    '''
    A useful generic selecter. Enumerates the options, then returns the
    chosen one.

    Parameters
    ----------
    candidates : list(object)
        The objects to select from. Must have a usable str() implementation.

    Returns
    -------
    object
        The object selected.

    '''
    n = None
    if len(candidates) == 0:
        print("Nothing found, Try again")
    if (len(candidates) == 1):
        return candidates[0]
    else:
        for i, candidate in enumerate(candidates):
            print(ui.Color.select(str(i + 1) + '.') + str(candidate))
    n = ui.readnumber('? ', 0, len(candidates) + 1, 'select')
    if n is None or n == 0:
        return None
    return candidates[n - 1]


def select_checkout(checkouts, show_members=False):
    '''
    show an enumerated list of checkouts and ask for a selection

    Parameters
    ----------
    checkouts : Checkouts
        a list of checkouts.
    show_members : boolean, optional
        Whether or not to show the members in the display. This isn't
        necessary in situations where you have already selected a member

    Returns
    -------
    Checkout
        The selected checkout.

    '''
    width = min(ui.termwidth(), 80) - 1
    print(checkouts.display(width, show_members=show_members, enum=True))
    print(ui.Color.select('Q.'), 'Back to Main Menu')
    print()

    num = ui.readnumber(
        "Select a book to check in: ",
        1,
        len(checkouts) + 1,
        escape='Q')

    if num is None:
        return None

    return checkouts[num - 1]


def select_edition(title):
    '''
    show an enumerated list of editions and ask for a selection

    Parameters
    ----------
    title : Title
        The title that contains the editions to be selected from.

    Returns
    -------
    Book
        The selected book.

    '''
    books = sorted(title.books, key=lambda x: x.shelfcode.code)
    n = None
    if len(books) == 0:
        print("Nothing found, Try again")
    else:
        for i, book in enumerate(books):
            outto = ''
            if book.outto:
                outto = f' (out to {book.outto})'
            print(
                ui.Color.select(str(i + 1) + '.') +
                '%s %s%s' % (book.shelfcode,
                             ', '.join(book.barcodes), outto))
        n = ui.readnumber('? ', 0, len(books) + 1, 'select')
    if n is None or n == 0:
        return None
    return books[n - 1]


def select_author(library):
    from mitsfs.dex.authors import Author

    authors = []
    while True:
        blank = ''
        if authors:
            blank = ' (blank to finish)'
        author = ui.read(f'Enter an author{blank}: ',
                         complete=library.catalog.authors.complete).upper()
        if not author:
            break

        selection = None
        candidates = library.catalog.authors.search(author)

        if not candidates:
            if ui.readyes(f'{author} does not exist. Create? [yN] '):
                selection = Author(library.db, name=author)
                selection.create()
        else:
            author_list = [Author(library.db, i) for i in candidates]
            # if there's only one and it's an exact match, adopt it
            if len(author_list) == 1 and author_list[0].name == author:
                selection = author_list[0]
            else:
                author_list.append(Author(library.db,
                                          name=f'Create {author}'))
                selection = select_generic(author_list)
                if selection.id is None:
                    selection.name = author
                    selection.create()
        # TODO: Ask about responsibility
        authors.append(selection)

    return authors


def select_series(library):
    from mitsfs.dex.series import Series

    series = []
    while True:
        name = ui.read('Enter a series (blank to finish): ',
                       complete=library.catalog.series.complete).upper()
        if not name:
            break

        candidates = library.catalog.series.search(name)

        if not candidates:
            if ui.readyes(f'{name} does not exist. Create? [yN] '):
                selection = Series(library.db, series_name=name)
                selection.create()
        else:
            series_list = [Series(library.db, i) for i in candidates]
            # if there's only one and it's an exact match, adopt it
            if (len(series_list) == 1 and series_list[0].series_name == name):
                selection = series_list[0]
            else:
                series_list.append(Series(library.db,
                                          series_name=f'Create {series}'))
                selection = select_generic(series_list)
                if selection is None:
                    continue
                if selection.id is None:
                    selection.series_name = name
                    selection.create()

        series_visible = ui.readyes('Is this series visible'
                                    ' on the spine? [yN] ')
        number = ui.read('Series number of the title: ')
        number_visible = ui.readyes('Is this number visible'
                                    ' on the spine? [yN] ')
        series.append((selection, number, series_visible, number_visible))

    return series
