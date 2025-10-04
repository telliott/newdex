#!/usr/bin/python
'''

Routines to ship out error logs

'''


import email.mime.application
import email.mime.multipart
import email.mime.text
import logging
import os
import subprocess
import sys
import traceback

from mitsfs.util import utils
from io import open


__all__ = ['handle_exception']


def handle_exception(context, exc_info):
    '''
    Print the traceback, log the exception.
    If we have email logging on, email the logs and exception
    '''
    log = logging.getLogger('mitsfs.error')
    log.error('%s', context, exc_info=exc_info)
    # Flush the log file so we can get exception
    for handler_ref in logging._handlerList:
        handle = handler_ref()
        if handle:
            handle.flush()

    type_, value_, traceback_ = exc_info
    traceback.print_exception(type_, value_, traceback_)

    # We want to know if this is development or production
    email = os.environ.get('MITSFS_EMAIL_DEBUG')
    if email:
        send_error_email(
            email, context, sys.argv[0] or 'python',
            type_.__name__ + ':' + str(value_),
            '\n'.join(traceback.format_exception(type_, value_, traceback_)))


def send_error_email(send_to, context, program, exception, traceback_str):
    username = os.getlogin()
    subject = "[%s error] %s - %s" % (
        program, username, exception)

    text = "program: %s\n" % program
    text += "user: %s\n" % username
    text += "context: %s\n" % context
    text += "traceback:\n%s" % traceback_str

    msg = email.mime.multipart.MIMEMultipart()
    msg['To'] = send_to
    msg['Subject'] = subject
    msg.attach(email.mime.text.MIMEText(text))

    for log_file in utils.get_logfiles():
        with open(log_file, "rb") as f:
            name = os.path.basename(log_file)
            part = email.mime.application.MIMEApplication(f.read(), Name=name)
            part['Content-Disposition'] = 'attachment; filename="%s"' % name
            msg.attach(part)

    sm = subprocess.Popen(
        ['/usr/lib/sendmail', send_to], stdin=subprocess.PIPE)
    sm.stdin.write(msg.as_string())
    sm.stdin.close()
    sm.wait()
