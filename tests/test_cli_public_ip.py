# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest
from tools.oci_test_case import OciTestCase


class TestCliOciPublicIp(OciTestCase):
    """ oci-public-ip tests.
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
            If the PUBLIC_IP does not exist.
        """
        super(TestCliOciPublicIp, self).setUp()
        self.oci_public_ip = self.properties.get_property('oci-public-ip')
        if not os.path.exists(self.oci_public_ip):
            raise unittest.SkipTest("%s not present" % self.oci_public_ip)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_public_ip, '--help'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get(self):
        """
        Test displaying all pulic addr
        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_public_ip, '--get', '--human-readable'])
        except subprocess.CalledProcessError as e:
            if e.returncode != 1:
                # when we cannot find the public IP , exit code is 1.
                self.fail('Execution has failed: %s' % str(e))

    def test_list_servers(self):
        """
        Test displaying STUN server
        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_public_ip, '--list-servers'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_list_all(self):
        """
        Test displaying all pulic addr
        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_public_ip, '--all', '--json'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))
