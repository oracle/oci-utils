# oci-utils
#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" oci_api exceptions.
"""


class OCISDKError(Exception):
    """Exception raised for various OCI API problems
    """

    def __init__(self, value):
        """
        Create a new OCISDKError instance.

        Parameters
        ----------
        value: str
            Value/error message.
        """
        assert (value is not None), 'No exception message given'
        Exception.__init__(self, value)
        self.value = value

    def __str__(self):
        """
        Get this OCISDKError representation.

        Returns
        -------
        str
            The error message.
        """
        return str(self.value)
