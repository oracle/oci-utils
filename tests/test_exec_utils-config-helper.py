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

    OCI_UTILS_CONFIG_HELPER = '/usr/libexec/oci-utils-config-helper'

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
        if not os.path.exists(TestExecConfigHelper.OCI_UTILS_CONFIG_HELPER):
            raise unittest.SkipTest(
                "%s not present" % TestExecConfigHelper.OCI_UTILS_CONFIG_HELPER)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output(
                [sys.executable, TestExecConfigHelper.OCI_UTILS_CONFIG_HELPER, '--help'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))
