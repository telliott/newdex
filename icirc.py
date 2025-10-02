#!/usr/bin/python3

import sys
import optparse
import datetime

from mitsfs.ui import Color, tabulate, money_str, \
                read, readmoney, readaddress, readdate, \
                readvalidate, readnumber, readyes, reademail, readphone, \
                readinitials, specify, specify_book, specify_member, \
                len_color_str, termwidth

from mitsfs import ui

from mitsfs.circulation import members
from mitsfs.circulation.transactions import get_transactions, \
    Transaction, CashTransaction
from mitsfs.circulation.checkouts import Checkouts

from mitsfs import library
from mitsfs.core import settings
from mitsfs.util import selecters

__release__ = '1.1'

program = 'greendex'

member = None


parser = optparse.OptionParser(
    usage='usage: %prog [options]',
    version='%prog ' + __release__)

'''
icirc is the circulation system app. It handles everything involving people -
adding/deleting members, memberships, checkin/checkout, fines, transactions

The circulation system is built around a set of menus, each of which contains
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

def no_member_header():
    '''
    Clears the screen and prints the header when there's no member selected'
    '''

    ui.clear_screen()
    width = min(termwidth(), 80) - 1
    print('-' * width)
    print(f'{"MITSFS Circulation System":^{width}}')
    print('-' * width)


def member_header(member, title='Member Menu'):
    '''
    Clears the screen and prints the header for the member selected menus'
    '''
    ui.clear_screen()
    width = min(termwidth(), 80) - 1
    title = f'  {title}  '

    print(f'{title:-^{width}}')

    # first row contains member name (including keyholder initials) and
    # membership status. We get the left justification here by calculating
    # length of the fields and padding the rest. Don't forget to strip
    # out any ansi terminal colors!
    name_len = len_color_str(member)
    membership_head = 'Membership: ' + member.membership.description
    membership_head_len = len(membership_head)
    keyholder = f' ({member.key_initials})' if member.key_initials else ''
    spaces = ' ' * max(1, width - name_len -
                       membership_head_len - len(keyholder))
    print(f'{member}{keyholder}{spaces}{membership_head}')

    books_out = len(member.checkout_history.out)
    match books_out:
        case 0:
            books_out = "No books out"
        case 1:
            books_out = "1 book out"
        case _:
            books_out = f'{books_out} books out'

    # second row contains the financial balance, books out and member expiry
    # We center the books out by calculating the length of the spacing in the
    # middle, then putting the books in that
    balance = money_str(member.balance)
    balance_len = len('Balance: ') + len_color_str(balance)
    expiry_len = len_color_str(member.membership.expiry)
    spaces = max(1, width - balance_len - expiry_len)
    print(f'Balance: {balance}{books_out:^{spaces}}{member.membership.expiry}')
    print('-' * width)
    return


def main(args):
    # all the information about the library.
    global library  
    # if a member is selected, they will be in here
    global member 

    library = library.Library()

    if library.db.dsn != settings.DATABASE_DSN:
        library.log.warn(f'Using database: {library.db.dsn}')

    main_menu('')


def main_menu(line):

    def select(line):
        '''
        Select a user to work with in the user menus
        '''
        global member
        member = specify_member(library.members, line)
        if member:
            member_menu(line)
        no_member_header()

    def checkin(line, pick_date=False):
        '''
        Basic checkin of a book, today. Select a book, see the checkout
        and check it back in as of now.
        '''
        no_member_header()

        while True:
            book = specify_book(
                library,
                authorcomplete=library.catalog.authors.complete_checkedout,
                titlecomplete=library.catalog.titles.complete_checkedout,
                # TODO: this isn't currently working for books that are
                # withdrawn while checked out
                title_predicate=lambda title: title.checkedout,
                book_predicate=lambda book: book.out
                )

            if not book:
                break

            # This is off by default, but turned on if you call it from the
            # advanced checkin menu.
            checkin_date = None
            if pick_date:
                print("Specify check in date:")
                checkin_date = readdate(datetime.datetime.today(), False)

            no_member_header()
            checkouts = book.checkout_history.out
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
        '''
        Checkin that lets you specify a date. Useful for bookdrop processing
        '''
        checkin(line, pick_date=True)

    def newmem(line):
        '''
        Add a member, and let them buy a membership
        '''
        no_member_header()
        print("Adding a new member")

        first = readvalidate("First Name: ").strip()
        last = readvalidate("Last Name: ").strip()

        # Find will split the string on the space and search for both parts
        names = library.members.find(f'{first} {last}')
        if len(names) > 0:
            print("The following people are already library members:")
            for n in names:
                print("    " + str(n))
            print('Are your sure you want to continue, instead of editing a')
            print('membership in the edit menu?')
            if not readyes('Continue? [' + Color.yN + '] '):
                return
        email = reademail("Email (required): ")
        phone = readphone("Phone number: ")
        address = readaddress()

        if not readyes('Add this member? [' + Color.yN + '] '):
            return

        newmember = members.Member(library.db, first_name=first,
                                   last_name=last, email=email,
                                   phone=phone, address=address)
        newmember.create(commit=True)

        # since we're creating a member, should set that to the global
        # so that we can check out books for them, etc.
        global member
        member = members.Member(library.db, newmember.id)

        print()
        print('Member added.')
        print()

        if readyes('Add a membership to new member? [' + Color.yN + '] '):
            membership(None)
        member_menu(line)
        no_member_header()

    def display(line):
        '''
        List all copies of the selected book, with who has it checked out
        '''
        no_member_header()
        title = specify(library)
        if not title:
            return

        for book in title.books:
            print(book)
            if book.out:
                print(
                    book.checkout_history.out.member_display('     Out to: '))
        print()

    no_member_header()
    print('Main Menu')
    print()

    recursive_menu([
        ('S', 'Select Member', select),
        ('I', 'Check In Books', checkin),
        ('B', 'Bookdrop Checkin (Choose Date)', checkin_advanced),
        ('N', 'New Member', newmem),
        ('D', 'Display Book', display),
        ('A', 'Admin', admin),
        ('Q', 'Quit', None),
        ])


def member_menu(line):

    def checkout(line, advanced=False):
        '''
        Check out a book for the active member

        Handles both regular and advanced checkouts. By default,
        can only check out circulating books today to members who are in good
        standing. If you need to violate these rules, you'll be directed to
        the nonstandard checkout.
        '''
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
                    print(correct + ' or use nonstandard  checkout.')
                    return

            # Only select from circulating books unless we're using nonstandard
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
                library,
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
        '''
        Invokes checkout with the advanced setting
        '''
        checkout(line, advanced=True)

    def checkin_member(line, pick_date=False):
        '''
        Select from the member's checked out books and check one back in.
        Lets you choose a date if you are in advanced mode
        '''
        member_header(member)
        while True:
            if not member.checkout_history.out:
                print(Color.warning('No books are checked out.'))
                return

            checkout = selecters.select_checkout(member.checkout_history.out)
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
        '''
        Invokes checkin with the advanced setting
        '''
        checkin_member(line, pick_date=True)

    def lost(line):
        '''
        Marks a book lost. Sad!
        '''
        member_header(member)
        if not member.checkout_history.out:
            print(Color.warning('No books are checked out.'))
            return

        while True:
            if not member.checkout_history.out:
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
        '''
        View balance and let them choose to pay some or all of it
        '''
        member_header(member)
        check_balance(member, print_notices=True)

    def unselect(line):
        '''
        Stop working with this member
        '''
        global member
        member = None
        no_member_header()
        print('Main Menu')
        print()
        # returning an explicit False lets us go up a menu level
        return False

    member_header(member)
    recursive_menu([
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
    '''
    Menu for viewing various histories
    '''

    def checkout_history(line):
        member_header(member, 'Checkout History')
        print(member.checkout_history.display())

    def financial_history(line):
        member_header(member, 'Financial History')
        print(tabulate(
            [('Amount', 'Keyholder', 'Date', 'Type', 'Description')] +
            [(money_str(t.amount), t.created_by, t.created.date(),
                t.type_description, t.description)
                for t in member.transactions]))

    def membership_history(line):
        member_header(member, 'Membership History')
        print(tabulate(
            [("Membership History", "Keyholder", "Bought")] +
            [(str(m), str(m.created_by), str(m.created.date()))
             for m in member.membership_history]))

    member_header(member)
    print(member.info())

    recursive_menu([
        ('C', 'Check Out History', checkout_history),
        ('F', 'Financial History', financial_history),
        ('M', 'Membership History', membership_history),
        ('Q', 'Back to User Menu', None),
        ], title="View Member:")

    # need to print the header for the menu we are returning to
    member_header(member)


def editmem(line):
    '''
    Menu for editing the attributes of a member, adding memberships, keying
    and committee management
    '''
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

    def renew_membership(line):
        membership(line)
        member_header(member)

    def edit_member(line):
        member_header(member)
        print()
        print(member.info())
        recursive_menu([
            ('N', 'Change Name', edit_name),
            ('E', 'Change Email', edit_email),
            ('A', 'Change Address', edit_address),
            ('P', 'Change Phone', edit_phone),
            ('Q', 'Back to Membership', None)
            ], title='Change Member Information')
        member_header(member)

    member_header(member)

    if member.pseudo:
        print("WARNING editing pseudo account: %s is disallowed." % (member,))
        print("Email libcomm@mit.edu if you need to modify information")
        print("in a pseudo user account.")
        return

    print()
    print(member.info())
    recursive_menu([
        ('M', 'New/Renew Membership', renew_membership),
        ('E', 'Edit Member', edit_member),
        ('*', 'Star Chamber', starchamber),
        ('Q', 'Main Menu', None),
        ], title='Membership')

    # need to print the header for the menu we are returning to
    member_header(member)


def starchamber(line):
    '''
    Key/dekey the active member, add and remove from committees, and merge
    a duplicate member with this one.
    '''
    def key(line):
        print('Keying', member.full_name)
        role = None
        if member.rolname:
            role = member.rolname
        elif member.email.lower().endswith('@mit.edu'):
            role = member.email.split('@')[0].lower()

        role = read('Kerberos name? ', preload=role)
        if not role:
            return
        while True:
            inits = readinitials("Keyholder initials? ").strip()
            if member.check_initials_ok(inits):
                member.key(role, inits)
                member_header(member, 'Star Chamber')
                print(f'{member.full_name} keyed')
                return
            else:
                print('Those initials have already been taken.'
                      'Please try again.')

    def dekey(line):
        print('Dekeying', member.full_name)
        if not readyes('Are you sure? '):
            return
        cttes = member.committees
        member.dekey()
        member_header(member, 'Star Chamber')
        print(f'{member.full_name} dekeyed')
        if cttes:
            print(f'{member.first_name} was on', ' '.join(cttes))

    def add_to_committee(line):
        committee = read(
            'Committee? ',
            callback=lambda: members.star_cttes(library.db) + ['*chamber'],
            ).lower().strip()
        if not committee:
            return
        member.grant(committee)
        member_header(member, 'Star Chamber')
        print(f'{member.full_name} is now in {list_clean(member.committees)}')
        committee_members = list_clean(str(m.full_name)
                                       for m in
                                       members.role_members(library.db,
                                                            committee))
        print(f'{committee} members: {committee_members}')

    def remove_committee(line):
        committee = read(
            'Committee? ',
            callback=lambda: member.committees,
            ).lower().strip()
        if not committee:
            return
        member.revoke(committee)
        member_header(member, 'Star Chamber')
        print(f'{member.full_name} is removed from {committee}')
        committee_members = members.role_members(library.db, committee)

        if committee_members:
            memlist = list_clean(str(m.full_name) for m in committee_members)
            print(f'{committee} members: {memlist}')
        else:
            print(f'{committee} now has no members')

    def merge(line):
        print('User entry that is merging with this one')
        other = specify_member(library.members, line)
        if other is None:
            return
        if other.id == member.id:
            print('Merge target must differ from merge subject')
            return

        other_name = other.full_name
        member.merge(other)
        member_header()
        print(f'Merged {other_name} into {member.full_name}')

    def menu_options():
        if not member.key_initials:
            return [
                ('K', 'Key this member', key),
                ('Q', 'Back to Other Menu', None),
                ]
        else:
            return [
                ('D', 'De-key this member', dekey),
                ('A', 'Add this member to a committee', add_to_committee),
                ('R', 'Remove this member from a committee', remove_committee),
                ('Q', 'Back to Other Menu', None),
                ]

    member_header(member)

    recursive_menu(menu_options, title='Star Chamber')
    member_header(member)


def financial(line):
    '''
    Perform various financial transactions.
    '''
    def financial_header():
        '''
        Normal member header with a different title
        '''
        member_header(member, 'Transactions')

    def donation(line):
        '''
        Book donation for fine credit
        '''
        financial_header()
        print('Enter amount of donation, this will increase'
              'the member\'s balance.')
        amount = readmoney().copy_abs()
        desc = read('Enter description: ', history='description')
        print('Adding %s to account of %s.' % (money_str(amount), member))
        if not readyes(
                'Commit the transaction? [' + Color.yN + '] '):
            return
        tx = Transaction(library.db, member.id, amount=amount,
                         transaction_type='D', description=desc)
        tx.create()
        financial_header()

    def assess_fine(line, tx_type='F'):
        '''
        Add a fine.
        '''
        financial_header()
        print('Enter the fine amount, this will decrease '
              'the member\'s balance.')
        amount = -readmoney().copy_abs()
        desc = read('Enter description: ', history='description')

        print(f'Adding {money_str(amount)} to account of {member}.')
        if not readyes(
                'Commit the transaction? [' + Color.yN + '] '):
            return
        tx = Transaction(library.db, member.id, amount=amount,
                         transaction_type=tx_type, description=desc)
        tx.create()
        financial_header()

    def assess_keyfine(line):
        '''
        the same as assess_fine, but with a Keyholder fine type
        Unclear why those are different.
        '''
        assess_fine(line, type='K')

    def payment(line):
        '''
        Accept cash from a member to get their balance healthy
        '''
        financial_header()
        print('Enter the amount being paid, this will increase'
              ' the member\'s balance.')
        amount = readmoney().copy_abs()
        desc = read('Enter description: ', history='description')

        print(f'Adding {money_str(amount)} to account of {member}.')
        print(f'Adding {money_str(amount)} to cash drawer')
        if not readyes(
                'Commit the transaction? [' + Color.yN + '] '):
            return
        cash_tx = CashTransaction(library.db, member.id, member.normal_str,
                                  amount=amount, transaction_type='P',
                                  description=desc)
        cash_tx.create()
        financial_header()

    def lhe_transaction(line):
        '''
        LHE gets to just do arbitrary transactions
        '''
        financial_header()
        print('Enter amount (negative for fines, positive for credit).')
        amount = readmoney()
        desc = read('Enter description: ', history='description')

        print('Adding %s to account of %s.' % (money_str(amount), member))
        if not readyes(
                'Commit the transaction? [' + Color.yN + '] '):
            return
        tx = Transaction(library.db, member.id, amount=amount,
                         transaction_type='L', description=desc)
        tx.create()
        financial_header()

    def pay_membership(line):
        '''
        Usually don't want to be here, as you get a chance tp pay while
        creating a membership. But if you didn't pay at that time, you can
        do it here.'
        '''
        financial_header()
        print('Warning, this does not update the member\'s membership.'
              ' It is only used when the member previously bought a'
              ' membership and is now paying. Use the Edit Member menu'
              ' to add a new membership; They can pay there.')
        print('Enter an amount; this will decrease the member\'s balance.')
        amount = -readmoney().copy_abs()
        desc = read('Enter description: ', history='description')

        print('Adding %s to account of %s.' % (money_str(amount), member))
        if not readyes(
                'Commit the transaction? [' + Color.yN + '] '):
            return
        tx = Transaction(library.db, member.id, amount=amount,
                         transaction_type='L', description=desc)
        tx.create()
        financial_header()

    def reimbursement(line):
        '''
        A bit of a misnomer. Takes cash out of the mitsfs account and returns
        it to the member. But also decreases that member's balance as a result.
        '''
        financial_header()
        print('Enter the amount the member is being reimbursed, this'
              ' will decrease the member\'s balance.')
        amount = -readmoney().copy_abs()
        desc = read('Enter description: ', history='description')

        print(f'Adding {money_str(amount)} to account of {member}.')
        print(f'Adding {money_str(amount)} to cash drawer')
        if not readyes(
                'Commit the transaction? [' + Color.yN + '] '):
            return
        cash_tx = CashTransaction(library.db, member.id, member.normal_str,
                                  amount=amount, transaction_type='R',
                                  description=desc)
        cash_tx.create()
        financial_header()

    def void_transaction(line):
        '''
        Voids a previous transaction. This gets a little complicated, because
        it also needs to void any linked transactions
        '''
        financial_header()
        txns = get_transactions(library.db, member.id, include_voided=False)

        if len(txns) == 0:
            print("No transactions to void.")
            return

        # generate a selectable list of previous transactions
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
                [(members.Member(library.db, tx.member_id).full_name,
                  money_str(tx.amount), tx.created_by, tx.created.date(),
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
        recursive_menu(menu, title="Advanced Financial Transactions")
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
    recursive_menu(menu, title='Financial Transactions')

    member_header(member)


def admin(line):
    '''
    Miscellaneous star chamber functions
    '''

    def invalid_logins(line):
        '''
        We shouldn't have any database logins that don't correspond to
        keyholders. This menu will tell you who they are.
        '''

        no_member_header()
        logins = members.invalid_logins(library.db)
        if logins:
            print('These roles can login, but are not tied to a member.')
            print('Key them or get the speaker-to-postgres to remove them):')
            print(' '.join(logins))
        else:
            print("No logins are unassociated. Gold star.")

    def committee_list(line):
        '''
        Committees managed by this system (since they define access)
        and who is in them.
        '''
        no_member_header()
        for committee in members.star_committees(library.db):
            print(committee, list_clean(
                str(member.key_initials)
                for member in members.role_members(library.db, committee)))

    def keylist(line):
        '''
        List of keyholders and what committees they are on
        '''
        no_member_header()
        for key in members.role_members(library.db, 'keyholders'):
            print(key.full_name, list_clean(key.committees))
        print()

    def vgg(line):
        '''
        List all the overdue books
        '''
        no_member_header()
        checkouts = Checkouts(library.db)
        for email, name, overdue in checkouts.vgg():
            print(name, '<' + email + '>')
            for stamp, code, title in overdue:
                print('', stamp, code, title)

    no_member_header()
    menu = [
        ('?', 'Check for invalid logins', invalid_logins),
        ('C', 'List committees', committee_list),
        ('W', 'Who are keyholders', keylist),
        ('V', 'Overdue Books', vgg),
        ('Q', 'Back to Main Menu', None)
        ]
    recursive_menu(menu, title='Admin')
    no_member_header()


def list_clean(x):
    '''
    prints (list item 1, list item 2) unless it's empty

    Parameters
    ----------
    x : list(str)
        list of items to print

    Returns
    -------
    str
        a stringified list if there are elements

    '''
    if not x:
        return ''
    return '(%s)' % ', '.join(x)


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
            tx = CashTransaction(library.db, member.member_id,
                                 member.normal_str, amount=amount,
                                 transaction_type='P', description=desc)
            tx.create()

    elif print_notices:
        print("Member doesn't have a negative balance")

    return member.balance >= 0


def recursive_menu(*args, **kw):
    return ui.menu(*args, cleanup=library.db.rollback, **kw)


if __name__ == '__main__':
    main(sys.argv)
