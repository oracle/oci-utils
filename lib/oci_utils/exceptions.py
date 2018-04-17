#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

"""
oci_api exceptions
"""

class OCISDKError(Exception):
    """
    Exception raised for various OCI API problems
    """
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

