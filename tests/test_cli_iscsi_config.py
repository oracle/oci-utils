# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest
from tools.oci_test_case import OciTestCase


class TestCliOciIscsiConfig(OciTestCase):
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
        unittest.SkipTest
            If the ISCSI_CONFIG file does not exist.
        """
        super(TestCliOciIscsiConfig, self).setUp()
        self.iscsi_config_path = self.properties.get_property('oci-iscsi-config-path')
        if not os.path.exists(self.iscsi_config_path):
            raise unittest.SkipTest("%s not present" %
                                    self.iscsi_config_path)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.iscsi_config_path,
                                         '--help'])
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
            _ = subprocess.check_output([self.iscsi_config_path,
                                         '--show'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_show_all_no_check(self):
        """
        Test basic run of --show command. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.iscsi_config_path,
                                         '--show', '--all'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))
