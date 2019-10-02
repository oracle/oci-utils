#!/usr/bin/env python2.7

# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest


class TestCliOciIscsiConfig(unittest.TestCase):
    """ oci-iscsi-config tests.
    """

    ISCSI_CONFIG = '/bin/oci-iscsi-config'

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
        if not os.path.exists(TestCliOciIscsiConfig.ISCSI_CONFIG):
            raise unittest.SkipTest("%s not present" %
                                    TestCliOciIscsiConfig.ISCSI_CONFIG)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([TestCliOciIscsiConfig.ISCSI_CONFIG,
                                         '--help'])
        except Exception, e:
            self.fail('Execution has failed: %s' % str(e))

    def test_show_no_check(self):
        """
        Test basic run of --show command. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([TestCliOciIscsiConfig.ISCSI_CONFIG,
                                         '--show'])
        except Exception, e:
            self.fail('Execution has failed: %s' % str(e))

    def test_show_all_no_check(self):
        """
        Test basic run of --show command. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([TestCliOciIscsiConfig.ISCSI_CONFIG,
                                         '--show', '--all'])
        except Exception, e:
            self.fail('Execution has failed: %s' % str(e))
