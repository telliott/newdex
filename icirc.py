#!/usr/bin/python3

import sys
import optparse
import datetime

from mitsfs.dexdb import DexDB, CirculationException
from mitsfs.ui import Color, banner, menu, tabulate, money_str, \
                read, readmoney, readaddress, readdate, readbarcode, \
                readvalidate, readnumber, readyes, reademail, readphone, \
                readinitials, specify, specify_book, specify_member, \
                len_color_str, bold, smul, sgr0, termwidth

from mitsfs.circulation.members import Member
from mitsfs.circulation.transactions import get_transactions, \
    Transaction, CashTransaction
from mitsfs import library
from mitsfs.core import settings

__release__ = '1.1'

program = 'greendex'


if 'dex' in locals():
    del dex
dex = None


parser = optparse.OptionParser(
    usage='usage: %prog [options]',
    version='%prog ' + __release__)

member = None


def main(args):
    global dex, member, library

    try:
        dex = DexDB(client=program)
    except Exception as e:
        # The traceback is unlikely to be nearly so useful as the error
        # message, and will cause people to miss the meat of the error message
        print(str(e))
        exit(1)

    # eventually Library will replace DexDB, but not there yet
    library = library.Library(dsn=dex.dsn)

    options, args = parser.parse_args(args)

    if len(args) != 1:
        banner(program, __release__)
        parser.print_usage()
        sys.exit(1)

    banner(program, __release__)

    if dex.dsn != settings.DATABASE_DSN:
        print('(' + dex.dsn + ')')

    def local_banner():
        if member is None:
            print('Main Menu')
            print()
        else:
            lm = len_color_str(member)
            ls = len_color_str(member.membership)
            ll = min(termwidth(), 80) - 1
            print('%s %*s%s' % (
                member,
                ll - lm - ls - 13, '',
                'Membership: ' + str(member.membership)))
            checkouts = member.checkouts.out
            if checkouts:
                if not member.pseudo:
                    print_checkouts(checkouts)
                else:
                    print()
                    if len(checkouts) == 1:
                        print('A book checked out.')
                    else:
                        print(len(checkouts), 'books checked out.',)
                    print('(B to display)')
                    print()
            dex.db.rollback()

    def advanced():
        return [
            ('B', 'Book Drop Check In',
                lambda line: checkin(line, bookdrop=True)),
            ('I', 'Fancy Check In',
                lambda line: checkin(line, advanced=True)),
            ('Q', 'Main Menu', None),
            ] if member is None else [
            ('B', 'Book Drop Check In',
                lambda line: checkin_member(line, bookdrop=True)),
            ('I', 'Fancy Check In',
                lambda line: checkin_member(line, advanced=True)),
            ('O', 'Fancy Check Out',
                lambda line: checkout(line, advanced=True)),
            ('Q', 'Main Menu', None),
            ]

    member_menu = [
        ('O', 'Check Out Books by Book', checkout),
        ('I', 'Check In Books by Patron', checkin_member),
        ('L', 'Declare Books Lost', lost),
        ('V', 'View Patron', viewmem),
        ('E', 'Edit Patron and Membership', editmem),
        ('P', 'Pay Outstanding Fines',
            lambda x: check_balance(member, print_notices=True)),
        ('F', 'Financial Transaction', financial),
        ('A', 'Advanced (Book Drop/Fancy Check In/Check Out)',
            lambda x: rmenu(advanced, x, title="Advanced")),
        ('S', 'Select Patron', select),
        ('Q', 'Unselect Patron', unselect),
        ]

    committee_member_menu = [
        ('B', 'Books checked out', print_member_checkouts)
        ] + member_menu

    nomember_menu = [
        ('S', 'Select Patron', select),
        ('I', 'Check In Books', checkin),
        ('N', 'New Patron', newmem),
        ('D', 'Display Book', display),
        ('A', 'Book Drop/Fancy Check In',
            lambda line: rmenu(
                advanced, line, title="Fancy/Book Drop Check In:")),
        ('Q', 'Quit', None),
        ]

    nomember_keys = set(x[0] for x in nomember_menu)
    nomember_menu += [
        (x[0], '', please) for x in member_menu if x[0] not in nomember_keys]

    def menu():
        if member:
            if member.pseudo:
                return committee_member_menu
            else:
                return member_menu
        return nomember_menu

    rmenu(menu, title=local_banner)


