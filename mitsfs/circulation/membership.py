import datetime

from mitsfs.core import db
from mitsfs import ui

'''
Basic information about what membership a person has, along with what it cost
and when it expires
'''


class Membership(db.Entry):
    def __init__(self, db, membership_id=None, **kw):
        super().__init__(
            'membership', 'membership_id', db, membership_id, **kw)

    membership_id = db.ReadField('membership_id')

    member_id = db.ReadField('member_id')
    expires = db.ReadField('membership_expires')
    membership_type = db.ReadField('membership_type')
    payment_id = db.ReadField('membership_payment')

    # unclear if we need to expose these
    created = db.ReadField('membership_created')
    created_by = db.ReadField('membership_created_by')
    created_with = db.ReadField('membership_created_with')


    
    @property
    def description(self):
        '''
        Gets the description of the type of membership the person has based
        on their membership type

        Returns
        -------
        str
            Description string of the membership.

        '''

        return self.cursor.selectvalue(
            'select membership_description'
            ' from membership_type'
            ' where membership_type=%s',
            (self.membership_type,))

    @property
    def expired(self):
        '''
        Figures out whether the current membership for this person is expired

        Returns
        -------
        bool
            True if the membership is expired
        '''
        if self.expires is None:
            return False
        return self.expires.replace(tzinfo=None) < datetime.datetime.today()

    @property
    def cost(self):
        '''
        Returns the cost of the last membership transaction. Checks first
        to see if it was voided, then looks at what was paid in the transaction

        Returns
        -------
        float
            The cost of the transaction.

        '''
        pid = self.payment_id
        v = list(self.cursor.execute(
            'select transaction_id2'
            ' from transaction_link'
            '  join transaction on transaction_id2 = transaction_id'
            " where transaction_id1 = %s and transaction_type='V'",
            (pid,)))
        if v:
            return 0.0

        return self.cursor.selectvalue(
            'select -transaction_amount'
            ' from transaction'
            ' where transaction_id=%s',
            (pid,))

    def __str__(self):
        desc = self.description + " "

        if self.expires is None:
            return desc + ui.Color.good("Expires: Never")

        expires = str(self.expires.date())
        if self.expired:
            return desc + ui.Color.warning("Expired: " + expires)

        return desc + ui.Color.good("Expires: " + expires)
