# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest
from tools.oci_test_case import OciTestCase


class TestCliOciNetworkConfig(OciTestCase):
    """ oci-iscsi-config tests.
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
            If the NETWORK_Config does not exist.
        """
        super(TestCliOciNetworkConfig, self).setUp()
        self.oci_net_config = self.properties.get_property('oci-network-config')
        if not os.path.exists(self.oci_net_config):
            raise unittest.SkipTest("%s not present" %
                                    self.oci_net_config)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_net_config, '--help'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_show_no_check(self):
        """
        Test basic run of --show command. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_net_config, '--show', '--quiet'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))
