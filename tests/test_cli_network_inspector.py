# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest


class TestCliOciNetworkInspector(unittest.TestCase):
    """ oci-iscsi-inspector tests.
    """

    NETWORK_INSPECTOR = '/bin/oci-network-inspector'

    def setUp(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.

        Raises
        ------
        unittest.Skiptest
            If the NETWORK_INSPECTOR does not exist.
        """
        if not os.path.exists(TestCliOciNetworkInspector.NETWORK_INSPECTOR):
            raise unittest.SkipTest(
                "%s not present" % TestCliOciNetworkInspector.NETWORK_INSPECTOR)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([
                TestCliOciNetworkInspector.NETWORK_INSPECTOR, '--help'])
        except Exception, e:
            self.fail('Execution has failed: %s' % str(e))

    def test_display_info(self):
        """
        Test displaying network info

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([
                TestCliOciNetworkInspector.NETWORK_INSPECTOR])
        except Exception, e:
            self.fail('Execution has failed: %s' % str(e))
