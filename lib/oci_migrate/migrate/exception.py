# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module with oci migrate related exceptions.
"""
import sys


class OciMigrateException(Exception):
    """ Exceptions for the Image Migrate to OCI context.
    """
    __args = None

    def __init__(self, message=None):
        """
        Initialisation of the Oci Migrate Exception.

        Parameters
        ----------
        message: str
            The exception message.
        """
        self.message = message
        assert (self.message is not None), 'No exception message given'

        if self.message is None:
            self.message = 'An exception occurred, no further information'

    def __str__(self):
        """
        Get this OCISDKError representation.

        Returns
        -------
        str
            The error message.
        """
        return str(self.message)

class NoSuchCommand(OciMigrateException):
    """ Exception for command not found.
    """
    def __init__(self, command):
        """
        Initialisation of the No Such Command' exception.

        Parameters
        ----------
        command: str
            The missing command, exec or script.
        """
        self.command = command
        assert (self.command is not None), 'No command given'


    def __str__(self):
        """
        Get this OCISDKError representation.

        Returns
        -------
        str
            The error message.
        """

        return str(self.message)
