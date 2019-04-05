#!/usr/bin/python

# Copyright (c) 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

# Common decorator functions for oci-utils unit tests

import unittest
from oci_utils.iscsiadm import __can_connect
from common import *

# skip tests that require an OCI instance if not running on an OCI instance
def skipUnlessOCI():
    if not __can_connect('169.254.169.254', 80):
        return unittest.skip("must be run on an OCI instance")
    return lambda func: func

# skip test if the user is not root
def skipUnlessRoot():
    if os.geteuid() != 0:
        return unittest.skip("must be root")
    return lambda func: func

# skip test if the OCI CLI is not installed and configured
def needsOCICLI():
    if not os.path.exists('/usr/bin/oci'):
        return unittest.skip("OCI CLI client must be installed for this test")
    try:
        instance_id = get_instance_id()
    except:
        return unittest.skip("must be run on an OCI instance")
    # now check that the oci client is configured
    (ret, out) = run_cmd(['/usr/bin/oci', 'compute', 'instance', 'get',
                          '--instance-id', get_instance_id()])
    if ret != 0:
        return unittest.skip("OCI CLI client must be configured for this test")

    return lambda func: func
