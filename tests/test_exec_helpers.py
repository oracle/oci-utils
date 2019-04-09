#!/usr/bin/env python2.7

# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import unittest

from decorators import skipUnlessRoot


class TestExecHelpers(unittest.TestCase):
    """ Test around lib/oci_utils/impl/sudo_utils.py.
    """
    @skipUnlessRoot()
    def test_call(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.sudo_utils
        self.assertFalse(oci_utils.impl.sudo_utils.call(['/bin/ls', '/']))
