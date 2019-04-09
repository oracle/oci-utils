#!/usr/bin/env python2.7

# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest


class TestCliOciPublicIp(unittest.TestCase):
    """ oci-public-ip tests.
    """

    PUBLIC_IP = '/bin/oci-public-ip'

    def setUp(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.

        Raises
        ------
        unittest.Skiptest
            If the PUBLIC_IP does not exist.
        """
        if not os.path.exists(TestCliOciPublicIp.PUBLIC_IP):
            raise unittest.SkipTest("%s not present" %
                                    TestCliOciPublicIp.PUBLIC_IP)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([TestCliOciPublicIp.PUBLIC_IP,
                                         '--help'])
        except Exception, e:
            self.fail('Execution has failed: %s' % str(e))
