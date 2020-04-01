# Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

from .execution.store import getCommandStore
from .execution.command import Command
import subprocess

import logging

_logger = logging.getLogger('oci-utils-tests')


def call(*popenargs, **kwargs):
    """overwrite subprocess.call method to still
    record outputs (former implementation do not call 'communicate()')
    """
    _p = subprocess.Popen(stdout=subprocess.PIPE, stderr=subprocess.PIPE, *popenargs, **kwargs)
    # this insure that we record everythhing
    _, _ = _p.communicate()
    return _p.poll()


class ReplayPopen(subprocess._Popen):
    """custom implementation of subprocess.Popen
    All executed command are replayed from information fetched in command store
    This rely on _Popen being present in subprocess module
    _Popen symbol must be a reference on real subprocess.Popen class
    """

    def __init__(self, args, **kwargs):
        """Creates a new Popen instance
        """

        # according to the way user will use this
        # i.e using 'communicate' with inout etc.
        # we may have to fetch it again . any way we need an instance
        self.command = Command(args)

        # if the command has already been recorded
        # as an execution error, get in now. stdin do not
        # change anything about identifying the commend
        _commandXML = getCommandStore().fetch(self.command.getKey())
        if _commandXML is not None:
            _execError = _commandXML.find('executionError')
            if _execError is not None:
                # raise it now
                raise OSError(int(_execError.get('code')), _execError.text)
            else:
                # we know about the command unmarshall it properly form XML
                self.command = Command.fromXMLElement(_commandXML)

        # we may need this later, kep track of them
        self.args = args
        self.kwargs = kwargs

    def communicate(self, input=None):
        """see ubprocess.Popen.communicate()
        capture out and err of excuted process
        """

        # check that we have it or not in the store
        if input:
            self.command.setInput(input)
            # input is part of the signature (i.e the key)
            # fetch it again
            _cmdXML = getCommandStore().fetch(self.command.getKey())
            if _cmdXML is not None:
                # fetch it again now that we now the input
                self.command = Command.fromXMLElement(_cmdXML)

        if self.command is not None:
            self.returncode = self.command.getExitCode()
            return (self.command.getOutput(), self.command.getErrorOutput())
        else:
            # we do not know this command trigger real execution
            return subprocess._Popen(self.args, self.kwargs).communicate(input)

    def poll(self):
        return self.command.getExitCode()

    def wait(self):
        return self.command.getExitCode()


class RecordPopen(subprocess._Popen):
    """custom implementation of subprocess.Popen
    This rely on _Popen being present in subprocess module
    _Popen symbol must be a reference on real subprocess.Popen class
    """

    def __init__(self, args, **kwargs):
        """Creates a new Popen instance
        """

        # upper class communicate call the 'wait' method
        # this end up in out implementation which flush the command
        # to the repository. So we do this even before 'communicate'
        # ends and so we grab stdout and stderr
        # use this flag to know if we have to store the command in wait
        # method or not
        self._communicateOnGoing = False

        _exc = None
        try:
            subprocess._Popen.__init__(self, args, **kwargs)
        except OSError as e:
            _exc = e

        self.command = Command(args)
        if _exc is not None:
            self.command.setExecutionError(_exc)

        if _exc is not None:
            raise _exc

    def communicate(self, input=None):
        """see ubprocess.Popen.communicate()
        capture out and err of excuted process
        """
        self._communicateOnGoing = True
        if input:
            self.command.setInput(input)
        o, e = subprocess._Popen.communicate(self, input)
        self.command.setOutput(o)
        self.command.setErrorOutput(e)
        self._communicateOnGoing = False
        return (o, e)

    def poll(self):
        """see ubprocess.Popen.poll()
        capture exit code of excuted process
        """
        retcode = subprocess._Popen.poll(self)
        self.command.setExitCode(retcode)
        self._record()
        return retcode

    def wait(self):
        """see ubprocess.Popen.wait()
        capture exit code of excuted process
        """

        retcode = subprocess._Popen.wait(self)
        self.command.setExitCode(retcode)
        if not self._communicateOnGoing:
            self._record()
        return retcode

    def _record(self):
        _ret = getCommandStore().store(self.command)
        print(_ret)
