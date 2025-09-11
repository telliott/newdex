#!/usr/bin/python

import sys
import os
import time
import re
import itertools
import smtplib

from mitsfs.library import Library
from mitsfs.ui import banner, menu, specify, specify_book, readinitials
from mitsfs.ui import specify_member, tabulate, read, readlines, readyes
from mitsfs.dexdb import DexDB, DataError
from mitsfs.constants import DEXBASE
from mitsfs.library import DATABASE_DSN
from mitsfs.dexfile import Dex, DexLine
from mitsfs.dex.members import star_dissociated, role_members, star_cttes
from mitsfs.dex.editions import InvalidShelfcode
from mitsfs.dex.editions import Editions, Edition
from mitsfs.circulation.checkouts import Checkouts

__release__ = '2'


if 'dex' in locals():
    del dex

dex = None
program = 'dexhamster'
review = False


def main(args):
    global dex, library

    try:
        import psyco
        psyco.full()
    except ImportError:
        pass

    dsn = None
    if len(args) > 2:
        print('usage: dexhamster [dsn]')
        return
    if len(args) == 2:
        dsn = args[1]

    banner(program, __release__)

    sys.stdout.write('Connecting to dex...')
    sys.stdout.flush()
    dex = DexDB(client='dexhamster', dsn=dsn or DATABASE_DSN)
    library = Library(dex)

    print('done. (%s)' % dex.filename)

    starmenu = [
        ('B', 'Back to Other Menu', None),
        ('?', 'Check for dissociated roles', checkdis),
        ('K', 'Key a member', key),
        ('D', 'De-key a member', dekey),
        ('W', 'Who are keyholders', keylist),
        ('C', 'List committees', cttelist),
        ('A', 'Add a keyholder to a committee', ctteadd),
        ('R', 'Remove a keyholder from a committee', ctteremove),
        ('Q', 'Quit', quithamster),
        ]

    othermenu = [
        ('B', 'Back to Main Menu', None),
        ('A', 'change codes in a shelfdex Arc', arc),
        ('C', 'check the dex consistency', dexck),
        ('O', 'edit bOok', book),
        ('T', 'edit Title', title),
        ('S', 'edit Series', series),
        ('W', 'Withdraw books', withdraw),
        ('M', 'Membership', membership),
        ('G', 'merGe user', merge),
        ('V', 'VGG list', vgg),
        ('*', '*-Chamber menu',
         lambda line: menu(starmenu, line)),
        ('Q', 'Quit', quithamster),
        ]

    mainmenu = [
        ('N', 'New Entry', newentry),
        ('C', 'Code Change/Add', editcodes),
        ('P', 'Put entry into series', lambda line: editfield('series', line)),
        ('T', 'Title Change', lambda line: editfield('titles', line)),
        ('A', 'Author Change', lambda line: editfield('authors', line)),
        ('R', 'Review mode toggle', reviewtoggle),
        ('G', 'Grep for pattern', grep),
        ('O', 'Other (The Dread Menu Miscellaneous)',
         lambda line: menu(othermenu, line)),
        ('F', 'File a bug', filebug),
        ('Q', 'Quit', quithamster),
        ]

    menu(mainmenu)


def reviewtoggle(line):
    global review
    review = not review
    print('Review mode is', review and 'ON' or 'OFF')


def editfield(field, line):
    pmap = {
        'authors': (
            'Author: ',
            [munge_author, munge_field],
            [validate_field]),
        'titles': (
            'Title: ',
            [munge_field],
            [validate_field, validate_title, validate_title_or_series]),
        'series': (
            'Series: ',
            [munge_field, munge_series],
            [validate_field, validate_series, validate_title_or_series]),
        }

    assert field in pmap

    book = specify(dex)
    if not book:
        return

    print('selected', book)

    prompt, munge, validate = pmap[field]
    value = readvalidate(
        prompt,
        dex.indices[field].iterkeys,
        preload=str(getattr(book, field)),
        munge=munge,
        validate=validate,
        history=field)
    if not value:
        return
    if value == '-':
        value = ''
    new = DexLine(book, **{field: value})
    print('now', new)
    dex.replace(book, new)


def convertcodes(codes):
    try:
        codes = Editions(codes)
    except InvalidShelfcode as e:
        print(e)
        return None
    return codes