def please(line):
    print("Please select a member first")
    print()


def select(line):
    global member

    line = line.strip()

    if line:
        possibles = library.members.find(line)
        if len(possibles) == 1:
            member = possibles[0]
            return
    member = specify_member(library.members, line)


def unselect(line):
    global member
    member = None


def checkin(line, advanced=False, bookdrop=False):
    global member

    while True:
        book = specify_book(
            dex,
            authorcomplete=dex.indices.authors.complete_checkedout,
            titlecomplete=dex.indices.titles.complete_checkedout,
            title_predicate=lambda title: title.checkedout,
            book_predicate=lambda book: book.out)

        if not book:
            break

        # TODO: it is pretty messed up that we have both book checkouts and
        # member checkouts. Need to clean this up
        checkouts = book.checkouts
        if len(checkouts.out) > 1:
            print('Warning: %s is checked out more than once' % (book,))
        for checkout in checkouts.out:
            member = checkin_internal(checkout, advanced, bookdrop)


def checkin_member(line, advanced=False, bookdrop=False):
    while True:
        if not member.checkouts.out:
            print('No books are checked out.')
            break

        checkout = select_checkedout('Select book to check in: ')

        print()

        if checkout is None:
            return

        checkin_internal(checkout, advanced, bookdrop)


def checkin_internal(checkout, advanced, bookdrop):
    checkin_date = None
    if advanced or bookdrop:
        print("Specify check in date:")
        checkin_date = readdate(datetime.datetime.today(), False)

    print('Checking in: ')

    try:
        print(checkout)
        print(checkout.checkin(checkin_date))
    except CirculationException as exc:
        print(exc)
        print('Book NOT checked in.')
    print()
    return Member(dex, checkout.member_id)


def lost(line):
    if not member.checkouts.out:
        print('No books are checked out.')
        return

    while True:
        if not member.checkouts.out:
            break

        checkout = select_checkedout('Select book to declare as lost: ')
        print()

        if checkout is None:
            return

        if checkout.lost:
            print('That book is already lost.  To unlose it, check it in.')
            continue

        print(checkout.lose())


def select_checkedout(prompt):
    print_checkouts(checkouts=member.checkouts.out, enum=True)
    print(Color.select('Q.'), 'Back to Main Menu')
    print()

    num = readnumber(
        prompt,
        1,
        len(member.checkouts.out) + 1,
        escape='Q')

    if num is None:
        return None

    return member.checkouts.out[num - 1]


def checkout(line, advanced=False):
    # move this logic to the library
    # if not member.pseudo:
    #    check_balance(member)

    while True:
        ok, msgs, correct = member.can_checkout(advanced)

        if not ok:
            if advanced:
                print('\n'.join('WARNING: ' + msg for msg in msgs))
            else:
                print('\n'.join(msgs))
                print()
                print(correct + ' or use Fancy Check Out.')
                return

        # Only Circulating books on non fancy checkoout
        if advanced or member.pseudo:
            def title_predicate(title):
                return any(book for book in title.books if not book.out)

            def book_predicate(book):
                return not book.out
        else:
            def title_predicate(title):
                return any(
                    book for book in title.books
                    if (not book.out and book.circulating))

            def book_predicate(book):
                return not book.out and book.circulating

        print("Check out books for member", str(member))
        print()
        book = specify_book(
            dex,  # predicate for not in select book_id in checkout
                  #  where checkin_stamp is not null
                  # is too much cpu for not enough benefit
            title_predicate=title_predicate,
            book_predicate=book_predicate,
            )

        if not book:
            break

        if book.out:
            print(book)
            print('is already checked out to', book.outto)
            return

        checkout_date = None
        if advanced:
            print("Specify check out date:")
            checkout_date = readdate(datetime.datetime.today(), False)

        checkout = book.checkout(member, checkout_date)
        print('Checking out:')
        print(checkout)


