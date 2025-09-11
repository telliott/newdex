from mitsfs.core import db
from mitsfs.ui import money_str
from mitsfs.constants import OVERDUE_DAY, MAX_OVERDUE

'''
Classes to write and retrieve the various financial transactions a member can
engage in.
'''


def get_transactions(db, member_id, include_voided=True):
    """
    returns a list of transactions associated with a member

    Parameters
    ----------
    db : db object
        The db to query against.
    member : int
        The member_id of the member
    include_voided: boolean
        Whether or not to include transactions that have been voided

    Returns
    -------
    list(Transaction)
        A list of all transactions for a member, in chronological order.
    """
    if include_voided:
        sql = ('select'
               '  transaction_id'
               ' from transaction'
               ' where member_id = %s'
               ' order by transaction_created')
    else:
        # TODO: This is a monstrosity, and I think it could be trivially
        # solved by just putting a voided column onto the transaction row.
        sql = ("select"
               "  transaction_id"
               " from transaction"
               " where transaction_id in ("
               "select t0.transaction_id"
               "  from transaction t0"
               "  where"
               "   t0.transaction_type != 'V' and"
               "   t0.member_id = %s"
               "  except ("
               "   select t1.transaction_id"
               "    from"
               "     transaction t1"
               "     inner join transaction_link tl"
               "      on (t1.transaction_id = tl.transaction_id1)"
               "     inner join transaction t2"
               "      on (t2.transaction_id =  tl.transaction_id2)"
               "    where t2.transaction_type = 'V'"
               "   union select t1.transaction_id"
               "    from"
               "     transaction t1"
               "     inner join transaction_link tl"
               "      on (t1.transaction_id = tl.transaction_id2)"
               "     inner join transaction t2"
               "      on (t2.transaction_id = tl.transaction_id1)"
               "    where t2.transaction_type = 'V'))"
               " order by transaction_created")

    return [Transaction(db, member_id, i)
            for i in
            db.cursor.execute(sql, (member_id,))]


def get_CASH_id(db):
    # Can't use find_members here because it would create a
    # circular dependency
    return db.cursor.selectvalue('select member_id from member'
                                 " where email = 'CASH'")


class Transaction(db.Entry):
    def __init__(self, db, member_id, transaction_id=None, **kw):
        super().__init__(
            'transaction', 'transaction_id', db, transaction_id, **kw)
        if transaction_id is None:
            self.member_id = member_id
        self.linked = None

    transaction_id = db.ReadField('transaction_id')

    member_id = db.Field('member_id')
    amount = db.Field('transaction_amount')
    transaction_type = db.Field('transaction_type')
    description = db.Field('transaction_description')

    created = db.ReadField('transaction_created')
    created_by = db.ReadField('transaction_created_by')
    created_with = db.ReadField('transaction_created_with')

    @property
    def type_description(self):
        '''
        Text descriptions of the types of transactions

        Returns
        -------
        type: str
            text description
        '''
        descriptions = {'D': 'Donation',
                        'F': 'Fine',
                        'K': 'Keyfine',
                        'P': 'Payment',
                        'L': 'LHE',
                        'M': 'Membership',
                        'R': 'Reimbursement',
                        'V': 'Void'
                        }
        return descriptions[self.transaction_type]        
        
    @property
    def linked_transaction(self):
        '''
        If the transaction is linked to another transaction, get that
        transaction object.
        Because a transaction may have no link, we have to track the query
        separate from the result.

        Returns
        -------
        Transaction
            DESCRIPTION.

        '''
        if self.linked is None:
            self.linked = [Transaction(self.db, None, i)
                           for i in
                           self.db.cursor.execute(
                               'select transaction_id1 from transaction_link'
                               ' where transaction_id2 = %s'
                               ' union '
                               'select transaction_id2'
                               ' from transaction_link'
                               ' where transaction_id1 = %s',
                               (self.id, self.id,))]
        return self.linked

    def is_void(self):
        return self.transaction_type == 'V' \
            or 'V' in [x.transaction_type for x in self.linked_transaction]

    def _void_transaction(self):
        '''
        Internal method to create a transaction object that voids this object

        Returns
        -------
        new : Transaction
            The transaction needed to void this transaction.
        '''
        new = Transaction(self.db, self.member_id)
        new.amount = -self.amount
        new.transaction_type = 'V'
        new.description = f'VOIDED: {str(self.created.today())}' + \
            f' Desc: {self.description}'
        new.create()

        # link the voided transaction with the original
        self.db.cursor.execute(
             'insert into transaction_link values (%s, %s)',
             (self.id, new.id))

        # reset the cache on linked because we added a transaction
        self.linked = None

        return new

    def void(self):
        '''
        Voids this transaction. Needs to check to see if there's a linked
        transaction so as to void both.

        Returns
        -------
            List of all transaction objects voided by this request

        '''
        if self.id is None:
            print("no transaction ID specified. Nothing to do.")
            return
        if self.is_void():
            print("Transaction already void, nothing to do...")
            return

        retval = [self]

        # see if there's a linked transaction that we also need to void. Messy!
        # However, since we already checked to see if we were void, any
        # transactions remaining should also be voided.

        for t in [i for i in self.linked_transaction
                  if i.transaction_type != 'V']:
            # can't call void directly, because it will try to link and find us
            t._void_transaction()
            retval.append(t)

        self._void_transaction()

        self.db.commit()
        return retval

    def __str__(self):
        '''
        Returns
        -------
            the Dex string representing a transaction
        '''
        return ', '.join((money_str(self.amount), str(self.created.date()),
                         self.transaction_type, self.description))

    def __repr__(self):
        '''
        Returns
        -------
            all the fields for debugging
        '''
        s = ', '.join(["%s: %s" % (x, str(getattr(self, x))) for x in
                       ['transaction_id', 'member_id', 'amount',
                        'transaction_type', 'description']])
        return "Transaction(" + s + ")"


