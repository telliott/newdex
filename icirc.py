#!/usr/bin/python3

import sys
import optparse
import datetime

from mitsfs.dexdb import DexDB
from mitsfs.ui import Color, banner, menu, tabulate, money_str, \
                read, readmoney, readaddress, readdate, \
                readvalidate, readnumber, readyes, reademail, readphone, \
                readinitials, specify, specify_book, specify_member, \
                len_color_str, termwidth

from mitsfs import ui

from mitsfs.circulation.members import Member, format_name
from mitsfs.circulation.transactions import get_transactions, \
    Transaction, CashTransaction
from mitsfs import library
from mitsfs.core import settings
from mitsfs.util import selecters

__release__ = '1.1'

program = 'greendex'


if 'dex' in locals():
    del dex
dex = None
member = None


parser = optparse.OptionParser(
    usage='usage: %prog [options]',
    version='%prog ' + __release__)


def no_member_header():
    ui.clear_screen()
    width = min(termwidth(), 80) - 1
    print('-' * width)
    print(f'{"MITSFS Circulation System":^{width}}')
    print('-' * width)


def member_header(member, title='Member Menu'):
    ui.clear_screen()
    width = min(termwidth(), 80) - 1
    title = f'  {title}  '

    print(f'{title:-^{width}}')
    name_len = len_color_str(member)
    membership_head = 'Membership: ' + member.membership.description
    membership_head_len = len(membership_head)
    spaces = ' ' * max(1, width - name_len - membership_head_len)
    print(f'{member}{spaces}{membership_head}')

    books_out = len(member.checkouts.out)
    match books_out:
        case 0:
            books_out = "No books out"
        case 1:
            books_out = "1 book out"
        case _:
            books_out = f'{books_out} books out'

    balance = money_str(member.balance)
    balance_len = len('Balance: ') + len_color_str(balance)
    expiry_len = len_color_str(member.membership.expiry)
    spaces = max(1, width - balance_len - expiry_len)
    print(f'Balance: {balance}{books_out:^{spaces}}{member.membership.expiry}')
    print('-' * width)
    return


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

    banner(program, __release__)
    if len(args) != 1:
        parser.print_usage()
        sys.exit(1)

    if dex.dsn != settings.DATABASE_DSN:
        print('(' + dex.dsn + ')')

    main_menu('')


def main_menu(line):

    def select(line):
        global member

        line = line.strip()

        if line:
            possibles = library.members.find(line)
            if len(possibles) == 1:
                member = possibles[0]
                return
        member = specify_member(library.members, line)
        member_menu(line)

    def checkin(line, pick_date=False):
        no_member_header()

        while True:
            book = specify_book(
                dex,
                authorcomplete=dex.indices.authors.complete_checkedout,
                titlecomplete=dex.indices.titles.complete_checkedout,
                title_predicate=lambda title: title.checkedout,
                book_predicate=lambda book: book.out)

            if not book:
                break

            checkin_date = None
            if pick_date:
                print("Specify check in date:")
                checkin_date = readdate(datetime.datetime.today(), False)

            no_member_header()
            print(book)
            checkouts = book.checkouts
            if len(checkouts) == 0:
                print("No editions of this book are checked out right now.")
                continue
            if len(checkouts.out) > 1:
                print(Color.warning('Warning: %s is checked out more than once'
                                    % (book,)))
            for checkout in checkouts.out:
                print(Color.info(checkout.checkin(checkin_date)))
        no_member_header()

    def checkin_advanced(line):
        checkin(line, pick_date=True)

    def newmem(line):
        no_member_header()
        print("Please transfer the patron's information from the sheet.")

        first = readvalidate("First Name: ").strip()
        last = readvalidate("Last Name: ").strip()

        # TODO: better search function here
        names = library.members.find(first+last)
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

        newmember = Member(dex, first_name=first, last_name=last,
                           email=email, phone=phone, address=address)
        newmember.create(commit=True)

        global member
        member = Member(dex, newmember.id)

        print()
        print('Member added.')
        print()

        if readyes(
                'Add a membership to new member? [' + Color.yN + '] '):
            membership(None)
        no_member_header()
        print(Color.info(format_name() + ' added to the members'))

    def display(line):
        no_member_header()
        title = specify(dex)
        if not title:
            return

        print(title)
        print()
        print('HOLDINGS - If book is checked out, the member'
              ' it is checked out to')
        print('will be on the next line.')
        for book in title.books:
            print(book)
            if book.out:
                print('    ', book.outto)
        print()

    no_member_header()
    print('Main Menu')
    print()

    rmenu([
        ('S', 'Select Patron', select),
        ('I', 'Check In Books', checkin),
        ('A', 'Bookdrop Checkin (Choose Date)', checkin_advanced),
        ('N', 'New Patron', newmem),
        ('D', 'Display Book', display),
        ('Q', 'Quit', None),
        ])