def barcodebook(book):
    if len(book.barcodes) == 0:
        print()
        print("Book has no barcode.  Please attach and scan new barcode.")
        while True:
            barcode = readbarcode()
            if barcode is None:
                break
            if book.addbarcode(barcode):
                if len(book.barcodes) > 1:
                    print("""
WARNING: book has acquired two barcodes when it had zero
moments ago; please look to your left or right and see if
someone is checking out a similar book and role-play
accordingly; otherwise please let libcomm know that they
need to go meditate on the database logs.""")
                break
            print("Error adding barcode; perhaps it is already in use.")


def viewmem(line):
    def fin(line):
        print('Transactions of ', member)
        print(tabulate(
            [('Amount', 'Keyholder', 'Date', 'Type', 'Description')] +
            [(money_str(t.amount), t.created_by, t.created.date(),
                t.type_description, t.description)
                for t in member.transactions]))

    def history(line):
        print("History of: ", str(member))
        print_checkouts(checkouts=member.checkouts)

    def mem(line):
        print("History of: ", str(member))
        print(tabulate(
            [("Membership History", "Keyholder", "Bought")] +
            [(str(m), str(m.created_by), str(m.created.date()))
             for m in member.membership_history]))

    print()
    print(member.info())

    rmenu([
        ('C', 'Check Out History', history),
        ('F', 'Financial History', fin),
        ('M', 'Membership History', mem),
        ('Q', 'Main Menu', None),
        ], title="View User/Patron:")


def membership(line):
    def validate(line):
        line = line.strip().upper()
        if line in library.membership_types:
            return True
        return False

        # if (len(line) == 1 and
        #         0 <= (ord(line) - ord('a')) < len(library.membership_types)):
        #     return True
        # print('Input must be a letter between a and', \
        #     chr(ord('a') + len(library.membership_types) - 1))
        # return False

    print("Select membership type:")

    print(tabulate([Color.select(key) + '.',
                    library.membership_types[key].description,
                    '$%.2f' % library.membership_types[key].cost]
                   for key in library.membership_types.keys()))

    # print(tabulate(
    #     [Color.select(chr(ord('a') + n) + '.'), d, '$%.2f' % c]
    #     for (n, (t, d, c)) in enumerate(
    #             [(m.code, m.description, m.cost) for m in
    #              sorted(library.membership_types.values(),
    #                     key=lambda d: d.cost)]
    #             )))

    member_type_char = readvalidate(
        'Select Membership Type: ', validate=validate).upper()
    member_type = library.membership_types[member_type_char]

    expiration = member.membership_addition_expiration(member_type)

    calc_cost = member_type.cost
    if member.membership and member_type.duration is None \
            and not member.membership.expired:
        calc_cost -= member.membership.cost

    msg = '%s membership would cost $%.2f' % (member_type.description,
                                              -calc_cost)
    if expiration:
        msg += f" and expire on {expiration.strftime('%Y-%m-%d')}."
    else:
        msg += '.'
    print(msg)
    if readyes('Continue? [' + Color.yN + '] '):
        member.membership_add(member_type)
        check_balance(member, 'Membership Payment')


