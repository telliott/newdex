#!/usr/bin/python
"""

Keep the pain of python's readline interface down to a dull roar

"""


import array
import curses
import dateutil.parser
import decimal
import fcntl
import itertools
import logging
import os
import re
import readline
import sys
import termios
import traceback
import pprint

from mitsfs.error import handle_exception
from mitsfs.barcode import validate_barcode

try:
    import ctypes
    we_get_ctypes = True
except ImportError:
    we_get_ctypes = False


__all__ = [
    'read', 'readlines', 'readnumber', 'specify', 'specify_book',
    'menu', 'readyes', 'banner', 'motd', 'tabulate', 'specify_member',
    'readvalidate', 'readmoney', 'readdate', 'menuize_dict',
    'clear_screen', 'readbarcode', 'money_str', 'reademail',
    'readaddress', 'readinitials', 'Color', 'termwidth', 'len_color_str',
    'pfill', 'lfill', 'smul', 'rmul', 'bold', 'sgr0', 'termheight',
    ]


class CompleteAdapter(object):
    def __init__(self, callback):
        self.callback = callback
        self.state = None
        self.iterator = None
        self.errlog = None
        self.log = logging.getLogger('mitsfs.CompleteAdapter')

    def __call__(self, text, state):
        try:
            if self.state is None or state <= self.state:
                self.iterator = iter(self.callback(text))
                self.last = None
            self.state = state
            try:
                result = next(self.iterator)
            except StopIteration:
                result = None
            return result
        except:
            exc = traceback.format_exc()
            self.errlog += exc
            self.log.error('%s', exc)


# This is the way to do tab completion on a mac. If we lose it on Athena,
# revert to the other line.
readline.parse_and_bind('bind ^I rl_complete')
# readline.parse_and_bind("tab: complete")
readline.set_completer_delims('@|')


# Add color to command line.
#
# Only works on linux

_COLORS = (
    'BLACK', 'RED', 'GREEN', 'YELLOW',
    'BLUE', 'MAGENTA', 'CYAN', 'WHITE',
    )

_use_color = 'MITSFS_SUPRESS_COLOR' not in os.environ


def color(text, color_name, bold=False):
    if _use_color and color_name in _COLORS:
        return '\033[{0};{1}m{2}\033[0m'.format(
            int(bold), _COLORS.index(color_name) + 30, text)
    return text


class Color(object):
    _info = "GREEN"
    _select = "RED"
    _good = "CYAN"
    _warning = "RED"

    @staticmethod
    def info(s):
        return color(str(s), Color._info)

    @staticmethod
    def select(s):
        return color(str(s), Color._select)

    @staticmethod
    def good(s):
        return color(str(s), Color._good)

    @staticmethod
    def warning(s):
        return color(str(s), Color._warning)

    yN = color('yN', _select)


DECOLOR = re.compile(r'\033\[[^m]*m')


def len_color_str(s):
    return len(DECOLOR.sub('', str(s)))


def money_str(money):
    bal_color = "CYAN"
    if money < 0:
            bal_color = "RED"
    return color('$%.2f' % (money,), bal_color)


def read(prompt, callback=None, preload=None, history=None, complete=None):
    #stash_and_switch_history(history)
    #try:
        if complete is not None:
            completer = CompleteAdapter(complete)
            readline.set_completer(completer)
        elif callback is not None:
            completer = CompleteAdapter(
                lambda text: (
                    i for i in callback() if i.startswith(text.upper())))
            readline.set_completer(completer)
        else:
            completer = None
        while True:
            if preload is not None:
                def setup():
                    readline.insert_text(preload)
                    readline.redisplay()
                    readline.set_pre_input_hook(None)
                readline.set_pre_input_hook(setup)
            result = input(prompt)
            if not result or result[0] != '!':
                break
            command = result[1:].strip()
            if not command:
                command = '$SHELL -i'
            os.system(command)

        readline.set_completer(None)
        if completer and completer.errlog:
            print(completer.errlog)
        return result
    #finally:
        #unstash_and_unswitch_history()


def reqarg(s):
    if(len(s.strip()) > 0):
        return True
    else:
        print("Input cannot be blank")
        return False


def readvalidate(
        prompt, callback=None, preload=None, history=None, complete=None,
        validate=reqarg
        ):
    while True:
        results = read(
            prompt, callback=callback, preload=preload,
            history=history, complete=complete,
            )
        if validate(results):
            return results


def readlines(prompt):
    lines = []

    print(prompt)

    try:
        while True:
            s = read('')
            if s == '.':
                return lines
            lines.append(s)
    except KeyboardInterrupt:
        return None


