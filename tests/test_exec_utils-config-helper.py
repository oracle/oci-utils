# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

import os
import sys
import subprocess
import unittest
from tools.oci_test_case import OciTestCase


class TestExecConfigHelper(OciTestCase):
    """ oci-utils-config-helper tests.
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
            If the OCI_UTILS_CONFIG_HELPER does not exist.
        """
        super(TestExecConfigHelper, self).setUp()
        self.oci_config_helper = self.properties.get_property('oci-utils-config-helper')
        if not os.path.exists(self.oci_config_helper):
            raise unittest.SkipTest("%s not present" % self.oci_config_helper)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_config_helper])
        except subprocess.CalledProcessError as e:
            if e.returncode != 1:
                self.fail('Execution has failed: %s' % str(e))
