#!/usr/bin/python


from mitsfs.util.ui import specify, read, readyes
from mitsfs.dexdb import DexDB


LABEL_GLOSS = """
This is the collection and catalogging of books that were out place.

Ok, make sure that the box/stack/agglomeration you're putting these
books into is labelled somehow.  If it's one of our new boxes, perhaps
consider labelling it with some sort of hang tag/punch card thingy.

Now, what's written on the label?
"""

AUTHOR_TITLE_FORMAT_GLOSS = """
Ok, now I'm going to ask for authors, titles, "formats", and the
preexistence of an orange sticker.  Tab completion works, and is
surprisingly effective.  (If you give it partial authors and title, it
will ask you to pick a 'dex entry.  The format should be one of the
following:
"""

MISTAKE_STICKER_FINISH_GLOSS = """
(If you make a mistake and don't realize until you're starting the
next entry, type OOPS for the format, and it will zap the previous
entry.  Don't worry too hard, the box contents will be reverified in
the next phase.)

Even if it has a sticker on it with a shelfcode, I'm still looking for
what it is, not where we keep it, so please make the decision by its
rigidity, long spine dimension, and bookitude.

Once you're done, just leave a full set of prompts blank.  If you exit
prematurely, just restart the program and give the same answer to the
label question.  If you make a mistake, you can drop the last entry
(but only the last) you sucessfully put in by typing oops at the
Format? prompt.  If you notice an error too late even for that, don't
stress about it, just mention it to the entity running the inventory.

(If you find an object that the 'dex doesn't seem to know about, set
it aside, and hand it to Inventory Actual once you're done with the
box.)
"""

OOPS_GLOSS = """
I'm going to ask you just once to be clear on whether we both agree on
how the "oops" feature works.  I'm about to delete:"""

last_experienced = False


def main():
    d = DexDB()

    ((inventory_code, inventory_id, inventory_desc),) = d.cursor.execute(
        'select inventory_code, inventory_id, inventory_desc'
        ' from inventory order by inventory_stamp desc limit 1')

    print('%s (%s)' % (inventory_desc, inventory_code))
    print(LABEL_GLOSS)
    first = True

    while True:
        label = read('Label: ')
        if not label:
            break

        if first:
            print(AUTHOR_TITLE_FORMAT_GLOSS)

        formats = dict(d.cursor.execute(
            'select format, format_id'
            ' from format where not format_deprecated'))
        for item in sorted(d.cursor.execute(
                'select format, format_description from format'
                ' where not format_deprecated')):
            print('%-4s %s' % item)

        if first:
            print(MISTAKE_STICKER_FINISH_GLOSS)

        read_books(d, inventory_id, label, formats)

        first = False


def read_books(d, inventory_id, label, formats):
    last_title = None
    last_format = None
    global last_experienced
    last_id = None

    title = None

    while True:
        try:
            print()
            title = specify(d, preload=title)
            if title:
                print('selected', out(title))
            else:
                break

            format = read(
                'Format? ',
                callback=formats.iterkeys,
                history='format',
                ).strip().upper()

            if not title and not format:
                break

            if format == 'OOPS':
                if last_id is None:
                    print('There is nothing to undo...')
                    continue
                if not last_experienced:
                    print(OOPS_GLOSS)
                    print(out(last_title, last_format))
                    if not readyes('Are you sure?'):
                        continue
                    last_experienced = True
                print('Undoing', out(last_title, last_format))
                d.cursor.execute(
                    'delete from inventory_found where inventory_found_id=%s',
                    (last_id,))
                d.db.commit()
            elif format not in formats:
                print('Unknown format', format)
                continue
            elif title:
                # this flow is wrong, but...
                # orange = readyes('Orange sticker? ', history='orange')
                orange = False

                # do the deed
                d.cursor.execute(
                    'insert into inventory_found('
                    ' inventory_id, title_id, format_id, found_tag, orange)'
                    ' values (%s, %s, %s, %s, %s)', (
                        inventory_id, title.title_id, formats[format],
                        label, orange))
                (last_id,) = d.cursor.execute('select last_value from id_seq')
                d.db.commit()
                print('entered', out(title, format))
                last_title = title
                last_format = format
                title = None
        except KeyboardInterrupt:
            continue


def out(title, format=None):
    if format:
        fc = [format]
    else:
        fc = []
    return '<'.join([title.authortxt, title.titletxt, title.seriestxt] + fc)


if __name__ == '__main__':
    main()