def readnumber(prompt, start, end, history=None, escape=None):
    while True:
        s = read(
            prompt,
            lambda: (str(i) for i in range(start, end)),
            history=history)
        if not s:
            return None
        try:
            n = int(s)
            if not start <= n < end:
                print("You must enter a number in the specified range.")
                continue
            return n
        except ValueError:
            if escape and s.upper() == escape:
                return None
            print("You must enter a number")
            continue


def readbarcode():
    while True:
        prompt = "Scan Barcode: "
        in_barcode = read(prompt, history="barcode").strip()
        if not in_barcode:
            return None
        if validate_barcode(in_barcode):
            return in_barcode
        else:
            print("Invalid Barcode")


def readmoney(
        amount=None,
        prompt='Amount: ',
        prompt2='Charge %s to member? [' + Color.yN + '] ',
        history='money',
        ):
    if amount is not None and readyes(prompt2 % (money_str(amount),)):
        return amount
    while True:
        n = read(prompt, history=history)
        try:
            n = decimal.Decimal(n)
        except decimal.InvalidOperation:
            print("You must enter a number")
            continue
        return n


def readdate(date, ret=True):
    strdate = date.strftime("%Y-%m-%d")
    if readyes('Is ' + strdate + ' correct? [' + Color.yN + '] '):
        if ret:
            return date
        else:
            return None
    else:
        while True:
            d = read('Enter a date (YY-MM-DD): ')
            try:
                return dateutil.parser.parse(
                    d, ignoretz=True, default=date, yearfirst=True)
            except ValueError:
                print("Bad date format, try again")
                continue


def reademail(prompt):
    def val(email):
        ok = re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip())
        if not ok:
            print("Not a valid email address")
        return ok
    return readvalidate(prompt, validate=val).strip()


def readinitials(prompt):
    def val(email):
        ok = re.match(r"^[A-Z]{2,4}$", email.strip())
        if not ok:
            print("Not valid initials (2-4 all caps)")
        return ok
    return readvalidate(prompt, validate=val).strip()


def readphone(prompt):
    def val(phone):
        ok = re.match(r"^[- \d\(\)]+$", phone.strip())
        if not ok:
            print("Not a valid phone number")
        return ok
    return readvalidate(prompt, validate=val).strip()


def readaddress():
    new = readlines('New address (End with a dot on a line by itself):')
    return new


def maxresults():
    return termheight() - 1


def specify(dex, preload=None, predicate=None):
    if preload is None:
        author_preload, title_preload = '', ''
    else:
        author_preload = preload.authortxt
        title_preload = preload.titletxt
    while True:
        if predicate is None:
            itf = dex.indices.authors.iterkeys
        else:
            def itf():
                return (
                    i for i in dex.indices['authors'].keys()
                    if any((
                        predicate(j)
                        for j in dex.indices['authors'][i])))
        author = read(
            'Author: ',
            itf,
            author_preload, 'authors').upper().strip()
        if len(author.split('<')) == 4 and author in dex:
            return dex[author]
        if author:
            if hasattr(dex.indices.titles, 'search'):
                def itf():
                    return dex.indices.titles.search(author)
            else:
                def itf():
                    return (
                        i for i in dex.indices.titles.keys()
                        if any(
                            (author in j.authortxt)
                            for j in dex.indices.titles[i]))
        else:
            itf = list(dex.indices.titles.iterkeys())
        if predicate is not None:
            xitf = itf

            def itf():
                return (
                    i for i in xitf()
                    if any((
                        predicate(j)
                        for j in dex.indices['titles'][i])))

        title = read('Title: ', itf, title_preload, 'titles').upper()
        title = re.sub(r'^(?:A|AN|THE) ', '', title)
        author_preload, title_preload = '', ''

        if not author and not title:
            return None

        if hasattr(dex, 'search'):
            possibles = list(dex.search(author, title))
        else:
            possibles = [
                ((i.authortxt, i.titletxt), i)
                for i in dex.titlesearch(title)
                if author in i.authortxt]
            possibles.sort()
            possibles = [v for (k, v) in possibles]
        if predicate is not None:
            possibles = [book for book in possibles if predicate(book)]

        n = None
        if len(possibles) == 0:
            print("Nothing found, try again")
        elif len(possibles) == 1:
            n = 1
        elif len(possibles) < maxresults():
            for i, name in zip(range(1, len(possibles) + 1), possibles):
                print(Color.select(str(i) + '.'), name)
            n = readnumber('? ', 0, len(possibles) + 1, 'select')
        else:
            print("Too many options (%d), try again" % len(possibles))
        if n == 0:
            return None
        if n is None:
            author_preload, title_preload = author, title
            continue

        book = possibles[n - 1]
        return book


