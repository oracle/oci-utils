# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'

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
        self.oci_metadata_path = self.properties.get_property('oci-metadata')

    def _get_compartment_id(self):
        """
        Get the compartment ocid.

        Returns
        -------
            str: the compartment ocid.
        """
        return subprocess.check_output([self.oci_metadata_path, '--get', '/instance/compartmentId', '--value-only', '--trim']).decode('utf-8')

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_net_inspector, '--help'])
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
            _ = subprocess.check_output([self.oci_net_inspector])
        except subprocess.CalledProcessError as e:
            if e.returncode != 1:
                self.fail('Execution has failed: %s' % str(e))

    def test_display_info_compartment(self):
        """
        Test displaying network in this compartment.

        Parameters
        ----------
        compartment_id: ocid of a compartment

        Returns
        -------
            No return value
        """
        comp_id = self._get_compartment_id()
        try:
            _ = subprocess.check_output([self.oci_net_inspector, '--compartment', comp_id])
        except subprocess.CalledProcessError as e:
            if e.returncode != 1:
                self.fail('Execution has failed: %s' % str(e))

#
# TODO
# test network_inspector --vnc <vcn ocid>


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCliOciNetworkInspector)
    unittest.TextTestRunner().run(suite)