def editcodes(line):
    if review:
        print('WARNING REVIEW MODE IS ON')

    codes = None
    while True:
        book = specify(dex)
        if not book:
            return

        print('selected', book)

        if line:
            codes = convertcodes(line)
            if not codes:
                line = ''
        if not codes:
            codes = readvalidate(
                'New codes: ',
                lambda: (
                    i + ':'
                    for i in itertools.chain(
                        list(dex.shelfcodes.keys()),
                        (i for i in book.codes if i not in dex.shelfcodes))),
                validate=[validate_shelfcodes],
                history='codes')
            codes = convertcodes(codes)
            if not codes:
                return
        if int(codes) > 0:  # check only if we are not rearranging deckchairs
            # the new state of things
            newcodes = book.codes + codes
            # only check the codes we're increasing
            basecodes = [c.code for c in codes if c.count > 0]
            hassleset = {dex.shelfcodes[c].hassle for c in basecodes}
            hassleset = {x for x in hassleset if x}
            # count up the books
            hassle = [
                (consider, keep, sum(newcodes[i] for i in consider))
                for (consider, keep) in hassleset]
            # check to see if any of them violate our constraints
            hassle = [
                (consider, keep, count)
                for (consider, keep, count) in hassle if count > keep]
            if hassle:
                print(codes, 'results in', newcodes, 'which seems like a lot')
                if not readyes('Are you sure you want to do that? '):
                    return
        changecodes(book, codes)
        if not line:
            return


def changecodes(book, codes):
    new_deprecated = {
        code: edition.count for (code, edition) in codes.items()
        if dex.shelfcodes[code].type == 'D' and edition.count > 0}

    if new_deprecated:
        print('Change would result in addition to deprecated codes')
        print(Editions(new_deprecated))
        if not readyes('Are you sure you want to do that? '):
            return

    oldcodes = book.codes
    both = oldcodes + codes
    lost = False

    negs = [(code, edition.count) for (code, edition) in both.items()
            if edition.count < 0]
    if negs:
        print('Change would result in', Editions(negs), '(%s)' % both)
        print('(not doing it)')
        return

    new = DexLine(book, codes=codes)
    if not both and readyes(
            'We will no longer have any copies, add to lostdex? '):
        lost = True
    dex.add(new, review, lost)
    print('now', dex[new])
    if review and int(codes) > 0:
        reviewdex_add(new)


def validate_field(field):
    cchars = False
    bchars = ''

    for c in field:
        if ord(c) < ord(' ') and not cchars:
            print('No control characters.  Tabs either.')
            cchars = True
        if c in '<>{}^\\':
            if c not in bchars:
                bchars += c
    if bchars:
        s = len(bchars) != 1 and 's' or ''
        print('Illegal character' + s + ':', bchars)
    return not cchars and not bchars


def validate_title_or_series(field):
    for c in field:
        if c in '[]':
            if not readyes('Do you really want those brackets? '):
                return False
            break
    if re.match(r'^(?:A|AN|THE) ', field):
        if not readyes('Do you really want to start with an article? '):
            return False
    return True


def validate_title(field):
    if len(field.split('=')) > 2:
        print('Only one placement title is allowed.')
        return False
    return True


def validate_series(field):
    # a series name should not itself start with "@"
    if field[:2] == '@@':
        print('May not have multiple leading @s.')
        return False
    if '|@' in field:
        print('May only be @ first series')
        return False
    # random @s in the name are allowed ("b@nking") but likely mistakes
    if '@' in field[1:]:
        if not readyes(
                "Do you really want an '@' as part of the series name? "):
            return False
    # better not have multiple #s, or any after |s
    if re.match(r'#.*#', field):
        print('Only one #, please')
        return False
    if re.match(r'\|.*#', field):
        print('#s only in the first series, please')
        return False
    # check they didn't put in a shelfcode by mistake
    if field:
        try:
            Editions(field)
            if not readyes(
                    'That looks like a shelfcode.  Did you mean that? '):
                return False
        except InvalidShelfcode:
            pass
    if '=' in field:
        if not readyes(
                "Do you really want an '=' as part of the series name? "):
            return False
    return True