def specify_book(
        dex, preload=None, authorcomplete=None, titlecomplete=None,
        title_predicate=None, book_predicate=lambda book: True
        ):
    if preload is None:
        author_preload, title_preload = '', ''
    else:
        author_preload = preload.authortxt
        title_preload = preload.titletxt

    while True:
        if authorcomplete is None:
            complete = dex.indices.authors.complete
        else:
            complete = authorcomplete
        print('To return, type Control-C or leave author and title blank')
        author = read(
            'Author or Barcode: ',
            preload=author_preload,
            history='authors',
            complete=complete,
            ).upper().strip()
        maybe = dex.barcode(author)
        if maybe:
            return maybe
        book = None
        if (len(author.split('<')) in (4, 5) and
                '<'.join(author.split('<')[:4]) in dex):
            book = dex[author]
        else:
            if titlecomplete:
                def complete(text):
                    return titlecomplete(text, author=author)
            else:
                def complete(text):
                    return dex.indices.titles.complete(text, author=author)
            title = read(
                'Title: ',
                preload=title_preload,
                history='titles',
                complete=complete,
                ).upper().strip()
            title = re.sub(r'^(?:A|AN|THE) ', '', title)
            author_preload, title_preload = '', ''

            if not author and not title:
                return None

            possibles = list(dex.search(author, title))
            if title_predicate is not None:
                possibles = [
                    book for book in possibles if title_predicate(book)]

            n = None
            if len(possibles) == 0:
                print("Nothing found, try again")
            elif len(possibles) == 1:
                n = 1
            elif len(possibles) < maxresults():
                for i, name in enumerate(possibles):
                    print(Color.select(str(i + 1) + '.'), name)
                n = readnumber('? ', 0, len(possibles) + 1, 'select')
            else:
                print("Too many options (%d), try again" % len(possibles))
            if n == 0:
                return None
            if n is None:
                author_preload, title_preload = author, title
                continue

            book = possibles[n - 1]

        books = [
            (x, list(y))
            for (x, y) in itertools.groupby(
                (i for i in book.books if book_predicate(i)),
                lambda x: (x.shelfcode, x.barcodes, x.outto))]

        n = None
        if len(books) == 0:
            print("Nothing found, Try again")
        else:
            print(book)
            for (i, ((shelfcode, barcodes, outto), booklist)) in \
                    enumerate(books):
                count = len(booklist)
                if outto:
                    outto = ' (out to ' + outto + ')'
                if count > 1:
                    s = (
                        Color.select(str(i + 1) + '.') +
                        '%2dx %s %s%s' % (
                            count, shelfcode, ', '.join(barcodes), outto))
                else:
                    s = (
                        Color.select(str(i + 1) + '.') +
                        '    %s %s%s' % (
                            shelfcode, ', '.join(barcodes), outto))
                print(s)
            n = readnumber('? ', 0, len(books) + 1, 'select')
        if n is None or n == 0:
            return None
        return books[n - 1][1][0]


def specify_member(membook, line=''):
    preload = ''
    while True:
        if line:
            possibles = membook.search(line)

            n = None
            if len(possibles) == 0:
                print("Nothing found, try again")
            elif len(possibles) == 1:
                return possibles[0]
            elif len(possibles) < maxresults():
                for i, name in enumerate(possibles):
                    print(Color.select(str(i + 1) + '.'), name)
                n = readnumber('? ', 0, len(possibles) + 1, 'select')
                if n == 0:
                    return None
                if n is not None:
                    return possibles[n - 1]
            else:
                print("Too many options (%d), try again" % len(possibles))

            preload = line

        line = read(
            'Member: ',
            preload=preload,
            history='members',
            complete=membook.complete_name,
            ).strip().upper()

        if not line:
            return None


_curses_setup = False
_curses_codes = {}


def _putcap(capname, default=''):
    def putcapper():
        global _curses_setup
        if not _curses_setup:
            curses.setupterm()

        if capname not in _curses_codes:
            _curses_codes[capname] = curses.tigetstr(capname)
            if _curses_codes[capname] is None:
                _curses_codes[capname] = default
        curses.putp(_curses_codes[capname])
    return putcapper


clear_screen = _putcap('clear', '\n')
smul = _putcap('smul')
rmul = _putcap('rmul')
sgr0 = _putcap('sgr0')
bold = _putcap('bold')


