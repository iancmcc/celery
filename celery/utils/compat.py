# -*- coding: utf-8 -*-
"""
    celery.utils.compat
    ~~~~~~~~~~~~~~~~~~~

    Backward compatible implementations of features
    only available in newer Python versions.

    :copyright: (c) 2009 - 2012 by Ask Solem.
    :license: BSD, see LICENSE for more details.

"""
from __future__ import absolute_import

############## py3k #########################################################
import sys
is_py3k = sys.version_info[0] == 3

try:
    reload = reload                     # noqa
except NameError:
    from imp import reload              # noqa

try:
    from UserList import UserList       # noqa
except ImportError:
    from collections import UserList    # noqa

try:
    from UserDict import UserDict       # noqa
except ImportError:
    from collections import UserDict    # noqa

if is_py3k:
    from io import StringIO, BytesIO
    from .encoding import bytes_to_str

    class WhateverIO(StringIO):

        def write(self, data):
            StringIO.write(self, bytes_to_str(data))
else:
    from StringIO import StringIO       # noqa
    BytesIO = WhateverIO = StringIO     # noqa


############## collections.OrderedDict ######################################
try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict  # noqa

############## itertools.zip_longest #######################################

try:
    from itertools import izip_longest as zip_longest
except ImportError:
    import itertools

    def zip_longest(*args, **kwds):  # noqa
        fillvalue = kwds.get("fillvalue")

        def sentinel(counter=([fillvalue] * (len(args) - 1)).pop):
            yield counter()     # yields the fillvalue, or raises IndexError

        fillers = itertools.repeat(fillvalue)
        iters = [itertools.chain(it, sentinel(), fillers)
                    for it in args]
        try:
            for tup in itertools.izip(*iters):
                yield tup
        except IndexError:
            pass


############## itertools.chain.from_iterable ################################
from itertools import chain


def _compat_chain_from_iterable(iterables):
    for it in iterables:
        for element in it:
            yield element

try:
    chain_from_iterable = getattr(chain, "from_iterable")
except AttributeError:
    chain_from_iterable = _compat_chain_from_iterable


############## logging.handlers.WatchedFileHandler ##########################
import logging
import os
from stat import ST_DEV, ST_INO
import platform as _platform

if _platform.system() == "Windows":
    #since windows doesn't go with WatchedFileHandler use FileHandler instead
    WatchedFileHandler = logging.FileHandler
else:
    try:
        from logging.handlers import WatchedFileHandler
    except ImportError:
        class WatchedFileHandler(logging.FileHandler):  # noqa
            """
            A handler for logging to a file, which watches the file
            to see if it has changed while in use. This can happen because of
            usage of programs such as newsyslog and logrotate which perform
            log file rotation. This handler, intended for use under Unix,
            watches the file to see if it has changed since the last emit.
            (A file has changed if its device or inode have changed.)
            If it has changed, the old file stream is closed, and the file
            opened to get a new stream.

            This handler is not appropriate for use under Windows, because
            under Windows open files cannot be moved or renamed - logging
            opens the files with exclusive locks - and so there is no need
            for such a handler. Furthermore, ST_INO is not supported under
            Windows; stat always returns zero for this value.

            This handler is based on a suggestion and patch by Chad J.
            Schroeder.
            """
            def __init__(self, *args, **kwargs):
                logging.FileHandler.__init__(self, *args, **kwargs)

                if not os.path.exists(self.baseFilename):
                    self.dev, self.ino = -1, -1
                else:
                    stat = os.stat(self.baseFilename)
                    self.dev, self.ino = stat[ST_DEV], stat[ST_INO]

            def emit(self, record):
                """
                Emit a record.

                First check if the underlying file has changed, and if it
                has, close the old stream and reopen the file to get the
                current stream.
                """
                if not os.path.exists(self.baseFilename):
                    stat = None
                    changed = 1
                else:
                    stat = os.stat(self.baseFilename)
                    changed = ((stat[ST_DEV] != self.dev) or
                               (stat[ST_INO] != self.ino))
                if changed and self.stream is not None:
                    self.stream.flush()
                    self.stream.close()
                    self.stream = self._open()
                    if stat is None:
                        stat = os.stat(self.baseFilename)
                    self.dev, self.ino = stat[ST_DEV], stat[ST_INO]
                logging.FileHandler.emit(self, record)