def validate_shelfcodes(field):
    if not field.strip():
        return True
    try:
        Editions(field)
    except InvalidShelfcode as e:
        print(e)
        return False
    return bool(field.strip())


def munge_series(field):
    # no spaces in "#1,2,3" part
    while True:
        newfield = re.sub(r'( [0-9#,]+) (?=[0-9#,]*(\Z|\|))', r'\1', field)
        if newfield == field:
            break
        else:
            field = newfield
    return field


def munge_field(field):
    field = field.strip()
    field = re.sub(r'\s+', ' ', field)
    field = re.sub(r'\s([=|,])', r'\1', field)
    field = re.sub(r'([=|,])\s', r'\1', field)
    field = re.sub(r',(\S)', r', \1', field)
    return field


def munge_author(author):
    return re.sub(r'\.(?![ \.,|]|\Z)', '. ', author)


def readvalidate(
        prompt, callback=None, preload=None, munge=[munge_field],
        validate=[validate_field], history=None):

    if preload is None:
        result = ''
    else:
        result = preload

    while True:
        result = read(prompt, callback, result, history).upper().strip()

        if not result:
            return result  # blank always validates

        for munger in munge:
            result = munger(result)

        for validater in validate:
            if not validater(result):
                break  # ... so falls back around the while loop
        else:
            break  # actually breaks the while loop

    return result


def newentry(line):
    if line.strip().upper() == 'R':
        reviewthis = True
    else:
        reviewthis = review
    if reviewthis:
        print('WARNING REVIEW MODE IS ON')

    author = readvalidate(
        'Author: ',
        dex.indices.authors.iterkeys,
        munge=[munge_field, munge_author],
        history='authors')

    if not author:
        return

    title = readvalidate(
        'Title: ',
        dex.indices.titles.iterkeys,
        validate=[validate_field, validate_title, validate_title_or_series],
        history='titles')

    if not title:
        return

    tl = '<'.join([author, title, '', ''])

    if tl in dex:
        print()
        print("* That's not new!  We have", dex[tl].codes)
        print()
        return

    series = readvalidate(
        'Series: ',
        dex.indices.series.iterkeys,
        munge=[munge_field, munge_series],
        validate=[validate_field, validate_series, validate_title_or_series],
        history='series')

    code = readvalidate(
        'Code: ',
        dex.shelfcodes.keys,
        validate=[validate_shelfcodes],
        history='codes')

    line = DexLine('<'.join([author, title, series, code]))
    if line.codes:
        print('entering ', line)
        dex.add(line, reviewthis)
        newdex_add(line)

        if reviewthis:
            reviewdex_add(line)
    else:
        print('No codes, not entering', line)


def mon():
    return time.strftime('%b').lower()


def reviewdex_add(book):
    foodex_add('review-' + mon(), book, recycle=True)


def newdex_add(book):
    foodex_add('newdex-' + mon(), book, recycle=True)


def lostdex_add(book):
    foodex_add('lostdex', book, zerok=True)


def foodex_add(dexname, book, recycle=False, zerok=False):
    if not hasattr(dex, 'db'):
        filename = os.path.join(DEXBASE, dexname)

        if recycle:
            try:
                st = os.stat(filename)
                # file exists
                if (time.time() - st.st_mtime) > 40 * 86400:
                    # older than 40 days
                    os.unlink(filename)
            except OSError:
                # file does not exist; Proceed.
                pass

        foodex = Dex(filename, zerok=zerok)
        foodex.add(book)
        foodex.save(filename)


def filebug(line):
    smtpserver = 'localhost'
    to = 'libcomm-bugs@mit.edu'
    fro = '%s@mit.edu' % os.environ['USER']

    desc = read('Short description: ')
    print()
    body = readlines('Details: ')

    # assemble the e-mail message
    report = [
        'To: %s' % to,
        'From: %s' % fro,
        'Subject: %s' % desc,
        '',
        ]
    report.extend(body)
    report.append('')

    print()
    print('---BUG REPORT---')
    msg = "\n".join(report)
    print(msg)

    if readyes('Send this report? [yN] '):
        session = smtplib.SMTP(smtpserver)
        smtpresult = session.sendmail([fro], [to], msg)
        if smtpresult:
            errstr = ""
            for recip in smtpresult.keys():
                errstr = """Could not delivery mail to: %s

Server said: %s
%s

%s""" % (recip, smtpresult[recip][0], smtpresult[recip][1], errstr)
                raise smtplib.SMTPException(errstr)
        else:
            print('Report sent.')


