#!/usr/bin/python


import sys
from mitsfs.util.ui import banner, specify_book, read
from mitsfs.barcode import valifrob
from mitsfs.dexdb import DexDB
__release__ = '0'

program = 'barcoder'


def main(args):
    banner(program, __release__)

    dex = DexDB()

    while True:
        book = specify_book(dex)

        if not book:
            break

        print('Adding barcode to:')
        print(book)

        while True:
            text = read('New Barcode: ')
            code = valifrob(text)

            # SKABETTI
            if code:
                other = dex.barcode(code)
                if other:
                    print("No, that's", other)
                    continue
                if book.addbarcode(code):
                    print('Now:')
                    print(book)
                else:
                    print('Error assigning code?')
                break
            else:
                if text:
                    print('Invalid Code')
                else:
                    break


if __name__ == '__main__':
    main(sys.argv)
