#!/usr/bin/python
'''

Code for keeping track of inventories and inventory-like behavior

'''


from mitsfs import dexdb
from mitsfs import dexfile
from mitsfs.dex.title import Title


__all__ = [
    'Inventory', 'InventoryUnknown',
    ]


class InventoryException(Exception):
    def __init__(self, *args, **kw):
        super(InventoryException, self).__init__(*args)
        for k, v in kw.items():
            setattr(self, k, v)


class InventoryUnknown(InventoryException):
    pass


class InventoryKnown(InventoryException):
    pass


class Inventory(object):
    def __init__(self, dex, code=None, desc=None):
        self.code = code
        self.dex = dex
        self.closed = None
        if code is not None:
            self.dex.cursor.execute(
                'select inventory_id, inventory_code,'
                '  inventory_desc, inventory_stamp, inventory_closed'
                ' from inventory where inventory_code=%s',
                (code,))
        else:
            self.dex.cursor.execute(
                'select inventory_id, inventory_code,'
                ' inventory_desc, inventory_stamp, inventory_closed'
                ' from inventory where inventory_closed is null'
                ' order by inventory_stamp desc limit 1')
        self._packet = []
        result = self.dex.cursor.fetchall()
        if result:
            ((self.id, self.code, self.desc, self.opened, self.closed),
             ) = result
        else:
            if desc:
                self.dex.cursor.execute(
                    'insert into inventory'
                    ' (inventory_code, inventory_desc)'
                    ' values (%s, %s)',
                    (code, desc))
                self.desc = desc
                (self.id,) = self.dex.cursor.execute(
                    'select last_value from id_seq')
                (self.opened,) = self.dex.cursor.execute(
                    'select inventory_stamp from inventory'
                    ' where inventory_id=%s', self.id)
                self.dex.db.commit()
            else:
                raise InventoryUnknown(
                    'Unknown inventory %s' % code, code=code)

    def setup(self):
        c= self.dex.cursor.execute(
            'select count(inventory_entry_id)'
            ' from'
            '  inventory_entry'
            '  natural join inventory_missing'
            ' where missing_count is not null'
            '  and inventory_id=%s',
            (self.id,))
        count = c.fetchone()[0]
        if count != 0:
            print ("INVID: %s" % self.id)
            raise InventoryKnown(
                "There are missing books recorded in %s already" % self.code)
        self.serial = 0
        self.dex.cursor.execute(
            'delete from inventory_entry where inventory_id=%s',
            (self.id,))
        self.dex.cursor.execute(
            'delete from inventory_packet where inventory_id=%s',
            (self.id,))
        self.dex.db.commit()

    def packet(self, code, shelfcode):
        xeq = self.dex.cursor.execute
        xeq('insert into inventory_packet'
            ' (inventory_id, inventory_packet_name)'
            ' values (%s, %s)',
            (self.id, code))
        (self.packet_id,) = xeq('select last_value from id_seq')
        (self.shelfcode_id,) = xeq(
            'select shelfcode_id from shelfcode where shelfcode=%s',
            (shelfcode,))

    def click(self):
        if self._packet:
            self.dex.cursor.executemany(
                'update inventory_entry'
                ' set inventory_packet_id = %s,'
                '     entry_number = %s'
                ' where inventory_entry_id=%s',
                self._packet)
            self._packet = []
            self.dex.db.commit()

    def add(self, title, count):
        self.serial += 1
        self._packet.append(
            (self.packet_id, self.serial, title.inventory_entry_id))

    def compute(self):
        self.setup()
        xeq = self.dex.getcursor().execute
        xeq("insert into inventory_entry"
            " (title_id, book_series_visible, doublecrap, shelfcode_id,"
            "  inventory_id, entry_expected)"
            " select"
            "  title_id, book_series_visible, doublecrap, shelfcode_id,"
            "  %s, count(book_id)"
            " from"
            "  book"
            "  natural join shelfcode"
            "  where"
            "   not withdrawn and"
            "   shelfcode_type != 'B'"
            "   and book_id not in"
            "    (select book_id from checkout where checkin_stamp is null)"
            "  group by"
            "   title_id, book_series_visible, doublecrap, shelfcode_id",
            (self.id,))

    def codes(self):
        c = self.dex.cursor.execute(
            'select distinct shelfcode'
            ' from shelfcode natural join inventory_entry'
            ' where inventory_id=%s',
            (self.id,))
        
        return [x[0] for x in c.fetchall()]

    def shelf(self, shelfcode):
        xeq = self.dex.getcursor().execute
        for (title_id, inventory_entry_id, book_series_visible, doublecrap,
             count) in \
            xeq('select'
                '  title_id, inventory_entry_id, book_series_visible,'
                '  doublecrap, entry_expected'
                ' from'
                '  inventory_entry'
                '  natural join shelfcode'
                ' where inventory_id=%s and shelfcode=%s',
                (self.id, shelfcode)):
            t = Title(self.dex, title_id)
            line = dexfile.DexLine(
                authors=t.authors,
                titles=t.titles,
                series=t.series,
                codes={shelfcode: count})
            line.inventory_entry_id = inventory_entry_id
            yield (
                line.shelfkey(
                    ('@' if book_series_visible else '') +
                    shelfcode +
                    (doublecrap if doublecrap else '')),
                line)