def quithamster(line):
    exit()


def lessiter(iterator):
    pager = os.environ.get('PAGER', 'less')
    os.environ['LESS'] = '-eMX'
    try:
        out = os.popen(pager, 'w')
        for i in iterator:
            out.write(str(i) + "\n")
        out.close()
    except IOError:
        pass


def grep(pattern):
    if not pattern:
        pattern = read('pattern? ', history='grep')
    try:
        if pattern:
            while pattern[-1] == '\\':
                print('Removing presumably spurious trailing \\.')
                pattern = pattern[:-1]
            lessiter(dex.grep(pattern))
    except InvalidShelfcode as e:
        print('In shelfcode query:', e)
    except DataError as e:
        print('While querying', e)


def validate_shelfcode(code):
    if not code.strip():
        return True
    try:
        e = Edition(code)
        if e.series_visible:
            print('No @s')
            return False
    except InvalidShelfcode:
        return False
    return True


def arc(line):
    sourcecode = readvalidate(
        'Source code: ',
        # dex.indices.codes.iterkeys,
        dex.shelfcodes.keys,
        validate=[validate_shelfcode],
        history='codes').upper()
    if not sourcecode:
        return

    print('extracting shelfcode')

    books = list(DexLine(i) for i in dex.indices.codes[sourcecode])

    print('sorting extract...')
    sys.stdout.flush()
    try:
        books.sort(key=lambda v: v.sortkey())
    except KeyError as e:
        print(e)
        return
    print('done')

    mydex = Dex(books)

    def predicate(book):
        return sourcecode in book.codes

    print('First book')
    start = specify(mydex, books[0], predicate)
    if not start:
        return
    print('selected', start)

    print('Last book')
    finish = specify(mydex, books[-1], predicate)
    if not finish:
        return
    print('selected', finish)

    destcode = readvalidate(
        'Destination code: ',
        #codes.iterkeys,
        dex.shelfcodes.keys,
        validate=[validate_shelfcode],
        history='codes')
    if not destcode:
        return

    starti = books.index(DexLine(start))
    finishi = books.index(DexLine(finish))
    for i in books[starti:finishi + 1]:
        count = i.codes[sourcecode]
        changecodes(
            i, Editions({sourcecode: -count, destcode: count}))


def dexck(line):
    print("Not yet")


def membership(line):

    member = specify_member(library.members, line)

    if not member:
        return  # I don't think this can happen at this point, but....

    while True:
        fields = ['pseudo', 'role']
        kf = dict((f[0].upper(), f) for f in fields)
        t = []
        unfilled = False
        for f in fields:
            v = getattr(member, f)
            k = f[0].upper()
            if v is not None:
                t += [(k + '.', f.title(), '', str(v))]
            else:
                t += [(k + '.', f.title(), '*')]
                unfilled = True
        t += [()]

        keys = list(kf.keys())
        if not member.id:
            if not unfilled:
                t += [('C.', 'Create')]
            else:
                t += [('C.', 'Create', '*', '(there are unfilled fields)')]
            keys.append('C')
        else:
            t += [
                (' created %s by %s with %s' % (
                    member.created, member.created_by, member.created_with),),
                ('modified %s by %s with %s' % (
                    member.modified, member.modified_by,
                    member.modified_with),),
                ()]
        t += [('X.', 'eXit')]
        keys.append('X')

        print()
        if member.new:
            print('Editing new member', member.name or '')
        else:
            print('Editing member', member.name)
        print()
        print(tabulate(t))
        what = read(
            'action: ', lambda: keys, history='menu').upper().strip()
        if not what:
            continue
        if what == 'X':
            if member.new and not readyes(
                    'Are you sure you want to exit without saving? '):
                continue
            break
        elif member.new and what == 'C':
            if unfilled:
                print('Please fill out the field marked with a *')
            else:
                member.create()
                print('Created.')
        elif what in kf:
            f = kf[what]
            try:
                val = read(
                    f.title() + '? ',
                    preload=getattr(member, f) or '',
                    history='memberfield')
            except KeyboardInterrupt:
                continue
            if val:
                setattr(member, f, val)
                member.cache_reset()
        else:
            print('Unknown option', what)