def member_menu(line):

    def checkout(line, advanced=False):
        member_header(member)
        while True:

            ok, msgs, correct = member.can_checkout(advanced)

            if not ok:
                if advanced:
                    print(Color.warning('\n'.join('WARNING: ' + msg
                                                  for msg in msgs)))
                else:
                    print(Color.warning('\n'.join(msgs)))
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
            member.reset_checkouts()

        member_header(member)

    def checkout_member_advanced(line):
        checkout(line, advanced=True)

    def checkin_member(line, pick_date=False):
        member_header(member)
        while True:
            if not member.checkouts.out:
                print(Color.warning('No books are checked out.'))
                return

            checkout = selecters.select_checkout(member.checkouts.out)
            if checkout is None:
                member_header(member)
                return

            checkin_date = None
            if pick_date:
                print("Specify check in date:")
                checkin_date = readdate(datetime.datetime.today(), False)

            member_header(member)
            print(Color.info(checkout.checkin(checkin_date)))
            print()

    def checkin_member_advanced(line):
        checkin_member(line, pick_date=True)

    def lost(line):
        member_header(member)
        if not member.checkouts.out:
            print(Color.warning('No books are checked out.'))
            return

        while True:
            if not member.checkouts.out:
                break

            checkout = selecters.select_checkout('Select book to '
                                                 'declare as lost: ')
            print()

            if checkout is None:
                return

            if checkout.lost:
                print('That book is already lost.  To unlose it, check it in.')
                continue

            print(checkout.lose())
        member_header(member)

    def pay_fines(line):
        member_header(member)
        check_balance(member, print_notices=True)

    def unselect(line):
        global member
        member = None
        no_member_header()
        print('Main Menu')
        print()
        return False

    member_header(member)
    rmenu([
        ('O', 'Check Out Books', checkout),
        ('N', 'Check Out Books (nonstandard)', checkout_member_advanced),
        ('I', 'Check In Books', checkin_member),
        ('A', 'Check in with Different Date', checkin_member_advanced),
        ('L', 'Declare Book Lost', lost),
        ('V', 'View Member', viewmem),
        ('E', 'Edit Member and Membership', editmem),
        ('P', 'Pay Outstanding Fines', pay_fines),
        ('F', 'Financial Transaction', financial),
        ('Q', 'Unselect Member', unselect),
    ])

    # need to print the header for the menu we are returning to
    no_member_header()
    print('Main Menu')
    print()


def viewmem(line):
    def fin(line):
        member_header(member, 'Financial History')
        print(tabulate(
            [('Amount', 'Keyholder', 'Date', 'Type', 'Description')] +
            [(money_str(t.amount), t.created_by, t.created.date(),
                t.type_description, t.description)
                for t in member.transactions]))

    def history(line):
        member_header(member, 'Checkout History')
        print(member.checkouts.display())
        
    def mem(line):
        member_header(member, 'Membership History')
        print(tabulate(
            [("Membership History", "Keyholder", "Bought")] +
            [(str(m), str(m.created_by), str(m.created.date()))
             for m in member.membership_history]))

    def back(line):
        member_header(member)
        return False

    member_header(member)
    print(member.info())

    rmenu([
        ('C', 'Check Out History', history),
        ('F', 'Financial History', fin),
        ('M', 'Membership History', mem),
        ('Q', 'User Menu', back),
        ], title="View User/Patron:")

    # need to print the header for the menu we are returning to
    member_header(member)