def menu(menu_in, line='', once=False, cleanup=None, title=None):
    def remenu(menu):
        newmenu = menu() if callable(menu) else menu
        menudict = dict(
            (letter, (action, description))
            for (letter, description, action) in newmenu)
        keys = [l for (l, d, a) in newmenu if d]
        return newmenu, menudict, keys
    menu, menudict, keys = remenu(menu_in)
    while True:
        try:
            line = line.strip()
            if line:
                c = line[0].upper()
                if c not in menudict:
                    print('That is not an option.')
                else:
                    choice = menudict[c]
                    if choice[0] is None:
                        return False
                    print()
                    print(choice[1])
                    choice[0](line[1:].strip())
                    if once:
                        break
            menu, menudict, keys = remenu(menu_in)
            print()
            if callable(title):
                title()
            elif title:
                print(title)

            for letter, description, action in menu:
                if not description:
                    continue

                if letter is not None:
                    print(Color.select(letter + '.'), description)
                else:
                    print(description)

            line = read(
                'selection: ', lambda: keys, history='menu')
        except KeyboardInterrupt:
            if once:
                break
            line = ''
            continue
        except EOFError:
            return False
        except Exception:
            handle_exception(
                locals().get('choice', (None, 'Unknown Context'))[1],
                sys.exc_info())
            if once:
                break
            line = ''
            continue
        finally:
            if cleanup:
                cleanup()
    return True


def readyes(prompt, history=None):
    line = read(prompt, history=history).lower().strip()
    return line and line[0] == 'y'


def banner(program, release):
    print('This is %s %s' % (program, release))
    motd()


def motd():
    from mitsfs.constants import LOCKER
    try:
        print(open(os.path.join(LOCKER, 'dexcode/motd')).read())
    except IOError:
        pass


def menuize_dict(d):
    return [(Color.select(k + '.'), d[k]) for k in sorted(d)]


def tabulate(t):
    t = list(t)  # consume a generator if relevant
    widths = []
    for i in t:
        for (j, l) in enumerate(len_color_str(str(k)) for k in i[:-1]):
            if len(widths) >= j:
                widths[len(widths):j] = [0] * (j + 1 - len(widths))
            if widths[j] < l:
                widths[j] = l

    def format(line, widths):
        s = ' '.join(
            '%*s' % (-width - len(str(s)) + len_color_str(str(s)), s)
            for (width, s) in zip(widths, line[:-1]))
        if line:
            if line[:-1]:
                s += ' '
            s += str(line[-1])
        return s

    return '\n'.join(format(line, widths) for line in t)


def termsize(x, evar, fallback):
    winsz = array.array('H', [0] * 4)  # four unsigned shorts per tty_ioctl(4)
    fcntl.ioctl(0, termios.TIOCGWINSZ, winsz, True)

    if winsz[x]:
        return winsz[x]

    try:
        width = int(os.environ.get(evar, '0'))
        if width:
            return width
    except ValueError:
        pass

    return fallback


def termwidth():
    return termsize(1, 'COLUMNS', 80)


def termheight():
    return termsize(0, 'ROWS', 24)


def lfill(l):
    width = termwidth()
    column = 0
    for word in l:
        if column and len(word) + column + 3 > width:
            column = 0
            print()
        print(word)
        column += len(word)
    print()


def pfill(s):
    lfill(s.split())


'''
class HISTORY_STATE(ctypes.Structure):
    _fields_ = [
            ('entries', ctypes.c_void_p),
            # HIST_ENTRY **entries; # Pointer to the entries themselves.
            ('offset', ctypes.c_int),
            # int offset;           # The location pointer within this array.
            ('length', ctypes.c_int),
            # int length;           # Number of elements within this array.
            ('size', ctypes.c_int),
            # int size;             # Number of slots allocated to this array.
            ('flags', ctypes.c_int),
            # int flags;
            ]

HISTORY_STATE_p = ctypes.POINTER(HISTORY_STATE)

readline.history_get_history_state.restype = HISTORY_STATE_p
readline.history_get_history_state.argtypes = []

readline.history_set_history_state.restype = ctypes.c_void_p
readline.history_set_history_state.argtypes = [HISTORY_STATE_p]

history_state = {}
history_saved = None
history_key = None


def stash_and_switch_history(key):
    global history_key, history_saved
    if history_key is None:
        history_saved = readline.history_get_history_state()
    else:
        if history_key != key:
            history_state[history_key] = (
                readline.history_get_history_state().contents)
    if key is not None:
        if key not in history_state:
            history_state[key] = HISTORY_STATE(None, 0, 0, 0, 0)
        readline.history_set_history_state(ctypes.byref(history_state[key]))
    else:
        readline.history_set_history_state(
            ctypes.pointer(HISTORY_STATE(None, 0, 0, 0, 0)))
    history_key = key


def unstash_and_unswitch_history():
    global history_key, history_saved
    if history_key is not None:
        history_state[history_key] = (
            readline.history_get_history_state().contents)
    history_key = None
    if history_saved is not None:
        readline.history_set_history_state(history_saved)
    history_saved = None
'''