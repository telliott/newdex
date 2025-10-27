import os
import sys
import math
from collections import defaultdict

from mitsfs import library
from mitsfs.core import settings
from mitsfs.dex.inventory import Inventories
from mitsfs.util import selecters, ui
from mitsfs.util import tex

shelfcode = None

'''
inven runs the inventory process. 

Inven is built around a set of menus, each of which contains
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
  

def no_shelfcode_header():
    '''
    Clears the screen and prints the header when there's no shelfcode selected'
    '''
    inventory = library.inventory
    head = ' Inventory '
    if inventory:
        head += f'({inventory.description}) '
        head = ui.Color.warning(head)
    
    ui.clear_screen()
    width = min(ui.termwidth(), 80) - 1
    print('-' * width)
    print(f'{head:^{width}}')
    print('-' * width)


def shelfcode_header(header='Shelfcode Menu'):
    '''
    Clears the screen and prints the header for the selected shelfcode'
    '''
    ui.clear_screen()
    width = min(ui.termwidth(), 80) - 1
    header = f'  {header}  '

    print(f'{header:-^{width}}')

    # first row contains Shelfcode and progress
    total = 0
    complete = 0
    
    for section in library.inventory.sections.get(shelfcode):
        total += 1
        if section.complete:
            complete += 1
    
    summary = f'{complete}/{total}'
    if total == complete:
        summary = ui.Color.good(summary)
    else:
        summary = ui.Color.warning(summary)
    
    name = shelfcode.detail

    spaces = ' ' * max(1, width - len(name) - ui.len_color_str(summary))
    print(f'{name}{spaces}{summary}')

    # second row contains the number of missing books
    missing = len(library.inventory.get_missing_books(shelfcode))
    second_line = f'{missing} missing'
    spaces = ' ' * max(1, width - len(second_line))
    print(f'{spaces}{second_line}')

    print('-' * width)

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

    def open_inventory(line):
        '''
        Start a new inventory. If there's no open inventory, the only option
        available.
        '''
        no_shelfcode_header()
        description = ui.read('Enter an inventory description: ')
        i = Inventories(library.db)
        i.create(description)
        library.reset_inventory()
        no_shelfcode_header()

    def select(line):
        '''
        Select a shelfcode to do missing/found with
        '''
        global shelfcode
        shelfcode = selecters.select_shelfcode(library.shelfcodes)
        if shelfcode:
            shelfcode_menu(line)
        no_shelfcode_header()

    def generate_files(line):
        '''
        Generate the shelf files needed to do this inventory. Writes them
        all into /tmp/inventory/<inventory_id>

        '''
        path = f'/tmp/inventory/{library.inventory.id}'
        if not os.path.exists(path):
            os.makedirs(path)

        for shelfcode in library.shelfcodes.values():
            sections = library.inventory.sections.get(shelfcode)          
            print(f'Fecthing {shelfcode.code}...')
            titles = library.catalog.titles.book_titles(shelfcode=shelfcode)
            if not titles:
                print(f'No books for {shelfcode.code}. Continuing...')
                continue
            print('Sorting...')
            titles.sort(key=lambda x: x.sortkey())
            titles_per_section = math.ceil(len(titles)/len(sections))
            
            count = 0
            section = 0
            fp = None
 
            for title in titles:
                if count % titles_per_section == 0:
                    if fp:
                        fp.write(tex.tex_footer())
                        fp.close()
                    section += 1
                    sc = shelfcode.code.replace('/', '_')
                    fp = open(f'{path}/{sc}_{section}.tex', 'w')            
                    print(f'Writing {sc}_{section}...')
                    
                    fp.write(tex.tex_header(
                        'Invendex',
                        f'{shelfcode.code} section {section}'))               
                
                shelfcount = int(title.codes[shelfcode.code])
                fp.write('\\Book{%s}{%s}{%s} %% %s' % (
                    tex.texquote(title.authortxt),
                    tex.texquote(tex.nicetitle(title)),
                    shelfcount, str(title)))
                fp.write("\n")
                count += 1
            fp.write(tex.tex_footer())
            fp.close()

    
    def stats(line):
        '''
        For each shelfcode, print who many sections are complete and how
        many books have been marked missing
        '''
        no_shelfcode_header()
        header = ('shelfcode', 'progress', 'missing count')
        total = defaultdict(int)
        complete = defaultdict(int)
        stats= []
        
        for section in library.inventory.sections.get():
            total[section.shelfcode] += 1
            if section.complete:
                complete[section.shelfcode] += 1
        
        missing = dict(library.inventory.stats())
        
        for section in total.keys():
            summary = f'{complete.get(section, 0)}/{total[section]}'
            if total[section] == complete.get(section, 0):
                summary = ui.Color.good(summary)
            else:
                summary = ui.Color.warning(summary)

            stats.append((section, summary, missing.get(section, 0)))

        print(ui.tabulate([header] + sorted(stats, key=lambda x: x[0])))
    
    def close_inventory(line):
        '''
        Close up the inventory. We are done! Will warn you if there are
        unreported sections
        '''
        no_shelfcode_header()
        incomplete = [f'{section.shelfcode}_{section.section}' 
                      for section in library.inventory.sections.get()
                      if not section.complete]
        if incomplete:
            print(ui.Color.warning(
                'The following sections have not been marked complete: ' +
                ' '.join(incomplete)))
        if ui.readyes("Confirm that inventory is complete? [yN]: "):
            inv = library.inventory
            inv.close()
            no_shelfcode_header()
            for book in inv.get_missing_books():
                print (ui.Color.warning(f'{book} withdrawn'))
             
        
    def menu_options():
        if library.inventory:
            menu = [
                ('S', 'Select Shelfcode', select),
                ('G', 'Generate Inventory Files', generate_files),
                ('I', 'Inventory Stats', stats),
                ('C', 'Close Inventory', close_inventory)
                ]        
        else:
            menu = [('O', 'Open Inventory', open_inventory)]
        menu.append(('Q', 'Quit', None))
        return menu

    no_shelfcode_header()

    recursive_menu(menu_options, title='Main Menu')


def shelfcode_menu(line):
    '''
    Working on a specific shelfcode - checking out, completing, losing and
    finding books...
    '''
    def book_predicate(book):
        return book.shelfcode == shelfcode

    def missing(line):
        '''
        Mark a book in the library missing.
        '''
        shelfcode_header()
        print('Report Book Missing')
        while True:
            book = ui.specify_book(library, book_predicate=book_predicate)
            if not book:
                break
            library.inventory.report_missing_book(book)
            print(f'{book} marked missing')
        shelfcode_header()
        
    def found(line):
        '''
        Mark a missing book found
        '''
        shelfcode_header()
        print('Report Book Found')
        while True:
            options = library.inventory.get_missing_books(shelfcode)
           
            if not options:
                print("There are no books missing from this shelfcode.")
                return
    
            if len(options) > 20:
                author = selecters.select_author(library, 
                                                 create=False, single=True)
                if author:
                    #TODO: use author ids here
                    options = [book for book in options 
                               if str(author) in book.authors]
            book = selecters.select_generic(options)
            if not book:
                break
            library.inventory.find_book(book)
            print(f'{book} restored')
        shelfcode_header()
    
    def take_section(line):
        '''
        Claim a section to work on for a member
        '''
        sections = library.inventory.sections.get(shelfcode)
        shelfcode_header()
        section = ui.readnumber('Enter the {shelfcode} section: ', 
                                1, len(sections) + 1)
        for i in sections:
            if i.section == section:
                if i.member_id:
                    print(f'{i.shelfcode} section {i.section} has already'
                          ' been claimed by {i.out_to}.')
                    if not ui.readyes('Take over? [yN] '):
                        return
        member = ui.specify_member(library.members)
        library.inventory.sections.checkout_section(shelfcode, section, member)
        shelfcode_header()
        print(f'{shelfcode.code} section {section} assigned to {member}')
        
    def status(line):
        '''
        Print the details about the status of each section of this shelfcode
        '''
        shelfcode_header()
        print(ui.tabulate([(section.shelfcode, section.section, 
                            'Done' if section.complete else 'Open', 
                            section.out_to or '') 
                           for section 
                           in library.inventory.sections.get(shelfcode)]))

    def complete_section(line):
        '''
        Mark a section completed
        '''
        sections = library.inventory.sections.get(shelfcode)
        shelfcode_header()

        section = ui.readnumber('Enter the {shelfcode} section: ', 
                                1, len(sections) + 1)
        for i in sections:
            if i.section == section:
                if i.complete:
                    print(ui.Color.warning(
                        '{i.shelfcode} section {i.section} has already'
                        ' been checked in!'))
                    return
        library.inventory.sections.complete_section(shelfcode, section)
        shelfcode_header()
    
    shelfcode_header()

    recursive_menu([
        ('M', 'Report Missing Book', missing),
        ('F', 'Find Missing Book', found),
        ('T', 'Take Section', take_section),
        ('S', 'Show Status', status),
        ('C', 'Complete Section', complete_section),
        ('Q', 'Back to Main Menu', None),
        ], title='Shelfcode Updates')

    shelfcode_header()


if __name__ == '__main__':
    main(sys.argv)