def editmem(line):
    if member.pseudo:
        print("WARNING editing pseudo account: %s is disallowed." % (member,))
        print("Email libcomm@mit.edu if you need to modify information")
        print("in a pseudo user account.")
        return

    def edit_name(line):
        print(f'Current:\n\t First Name: {member.first_name}, '
              f'Last Name: {member.last_name}')
        first = read("New First Name (blank to retain): ").strip()
        last = read("New Last Name (blank to retain): ").strip()

        if first:
            member.first_name = first
        if last:
            member.last_name = last

    def edit_email(line):
        print(f'Current: {member.email}')
        email = reademail("New Email: ").strip()

        if email:
            member.email = email

    def edit_address(line):
        print(f'Current: {member.address}')
        address = readaddress()
        if address:
            member.address = address

    def edit_phone(line):
        print(f'Current: {member.phone}')
        phone = readphone('New Phone: ').strip()

        if phone:
            member.phone = phone

    # TODO: Move this to a protected area and expose as part of keying
    def edit_initials(line):
        print(f'Current: {member.key_initials}')
        inits = readinitials().strip()

        if inits:
            member.key_initials = inits

    def remove(_, title, info):
        if len(info) == 0:
            print("No non-default", title, "to remove")
            return
        print("Remove a non-default", title + ":")
        table = []
        for n, x in enumerate(info):
            lines = str(x).split("\n")
            table += [(Color.select('%d.' % (n + 1,)), lines[0])]
            table += [('', line) for line in lines[1:]]
        table += [(Color.select('Q.'), 'Back to Remove Menu')]
        print(tabulate(table))
        print()

        delete = readnumber(
            'Select %s to delete: ' % (title,), 0, len(info) + 1, escape='Q')

        if delete is None:
            print('Nothing removed.')
            return
        else:
            info[delete - 1].delete()

    def edit_member(line):
        rmenu([
            ('N', 'Change Name', edit_name),
            ('E', 'Change Email', edit_email),
            ('A', 'Change Address', edit_address),
            ('P', 'Change Phone', edit_phone),
            ('Q', 'Back to Edit Membership', None)
            ], title='Change Member Information')

    print()
    print(member.info())
    rmenu([
        ('M', 'New/Renew Membership', membership),
        ('E', 'Edit Member', edit_member),
        ('Q', 'Main Menu', None),
        ], title='Membership')


def newmem(line):
    print("Please transfer the patron's information from the sheet.")

    first = readvalidate("First Name: ").strip()
    last = readvalidate("Last Name: ").strip()

    # TODO: better search function here
    names = library.members.search(first+last)
    if len(names) > 0:
        print("The following people are already in greendex:")
        for n in names:
            print("    " + str(n))
        print('Are your sure you want to continue, instead of editing a')
        print('membership in the edit menu?')
        if not readyes('Continue? [' + Color.yN + '] '):
            return
    email = reademail("Email (required): ")
    phone = readphone("Phone number: ")
    print()
    print("Postal address that will work long-term:")
    print()

    address = readaddress()

    if not readyes('Add this member? [' + Color.yN + '] '):
        return

    newmember = Member(dex)
    newmember.first_name = first
    newmember.last_name = last
    newmember.email = email
    newmember.phone = phone
    newmember.address = address
    newmember.create(commit=True)

    global member
    member = Member(dex, newmember.id)

    print()
    print('Member added.')
    print()

    if readyes(
            'Add a membership to new member? [' + Color.yN + '] '):
        membership(None)