def editmem(line):
    if member.pseudo:
        print("WARNING editing pseudo account: %s is disallowed." % (member,))
        print("Email libcomm@mit.edu if you need to modify information")
        print("in a pseudo user account.")
        return

    def edit_name(line):
        member_header(member, 'Edit Member')
        print(f'Current:\n\t First Name: {member.first_name}, '
              f'Last Name: {member.last_name}')
        first = read("New First Name (blank to retain): ").strip()
        last = read("New Last Name (blank to retain): ").strip()

        if first:
            member.first_name = first
        if last:
            member.last_name = last
        member_header(member, 'Edit Member')
        print()
        print(member.info())

    def edit_email(line):
        member_header(member, 'Edit Member')
        print(f'Current: {member.email}')
        email = reademail("New Email: ").strip()
        print()
        print(member.info())

        if email:
            member.email = email
        member_header(member, 'Edit Member')
        print()
        print(member.info())

    def edit_address(line):
        member_header(member, 'Edit Member')
        print(f'Current: {member.address}')
        address = readaddress()
        if address:
            member.address = address
        member_header(member, 'Edit Member')
        print()
        print(member.info())

    def edit_phone(line):
        member_header(member, 'Edit Member')
        print(f'Current: {member.phone}')
        phone = readphone('New Phone: ').strip()

        if phone:
            member.phone = phone
        member_header(member, 'Edit Member')
        print()
        print(member.info())

    # TODO: Move this to a protected area and expose as part of keying
    def edit_initials(line):
        member_header(member, 'Edit Member')
        print(f'Current: {member.key_initials}')
        inits = readinitials().strip()

        if inits:
            member.key_initials = inits
        member_header(member, 'Edit Member')
        print()
        print(member.info())

    def renew_membership(line):
        membership(line)
        member_header(member)

    def edit_member(line):
        member_header(member)
        print()
        print(member.info())
        rmenu([
            ('N', 'Change Name', edit_name),
            ('E', 'Change Email', edit_email),
            ('A', 'Change Address', edit_address),
            ('P', 'Change Phone', edit_phone),
            ('Q', 'Back to Membership', None)
            ], title='Change Member Information')
        member_header(member)

    member_header(member)
    print()
    print(member.info())
    rmenu([
        ('M', 'New/Renew Membership', renew_membership),
        ('E', 'Edit Member', edit_member),
        ('Q', 'Main Menu', None),
        ], title='Membership')

    # need to print the header for the menu we are returning to
    member_header(member)


def financial(line):

    def financial_header():
        member_header(member, 'Transactions')

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
        financial_header()

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
        financial_header()

    def assess_keyfine(line):
        assess_fine(line, type='K')

    def payment(line):
        financial_header()
        print('Enter the amount being paid, this will increase'
              ' the patron\'s balance.')
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
        financial_header()

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
        financial_header()

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
        financial_header()

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
        financial_header()

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
        financial_header()

    def advanced_financial(line):
        financial_header()
        menu = [
            ('L', 'LHE', lhe_transaction),
            ('R', 'Reimbursement', reimbursement),
            ('V', 'Void Previous', void_transaction),
            ('Q', 'Back to Financial Transactions', None)
            ]
        rmenu(menu, title="Advanced Financial Transactions")
        financial_header()

    financial_header()
    menu = [
        ('D', 'Donation for Fine Credit', donation),
        ('F', 'Assess Fine', assess_fine),
        ('K', 'Assess Keyfine', assess_keyfine),
        ('P', 'Payment', payment),
        ('A', 'Advanced Transactions', advanced_financial),
        ('Q', 'Back to Main Menu', None)
        ]
    rmenu(menu, title='Financial Transactions')

    member_header(member)


def membership(line):
    def validate(line):
        line = line.strip().upper()
        if line in library.membership_types:
            return True
        return False

    print("Select membership type:")

    print(tabulate([Color.select(key) + '.',
                    library.membership_types[key].description,
                    '$%.2f' % library.membership_types[key].cost]
                   for key in library.membership_types.keys()))

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


def rmenu(*args, **kw):
    return menu(*args, cleanup=dex.db.rollback, **kw)


if __name__ == '__main__':
    main(sys.argv)
