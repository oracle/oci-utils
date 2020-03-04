# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest
from tools.oci_test_case import OciTestCase


class TestCliOciNetworkInspector(OciTestCase):
    """ oci-iscsi-inspector tests.
    """

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
        super(TestCliOciNetworkInspector, self).setUp()
        self.oci_net_inspector = self.properties.get_property('oci-network-inspector')
        if not os.path.exists(self.oci_net_inspector):
            raise unittest.SkipTest("%s not present" % self.oci_net_inspector)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([
                self.oci_net_inspector, '--help'])
        except Exception as e:
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
                self.oci_net_inspector])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))