def financial(line):

    def financial_header():
        print()
        print('Transaction for', member)
        print()

    def donation(line):
        financial_header()
        print('Enter amount of donation, this will increase'
              'the patron\'s balance.')
        amount = readmoney().copy_abs()
        desc = read('Enter description: ', history='description')
        print('Adding %s to account of %s.' % (money_str(amount), member))
        if not readyes(
                'Commit the transaction? [' + Color.yN + '] '):
            return
        tx = Transaction(dex, member.id, amount=amount,
                         transaction_type='D', description=desc)
        tx.create()

    def assess_fine(line, tx_type='F'):
        financial_header()
        print('Enter the fine amount, this will decrease '
              'the patron\'s balance.')
        amount = -readmoney().copy_abs()
        desc = read('Enter description: ', history='description')

        print(f'Adding {money_str(amount)} to account of {member}.')
        if not readyes(
                'Commit the transaction? [' + Color.yN + '] '):
            return
        tx = Transaction(dex, member.id, amount=amount,
                         transaction_type=tx_type, description=desc)
        tx.create()

    def assess_keyfine(line):
        assess_fine(line, type='K')

    def payment(line):
        financial_header()
        print('Enter the amount being paid, this will increase'
              'the patron\'s balance.')
        amount = readmoney().copy_abs()
        desc = read('Enter description: ', history='description')

        print(f'Adding {money_str(amount)} to account of {member}.')
        print(f'Adding {money_str(amount)} to cash drawer')
        if not readyes(
                'Commit the transaction? [' + Color.yN + '] '):
            return
        cash_tx = CashTransaction(dex, member.id, member.normal_str,
                                  amount=amount, transaction_type='P',
                                  description=desc)
        cash_tx.create()

    def lhe_transaction(line):
        financial_header()
        print('Enter amount (negative for fines, positive for credit).')
        amount = readmoney()
        desc = read('Enter description: ', history='description')

        print('Adding %s to account of %s.' % (money_str(amount), member))
        if not readyes(
                'Commit the transaction? [' + Color.yN + '] '):
            return
        tx = Transaction(dex, member.id, amount=amount,
                         transaction_type='L', description=desc)
        tx.create()

    def pay_membership(line):
        financial_header()
        print('Warning, this does not update the patron\'s membership.'
              ' It is only used when the patron previously bought a'
              ' membership and is now paying. Use the Edit Member menu'
              ' to add a new membership; They can pay there.')
        print('Enter an amount; this will decrease the patron\'s balance.')
        amount = -readmoney().copy_abs()
        desc = read('Enter description: ', history='description')

        print('Adding %s to account of %s.' % (money_str(amount), member))
        if not readyes(
                'Commit the transaction? [' + Color.yN + '] '):
            return
        tx = Transaction(dex, member.id, amount=amount,
                         transaction_type='L', description=desc)
        tx.create()

    def reimbursement(line):
        financial_header()
        print('Enter the amount the patron is being reimbursed, this'
              ' will decrease the patron\'s balance.')
        amount = -readmoney().copy_abs()
        desc = read('Enter description: ', history='description')

        print(f'Adding {money_str(amount)} to account of {member}.')
        print(f'Adding {money_str(amount)} to cash drawer')
        if not readyes(
                'Commit the transaction? [' + Color.yN + '] '):
            return
        cash_tx = CashTransaction(dex, member.id, member.normal_str,
                                  amount=amount, transaction_type='R',
                                  description=desc)
        cash_tx.create()

    def void_transaction(line):
        financial_header()
        txns = get_transactions(dex, member.id, include_voided=False)

        if len(txns) == 0:
            print("No transactions to void.")
            return

        quit_item = (Color.select('Q.'), 'Back to Main Menu')

        print('Non-void Transactions of ', member)
        print(tabulate(
            [('#', 'Amount', 'Keyholder', 'Date', 'Type', 'Description')] +
            [(Color.select(str(i + 1) + '.'), money_str(tx.amount),
                tx.created_by, tx.created.date(),
                tx.type_description, tx.description)
                for (i, tx) in enumerate(txns)] +
            [quit_item]))

        num = readnumber(
            'Select transaction to void: ', 1, len(txns) + 1, escape='Q')

        if num is not None:
            print()
            voided = txns[num - 1].void()
            print("Voided transactions:")
            print(tabulate(
                [('Member', 'Amount', 'Keyholder', 'Date', 'Type',
                    'Description')] +
                [(Member(dex, tx.member_id).full_name, money_str(tx.amount),
                    tx.created_by, tx.created.date(),
                    tx.type_description, tx.description)
                    for tx in voided]))

    def advanced_financial(line):
        menu = [
            ('L', 'LHE', lhe_transaction),
            ('M', 'Pay Membership', pay_membership),
            ('R', 'Reimbursement', reimbursement),
            ('V', 'Void Previous', void_transaction),
            ('Q', 'Back to Financial Transactions', None)
            ]
        rmenu(menu, title="Advanced Financial Transactions")

    menu = [
        ('D', 'Donation for Fine Credit', donation),
        ('F', 'Assess Fine', assess_fine),
        ('K', 'Assess Keyfine', assess_keyfine),
        ('P', 'Payment', payment),
        ('A', 'Advanced Transactions', advanced_financial),
        ('Q', 'Back to Main Menu', None)
        ]
    rmenu(menu, title='Financial Transactions')

