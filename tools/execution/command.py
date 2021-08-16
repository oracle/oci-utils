# Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import xml.etree.ElementTree as ET

import hashlib
import shlex

from . import storable


class Command(storable.Storable):
    """
    Command class.
    This represent a sub process execution
    Stored or retrieved to or form the execution store
    """

    def __init__(self, args):
        """
        Create a new command

        Parameters
        ----------
        args : [str] | str
            command execution option as a list of string or a string
            When passed as string the string os split using shlex
        """

        if isinstance(args, str):
            self._arguments = shlex.split(args)
        else:
            self._arguments = args
        self._exitCode = 0
        self._in = None
        self._out = None
        self._err = None
        self._executionError = None

    @classmethod
    def fromXMLElement(cls, xmlElement):
        """
        Create a COmmand instance from XML element
        Parameter
        ---------
              xmlElement   xml.etree.ElementTree.Element
        Return
        ------
            Command a command instance
        """
        assert isinstance(xmlElement, ET.Element), 'must be xml.etree.ElementTree.Element'
        _allArgs = [xmlElement.get('exec')]
        _args = xmlElement.find('arguments')
        if _args is not None:
            for _a in _args.findall('argument'):
                _allArgs.append(_a.text)

        _newCommand = cls(_allArgs)

        _e = xmlElement.find('input')
        if _e is not None:
            _newCommand._in = _e.text

        _e = xmlElement.find('executionError')
        if _e is not None:
            _newCommand._executionError = OSError(int(_e.get('code')), _e.text)
        else:
            _e = xmlElement.find('exitCode')
            if _e is not None:
                _newCommand._exitCode = int(_e.get('value'))
            _e = xmlElement.find('error')
            if _e is not None:
                _newCommand._err = _e.text
            _e = xmlElement.find('output')
            if _e is not None:
                _newCommand._out = _e.text

        return _newCommand

    def toXMLElement(self):
        """Serialise this command as XML element

        Returns
        -------
        xml.etree.ElementTree.Element
            the serialize command
        """

        celement = ET.Element('command', {
            'key': self.getKey(),
            'exec': self._arguments[0]})

        if self._in is not None:
            _i = ET.Element('input')
            _i.text = self._in
            celement.append(_i)

        if len(self._arguments) > 1:
            _allargs = ET.Element('arguments')
            for _a in self._arguments[1:]:
                _argval = ET.Element('argument')
                _argval.text = _a
                _allargs.append(_argval)
            celement.append(_allargs)

        if self._executionError is None:
            _o = ET.Element('output')
            _o.text = self._out
            celement.append(_o)
            _e = ET.Element('error')
            _e.text = self._err
            celement.append(_e)
            celement.append(ET.Element('exitCode', {'value': str(self._exitCode)}))
        else:
            _error = ET.Element('executionError', {'code': str(self._executionError.errno)})
            _error.text = self._executionError.strerror
            celement.append(_error)

        return celement

    def getKey(self):
        """get this comamnd hash as an unique identifier

        Returns
        -------
        str
            command hash base on input and parameters
        """

        data = hashlib.md5()
        for _a in self._arguments:
            data.update(_a)
        if self._in:
            data.update(self._in)
        return data.hexdigest()

    def setExitCode(self, code):
        """Set this command  excution code

        Parameters
        ----------
        code : int
            0 to 255 execution code.
        """
        assert type(code) == int, 'wrong exit code type'
        self._exitCode = code

    def getExitCode(self):
        return self._exitCode

    def setOutput(self, output):
        """Set the command execution stdout

        Parameters
        ----------
        output : str
            command execution output
        """
        self._out = output

    def getOutput(self):
        """get the command execution stdout

        Return
        ------
          str
            command execution output
        """
        return self._out

    def setInput(self, input):
        """Set the command execution input

        Parameters
        ----------
        input : str
            command execution input
        """
        self._in = input

    def setErrorOutput(self, error):
        """Set the command execution stderr

        Parameters
        ----------
        output : str
            command execution output
        """
        self._err = error

    def getErrorOutput(self):
        """Get the command execution stderr

        Return
        ------
          str
            command execution error
        """
        return self._err

    def setExecutionError(self, OSErrorInstance):
        """set the execution error
        When a command failed to execute,Popen raise an OSError exception
        We keep track of raised OSError
        """
        self._executionError = OSErrorInstance

    def getExecutionError(self):
        """Get the execution error
        return
        ------
            OSError the error or None if execution hasn't failed
        """
        return self._executionError

    def __eq__(self, other):
        _o = other
        if isinstance(other, ET.Element):
            _o = Command.fromXMLElement(other)

        if not isinstance(_o, Command):
            return False

        if self.getKey() != _o.getKey():
            # this test equality of args and input
            return False
        if self._out != _o._out:
            return False
        if self._err != _o._err:
            return False
        if self._exitCode != _o._exitCode:
            return False

        if self._executionError is not None:
            if _o._executionError is None:
                return False
            if self._executionError.errno != _o._executionError.errno:
                return False
            if self._executionError.strerror != _o._executionError.strerror:
                return False
        else:
            if _o._executionError is not None:
                return False
        return True
