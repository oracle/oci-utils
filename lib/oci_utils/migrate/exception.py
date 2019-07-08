#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module with oci migrate related exceptions.
"""


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
        if message is None:
            message = 'An exception occured, no further information'
        super(OciMigrateException, self).__init__(message)


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
        super(NoSuchCommand, self).__init__('Command %s not found' % command)