def series(line):
    series = None
    while series is None:
        name = read(
            'Series Name? ',
            preload=line,
            complete=dex.indices.series.complete).strip()
        if not name:
            return

        series = dex.series(name)
        if not series:
            print('No such series.')

    while True:
        fields = ['name', 'comment']
        kf = dict((f[0].upper(), f) for f in fields)
        t = []
        for f in fields:
            v = getattr(series, f)
            k = f[0].upper()
            if v is not None:
                t += [(k + '.', f.title(), '', v)]
            else:
                t += [(k + '.', f.title(), '*')]
        t += [()]

        keys = list(kf.keys())
        t += [
            (' created %s by %s with %s' % (
                series.created, series.created_by, series.created_with),),
            ('modified %s by %s with %s' % (
                series.modified, series.modified_by, series.modified_with),),
            (),
            ]

        count = len(series)

        if count:
            if count == 1:
                counts = ''
            else:
                counts = 's'
            t += [('L.', 'List series (%d title%s)' % (count, counts))]
            keys.append('L')
        else:
            t += [('', 'No titles in series')]

        t += [(),
              ('X.', 'eXit')]
        keys.append('X')

        print()
        print('Editing series', series.name)
        print()
        print(tabulate(t))
        what = read(
            'action: ',
            lambda: keys,
            history='menu').upper().strip()
        if not what:
            continue
        if what == 'X':
            break
        elif len(series) and what == 'L':
            lessiter(series)
        elif what in kf:
            f = kf[what]
            try:
                val = read(
                    f.title() + '? ',
                    preload=getattr(series, f) or '',
                    history='seriesfield')
            except KeyboardInterrupt:
                continue
            if val:
                setattr(series, f, val)
        else:
            print('Unknown option', what)


def book(line):
    book = specify_book(dex)
    if book is None:
        return

    while True:
        fields = [
            'title', 'shelfcode', 'visible', 'doublecrap',
            'review', 'withdrawn', 'comment',
            ]
        kf = dict((f[0].upper(), f) for f in fields)
        t = []
        for f in fields:
            v = getattr(book, f)
            k = f[0].upper()
            if v is not None:
                t += [(k + '.', f.title(), '', str(v))]
            else:
                t += [(k + '.', f.title(), '*')]
        t += [()]

        keys = list(kf.keys())
        t += [
            (' created %s by %s with %s' % (
                book.created, book.created_by, book.created_with),),
            ('modified %s by %s with %s' % (
                book.modified, book.modified_by, book.modified_with),),
            (),
            ]

        t += [
            (),
            ('X.', 'eXit')]
        keys.append('X')

        print()
        print('Editing book', book)
        print()
        print(tabulate(t))
        what = read(
            'action: ',
            lambda: keys,
            history='menu').upper().strip()
        if not what:
            continue
        if what == 'X':
            break
        elif what in kf:
            f = kf[what]
            try:
                if f == 'title':
                    val = specify(dex, book.title)
                else:
                    val = read(
                        f.title() + '? ',
                        preload=getattr(book, f) or '',
                        history='bookfield')
            except KeyboardInterrupt:
                continue
            if val:
                setattr(book, f, val)
        else:
            print('Unknown option', what)


def withdraw(line):
    while True:
        print()
        print('Book to withdraw ->')
        book = specify_book(dex)
        if not book:
            break
        if book.withdrawn:
            print(book, 'is already withdrawn')
            continue
        book.withdrawn = True
        print(book, ': withdrawn')