# def do_transaction(txntype):
#     print()
#     print('Transaction for', member)
#     print()

#     if txntype == 'V':
#         txns = get_transactions()
#         member.transactions(False)

#         if len(txns) == 0:
#             print("No transactions to void.")
#             return

#         quit_item = (Color.select('Q.'), 'Back to Main Menu')

#         print('Non-void Transactions of ', member)
#         print(tabulate(
#             [('#', 'Amount', 'Keyholder', 'Date', 'Type', 'Description')] +
#             [(Color.select(str(i + 1) + '.'), money_str(tx.amount),
#                 tx.created_by, tx.created.date(),
#                 tx.type_description, tx.description)
#                 for (i, tx) in enumerate(txns)] +
#             [quit_item]))

#         num = readnumber(
#             'Select transaction to void: ', 1, len(txns) + 1, escape='Q')

#         if num is not None:
#             print()
#             voided = txns[num - 1].void()
#             print("Voided transactions:")
#             print(tabulate(
#                 [('Member', 'Amount', 'Keyholder', 'Date', 'Type',
#                     'Description')] +
#                 [(Member(dex, tx.member_id).name, money_str(tx.amount),
#                     tx.created_by, tx.created.date(),
#                     tx.type_description, tx.desc)
#                     for tx in voided]))
#         return

#     if txntype in ['D', 'P']:
#         if txntype == 'D':
#             print('Enter amount of donation, this will increase')
#             print("the patron's balance.")
#         else:
#             print('Enter the amount being paid, this will increase')
#             print("the patron's balance.")
#         amount = readmoney().copy_abs()
#         print(amount)
#     elif txntype in ['K', 'F', 'R', 'M']:
#         if txntype in ['K', 'F']:
#             print('Enter the fine amount, this will decrease')
#             print("the patron's balance.")
#         elif txntype == 'M':
#             print("""Warning, this does not update the patron's membership.
# All this does is create a transaction with the type 'membership'.
# If you want to update a membership, go to 'Edit Member' and add
# a new membership; that will automatically create a new transaction.

# Enter an amount; this will decrease the patron's balance.""")
#         else:
#             print("""Enter the amount the patron is being reimbursed,
# this will decrease the patron's balance.""")
#         amount = -readmoney().copy_abs()
#     else:
#         print('Enter amount (negative for fines, positive for credit).')
#         amount = readmoney()

#     desc = read('Enter description: ', history='description')

#     print('Adding %s to account of %s.' % (money_str(amount), member))

#     if txntype in ['P', 'R']:
#         print('Adding %s to cash drawer' % (money_str(amount),))

#     if not readyes(
#             'Commit the transaction? [' + Color.yN + '] '):
#         return

#     if txntype not in ['P', 'R']:
#         tx = Transaction(dex, member.id, amount=amount,
#                          transaction_type=txntype, description=desc)
#         tx.create()
#     else:
#         cash_tx = CashTransaction(dex, member.id, member.normal_str,
#                                   amount=amount, transaction_type='D',
#                                   description=desc)
#         cash_tx.create()

        # cash_desc = "Cash transaction for %s: %s" % (member.normal_str, desc)
        # member.cash_transaction(amount, txntype, cash_desc)


