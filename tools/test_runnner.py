# Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

from unittest import TextTestRunner
import sys
from .execution.store import getCommandStore


class OciUtilsTestRunner(TextTestRunner):
    """Base class for OCI util test runner
    Subclass of TextTestRunner
    """

    def __init__(self, mode):
        """Creates a new OciUtilsTestRunner
        This will replace the current subprocess.Popen implementation
        by a custom one responsible of recirding or replay execution
        """

        TextTestRunner.__init__(self)

        assert (mode in ['replay', 'record']), 'unkonwn mode'

        # if subprocess module is already imported
        # delete it first
        if 'subprocess' in sys.modules:
            del sys.modules['subprocess']

        # import the subprocess module and keep a reference on it.
        _subprocess_origin = __import__('subprocess')

        # We gonna need the real implementation to execute command and to be able
        # to use it a super-class for our own Popen impl so we keep it as
        # a  new symbol _Popen
        _subprocess_origin.__dict__['_Popen'] = _subprocess_origin.Popen
        _subprocess_origin.__all__.append('_Popen')

        # import our own Popen class
        _new_popen = __import__('snooppopen')

        # Replace the Popen class with our implementation
        if mode == 'record':
            _subprocess_origin.__dict__['Popen'] = _new_popen.RecordPopen
            # 'call' and 'check_call'  discard stdout and stderr
            # but we need to record them any way. otherwise following scenario will fail
            #    call('foo')
            #    ...
            #    check_output('foo')
            #   -> for second method call, as we already record the command, we won't
            #      execute/record it again . i.e we never have the output
            _subprocess_origin.__dict__['_call'] = _subprocess_origin.call
            _subprocess_origin.__all__.append('_call')
            _subprocess_origin.__dict__['call'] = _new_popen.call
        elif mode == 'replay':
            _subprocess_origin.__dict__['Popen'] = _new_popen.ReplayPopen


class OciUtilsTestRunnerReplay(OciUtilsTestRunner):
    """Replay OciUtilsTestRunner
    Any executed command line will be simulate and outputs will be
    fetched from command repository
    """

    def __init__(self):
        OciUtilsTestRunner.__init__(self, 'replay')


class OciUtilsTestRunnerRecord(OciUtilsTestRunner):
    """Record OciUtilsTestRunner
    Any executed command line will be recorded to command repository
    """

    def __init__(self):
        OciUtilsTestRunner.__init__(self, 'record')

    def run(self, test):
        try:
            return OciUtilsTestRunner.run(self, test)
        finally:
            getCommandStore().flush()