class CashTransaction(Transaction):
    def __init__(self, db, member_id, member_str, transaction_id=None, **kw):
        '''
        A transaction involving a a cash payment. Writes two transactions
        under the hood - one to the member and one to the cash drawer.

        Parameters
        ----------
        db : Database
            The database to write to
        member_id: int
            The member the fine is being levied against
        checkout_id: int
            The particular book checkout that generated the fine

        Returns
        -------
            None.
        '''
        super().__init__(db, member_id, None, **kw)
        self.member_str = member_str

    def create(self, commit=True):
        '''
        This is such a hack. Creates a second transaction object to log
        intake against CASH and links the two together.

        Write-only class. Load as a normal transaction.

        Parameters
        ----------
        commit : Boolean, optional
            Whether to commit these transactions to the db. Default is True.

        Returns
        -------
            None.
        '''
        cash_id = get_CASH_id(self.db)
        cash = Transaction(self.db, self.member_id)
        cash.member_id = cash_id
        cash.amount = self.amount
        cash.transaction_type = self.transaction_type
        cash.description = "Cash transaction for %s: %s" % (self.member_str,
                                                            self.description)
        super().create(commit=False)
        cash.create(commit=False)

        # link the two transactions together
        self.db.cursor.execute(
             'insert into transaction_link values (%s, %s)',
             (self.id, cash.id))

        # reset the cache on linked because we added a transaction
        self.linked = None

        if commit:
            self.db.commit()


class FineTransaction(Transaction):
    def __init__(self, db, member_id, checkout_id, **kw):
        '''
        A transaction of type 'F' that is also associated with a checkout.

        Write-only class. Load as a normal transaction.

        Parameters
        ----------
        db : Database
            The database to write to
        member_id: int
            The member the fine is being levied against
        checkout_id: int
            The particular book checkout that generated the fine

        Returns
        -------
            None.
        '''
        super().__init__(db, member_id, None, **kw)
        self.checkout_id = checkout_id
        self.transaction_type = 'F'

    def create(self, commit=True):
        '''
        Creates a normal transaction, but then also associates that
        transaction with a checkout.

        Parameters
        ----------
        commit : Boolean, optional
            Whether to commit these transactions to the db. Default is True.

        Returns
        -------
            None.
        '''
        super().create(commit=False)

        # record this amount into the fine_payment table. No idea why
        self.db.cursor.execute(
             'insert into fine_payment (checkout_id, transaction_id)'
             ' values (%s, %s)',
             (self.checkout_id, self.id))

        if commit:
            self.db.commit()


class OverdueTransaction(FineTransaction):

    def __init__(self, db, member_id, checkout_id, days=0, book=None):
        '''
        Will calculate the fine associated with the overdue book. So it's a
        Transaction, but it has different init parameters.

        Note that this is a create-only class. You read it back as a
        normal transaction. That simply means you can't construct the
        object from the transaction ID.

        Parameters
        ----------
        db : database
            The database to operate on
        member_id : int
            The member id.
        days : int, optional
            Number of days the book is overdue. The default is None.
        book : a book object, optional
            The book being returned. The default is None.

        Returns
        -------
        None.

        '''
        super().__init__(db, member_id, checkout_id)

        # TODO: Why can't we calculate this from the checkout_id?
        if days:
            self.amount = -min(days * OVERDUE_DAY, MAX_OVERDUE)
            if book:
                self.description = 'Book %s overdue %d days.' % (book, days)