def check_balance(member, desc="Payment", print_notices=False):
    if member.pseudo:
        if print_notices:
            print("Pseudo-member, can't change balances.")
        return True
    amount = -member.balance

    if amount > 0:
        print('Member', member, 'has a negative balance')
        if readyes('Pay balance? [' + Color.yN + '] '):
            amount = readmoney(
                amount,
                prompt2='Is member paying %s? [' + Color.yN + '] ',
                prompt='Amount they are paying: ')

            desc = desc + ' by ' + member.normal_str
            tx = CashTransaction(dex, member.member_id, member.normal_str,
                                 amount=amount, transaction_type='P',
                                 description=desc)
            tx.create()

    elif print_notices:
        print("Member doesn't have a negative balance")

    return member.balance >= 0


def display(line):
    title = specify(dex)
    if not title:
        return

    print(title)
    print()
    print('HOLDINGS - If book is checked out, the member it is checked out to')
    print('will be on the next line.')
    for book in title.books:
        print(book)
        if book.out:
            print('    ', book.outto)
    print()


def color_due_date(stamp):
    return (
        Color.good
        if datetime.datetime.now() < stamp
        else Color.warning)(stamp.date())


def print_member_checkouts(line):
    print_checkouts(sorted(member.checkouts.out,
                           key=lambda x: x.title.sortkey()))


def print_checkouts(checkouts, enum=False):
    ll = min(termwidth(), 80) - 1
    offset = ''
    if enum:
        # We're assuming here that this is for the checkin-by-member function.
        # Normal users shouldn't have more than eight books out.  Abnormal
        # users can deal with a little bit of ugly.
        offset = '   '
        ll -= 3
    bold()
    print(offset + 'Author ' + ' ' * (ll - 12) + 'Title')
    smul()
    print(
        offset + ' ' * (ll - 43) + 'Code' + (3 * ' ') + 'Check Out' +
        (9 * ' ') + 'Check In/Due' + (6 * ' '))
    sgr0()
    lookup_member = None

    for n, c in enumerate(list(checkouts)):
        title = c.book.title.titletxt
        if c.book.visible:
            title = c.book.title.seriestxt + ': ' + title

        author = c.book.title.authortxt
        width = len(title) + len(author)

        # most of the time you will just look up the member associated with
        # the checkouts, but if you passed in checkouts by a book, they
        # will belong to different people, possibly pseudo

        if lookup_member is None or c.member_id != member.member_id:
            lookup_member = Member(dex, c.member_id)
        if enum:
            print('%d.' % (n + 1),)

        if width <= ll - 1:
            print(author + ' ' * (ll - width) + title)
        else:
            print(author)
            print(offset + ' ' + ' ' * (ll - len(title) - 1) + title)

        if c.checkin_stamp:
            duestr = c.checkin_user
            duedate = c.checkin_stamp.date()
        elif c.lost:
            duedate = c.checkin_stamp.date()
            duestr = Color.warning('LOST')
        elif lookup_member.pseudo:
            duestr = ''
            duedate = ''
        else:
            duestr = 'Due:'
            duedate = color_due_date(c.due_stamp)

        print(offset + ' %*s %8s %s %s %s' % (
            ll - 41,
            str(c.book.shelfcode) + ((' ' + c.book.barcodes[-1])
                                     if c.book.barcodes else ''),
            c.checkout_user,
            c.checkout_stamp.date(),
            max(8 - len_color_str(duestr), 0) * ' ' + duestr,
            duedate,
            ))
    dex.db.rollback()


def rmenu(*args, **kw):
    return menu(*args, cleanup=dex.db.rollback, **kw)


if __name__ == '__main__':
    main(sys.argv)
