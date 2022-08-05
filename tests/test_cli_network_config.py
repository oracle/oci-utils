# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import re
import subprocess
import time
import uuid
import unittest
from ipaddress import ip_address

import oci_utils.oci_api
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'


def _get_ip_from_response(response):
    """
    Filter ipv4 addresses from string.

    Parameters
    ----------
    response: str
        String with ipv4 addresses.

    Returns
    -------
        list: list with ip4 addresses.
    """
    ip = re.findall(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b', response)
    return ip


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
        super().setUp()
        # super(TestCliOciNetworkConfig, self).setUp()
        self.oci_net_config = self.properties.get_property('oci-network-config')
        if not os.path.exists(self.oci_net_config):
            raise unittest.SkipTest("%s not present" % self.oci_net_config)
        self._session = None
        self._instance = None
        self._allvnics = None
        try:
            self.waittime = int(self.properties.get_property('waittime'))
        except Exception:
            self.waittime = 20
        try:
            self.vnic_name = self.properties.get_property('network-name-prefix') + uuid.uuid4().hex[:8]
        except Exception:
            self.vnic_name = 'some_vnic_display_name'
        try:
            self.new_ip = self.properties.get_property('new_ip')
            self.extra_ip = self.properties.get_property('extra_ip')
        except Exception:
            self.new_ip = '100.110.100.101'
            self.extra_ip = '100.110.100.100'

    def _get_vnic(self):
        """
        Get the list of all vcn's for this instance.

        Returns
        -------
            list of OCIVCN
        """
        if self._session is None:
            self._session = oci_utils.oci_api.OCISession()
            self._instance = self._session.this_instance()
            self._allvnics = self._instance.all_vnics()
        return self._allvnics

    def _get_vnic_ocid(self, name):
        """
        Get the ocid for the vcn with display name name.

        Parameters
        ----------
        name: str
            the display name of the vcn

        Returns
        -------
            str: the ocid.
        """
        all_vnics = self._get_vnic()
        for vn in all_vnics:
            if vn.get_display_name() == name:
                vn_ocid = vn.get_ocid()
                break
        return vn_ocid

    def _get_vnic_private_ip(self, name):
        """
        Get the private ip for the vcn with display name name.

        Parameters
        ----------
        name: str
            the private ip of the vcn

        Returns
        -------
            str: the ocid.
        """
        all_vnics = self._get_vnic()
        for vn in all_vnics:
            if vn.get_display_name() == name:
                vn_pip = vn.get_private_ip()
                break
        return vn_pip

    def test_display_help_comp(self):
        """
        Test displaying help compatibility. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_net_config, '--help'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_net_config, 'usage'])
            _ = subprocess.check_output([self.oci_net_config, 'usage', '--help'])
            _ = subprocess.check_output([self.oci_net_config, 'show', '--help'])
            _ = subprocess.check_output([self.oci_net_config, 'show-vnics', '--help'])
            _ = subprocess.check_output([self.oci_net_config, 'show-vnics-all', '--help'])
            _ = subprocess.check_output([self.oci_net_config, 'show-vcns', '--help'])
            _ = subprocess.check_output([self.oci_net_config, 'show-subnets', '--help'])
            _ = subprocess.check_output([self.oci_net_config, 'configure', '--help'])
            _ = subprocess.check_output([self.oci_net_config, 'unconfigure', '--help'])
            _ = subprocess.check_output([self.oci_net_config, 'attach-vnic', '--help'])
            _ = subprocess.check_output([self.oci_net_config, 'detach-vnic', '--help'])
            _ = subprocess.check_output([self.oci_net_config, 'add-secondary-addr', '--help'])
            _ = subprocess.check_output([self.oci_net_config, 'remove-secondary-addr', '--help'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_show_no_check_comp(self):
        """
        Test basic run of --show/show command compatibility. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            print(subprocess.check_output([self.oci_net_config, '--show']).decode('utf-8'))
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_show_no_check(self):
        """
        Test basic run of --show/show command. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            print(subprocess.check_output([self.oci_net_config, 'show']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show', '--details']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show', '--details', '--output-mode', 'parsable']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show', '--details', '--output-mode', 'table']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show', '--details', '--output-mode', 'json']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show', '--details', '--output-mode', 'text']).decode('utf-8'))
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_show_vcns_no_check(self):
        """
        Test basic run of show-vcns command. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            print(subprocess.check_output([self.oci_net_config, 'show-vcns']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show-vcns', '--details']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show-vcns', '--details', '--output-mode', 'parsable']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show-vcns', '--details', '--output-mode', 'table']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show-vcns', '--details', '--output-mode', 'json']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show-vcns', '--details', '--output-mode', 'text']).decode('utf-8'))

        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_show_subnets_no_check(self):
        """
        Test basic run of show-subnets command. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            print(subprocess.check_output([self.oci_net_config, 'show-subnets']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show-subnets', '--details']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show-subnets', '--details', '--output-mode', 'parsable']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show-subnets', '--details', '--output-mode', 'table']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show-subnets', '--details', '--output-mode', 'json']).decode('utf-8'))
            print(subprocess.check_output([self.oci_net_config, 'show-subnets', '--details', '--output-mode', 'text']).decode('utf-8'))

        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))


    def test_show_vnics_no_check(self):
        """
        Test basic run of show-vnic command. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics', '--details']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics', '--details', '--output-mode', 'parsable']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics', '--details', '--output-mode', 'table']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics', '--details', '--output-mode', 'json']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics', '--details', '--output-mode', 'text']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics', '--ocid', self._get_vnic()[0].get_ocid(), '--details']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics', '--name', self._get_vnic()[0].get_display_name(), '--details']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics', '--ip-address', self._get_vnic()[0].get_private_ip(), '--details']).decode('utf-8'))
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_show_vnics_all_no_check(self):
        """
        Test basic run of show-vnic command. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics-all']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics-all']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics-all', '--output-mode', 'parsable']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics-all', '--output-mode', 'table']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics-all', '--output-mode', 'json']).decode('utf-8'))
            print(subprocess.check_output(
                [self.oci_net_config, 'show-vnics-all', '--output-mode', 'text']).decode('utf-8'))
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCliOciNetworkConfig)
    unittest.TextTestRunner().run(suite)
