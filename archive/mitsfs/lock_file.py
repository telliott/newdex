#!/usr/bin/python
'''

class for locking files

'''


import os
import time
import socket
from io import open


__all__ = [
    'LockException', 'LockFile',
    ]


class LockException(Exception):
    pass


def readfile(name):
    if os.path.exists(name):
        fp = open(name)
        result = fp.read()
        fp.close()
        return result
    else:
        return ''


class LockFile(object):
    def __init__(self, name):
        self.locked = False
        self.name = name + '.lock'
        self.lock()

    def lock(self):
        if not self.locked:
            try:
                fd = os.open(
                    self.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except OSError as e:
                print(e)
                raise LockException(self.name, readfile(self.name))
            try:
                fp = os.fdopen(fd, 'w')
            except:
                os.close(fd)
                raise
            try:
                stamp = ' '.join([
                    time.asctime(),
                    os.environ['USER'],
                    socket.gethostname(),
                    str(os.getpid())
                    ]) + '\n'
                fp.write(stamp)
            finally:
                fp.close()
            read = readfile(self.name)
            if read != stamp:
                raise LockException(self.name, read)
            self.locked = True

    def __nonzero__(self):
        return self.locked

    def unlock(self):
        if self.locked:
            os.unlink(self.name)
            self.locked = False