def title(line):
    title = specify(dex)
    if title is None:
        return

    while True:
        fields = ['lang', 'lost', 'comment']
        kf = dict((f[0].upper(), f) for f in fields)
        t = []
        for f in fields:
            v = getattr(title, f)
            k = f[0].upper()
            if v is not None:
                t += [(k + '.', f.title(), '', str(v))]
            else:
                t += [(k + '.', f.title(), '*')]
        t += [()]

        keys = list(kf.keys())
        t += [
            (' created %s by %s with %s' % (
                title.created, title.created_by, title.created_with),),
            ('modified %s by %s with %s' % (
                title.modified, title.modified_by, title.modified_with),),
            (),
            ]

        t += [(),
              ('X.', 'eXit')]
        keys.append('X')

        print()
        print('Editing title', title)
        print()
        print(tabulate(t))
        what = read(
            'action: ',
            lambda: keys,
            history='menu').upper().strip()
        if not what:
            continue
        if what == 'X':
            break
        elif what in kf:
            f = kf[what]
            try:
                val = read(
                    f.title() + '? ',
                    preload=getattr(title, f) or '',
                    history='titlefield')
            except KeyboardInterrupt:
                continue
            if val:
                setattr(title, f, val)
        else:
            print('Unknown option', what)


# Should really move all this stuff to icirc or some more privileged script
def checkdis(line):
    print('Dissociated roles (key them or get the speaker-to-postgres to ')
    print('remove them)')
    print(' '.join(star_dissociated(dex)))

def key(line):
    mem = specify_member(library.members, line)

    if not mem:
        return
    print('Keying', mem.name)
    role = None
    if mem.role:
        role = mem.role
    elif mem.email.lower().endswith('@mit.edu'):
        role = mem.email.split('@')[0].lower()
    
    role = read('Kerberos name? ', preload=role)
    if not role:
        return
    while True: 
        inits = readinitials("Keyholder initials? ").strip()
        if mem.check_initials_ok(inits):
            mem.key(role, inits)
            return
        else:
            print("Those initials have already been taken. Please try again.")
 

def specify_keyholder(dex, line):
    m = specify_member(library.members, line)
    key_ids = set(mem.id for mem in role_members(dex, 'keyholders'))
    while True:
        mem = specify_member(m, line)  # XXX constrain to keyholders
        if mem is None:
            return None
        if mem.id in key_ids:
            return mem
        print(mem, 'does not appear to be a keyholder.')


def dekey(line):
    mem = specify_keyholder(dex, line)
    if mem is None:
        return
    print('Dekeying', mem.name)
    if not readyes('Are you sure? '):
        return
    cttes = mem.committees
    mem.dekey()
    if cttes:
        print('Was on', ' '.join(cttes))


def maybeprettylist(x):
    if not x:
        return ''
    return '(%s)' % ', '.join(x)


def keylist(line):
    print()
    for key in role_members(dex, 'keyholders'):
        print(key.name, maybeprettylist(key.committees))
    print()


def cttelist(line):
    print()
    for ctte in star_cttes(dex):
        print(ctte, maybeprettylist(
            str(mem.name) for mem in role_members(dex, ctte)))
    print()


def ctteadd(line):
    print('Adding...')
    mem = specify_keyholder(dex, line)
    if mem is None:
        return
    ctte = read(
        'Committee? ',
        callback=lambda: star_cttes(dex) + ['*chamber'],
        ).lower().strip()
    if not ctte:
        return
    mem.grant(ctte)
    print(mem.name, maybeprettylist(mem.committees))
    print(ctte, maybeprettylist(
        str(m.name) for m in role_members(dex, ctte)))


def ctteremove(line):
    print('Removing...')
    mem = specify_keyholder(dex, line)
    if mem is None:
        return
    ctte = read(
        'Committee? ',
        callback=lambda: mem.committees,
        ).lower().strip()
    if not ctte:
        return
    mem.revoke(ctte)
    print(mem.name, maybeprettylist(mem.committees))
    print(ctte, maybeprettylist(
        str(m.name) for m in role_members(dex, ctte)))


def merge(line):
    print('This can only be expected to work by a speaker-to-postgres')
    print()
    print('User entry that is going away')
    other = specify_member(library.members, line)
    if other is None:
        return
    print('User that is sticking around')
    while True:
        mem = specify_member(library.members, line)
        if mem is None:
            return
        if mem.id != other.id:
            break
        print('Merge target must differ from merge subject')
    mem.merge(other)


def vgg(line):
    checkouts = Checkouts()
    for email, name, overdue in checkouts.vgg():
        print(name, '<' + email + '>')
        for stamp, code, title in overdue:
            print('', stamp, code, title)


if __name__ == '__main__':
    main(sys.argv)
