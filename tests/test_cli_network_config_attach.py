# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import re
import subprocess
import time
import unittest
import uuid
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

    def test_attach_detach_vnic(self):
        """
        Test attach and detach a vnic.

        Returns
        -------
            No return value.
        """
        try:
            create_data = subprocess.check_output( [self.oci_net_config, 'attach-vnic', '--name', self.vnic_name]).decode('utf-8')
            print(create_data)
            self.assertIn('Creating', create_data, 'attach vnic failed')
            time.sleep(self.waittime)
            vn_ocid = self._get_vnic_ocid(self.vnic_name)
            new_ipv4 = _get_ip_from_response(create_data)[0]
            detach_data = subprocess.check_output([self.oci_net_config, 'detach-vnic', '--ocid', vn_ocid]).decode('utf-8')
            self.assertIn('is detached', detach_data, '')
            time.sleep(self.waittime)
        except Exception as e:
            self.fail('Execution oci-network-config attach detach has failed: %s' % str(e))
    
    
    def test_add_remove_secondary_ip_0(self):
        """
        Test add secondary ip to a vnic with mininal options.
        
        Returns
        -------
            No return value.
        """
        try:
            self.assertIn('Creating', subprocess.check_output([self.oci_net_config, 'attach-vnic', '--name', self.vnic_name]).decode('utf-8'), 'attach vnic failed')
            time.sleep(self.waittime)
            vn_ocid = self._get_vnic_ocid(self.vnic_name)
            response = subprocess.check_output([self.oci_net_config, 'add-secondary-addr','--ocid', vn_ocid]).decode('utf-8').splitlines()
            self.assertIn('Provisioning secondary private', response[0], 'adding secondary ip failed')
            new_ip = _get_ip_from_response(response[0])
            time.sleep(self.waittime)
            response = subprocess.check_output([self.oci_net_config, 'remove-secondary-addr', '--ip-address', new_ip]).decode('utf-8').splitlines()
            self.assertIn('Deconfigure secondary private', response[0], 'remove secondary ip failed')
            time.sleep(self.waittime)
            detach_data = subprocess.check_output([self.oci_net_config, 'detach-vnic', '--ocid', vn_ocid]).decode('utf-8')
            self.assertIn('is detached', detach_data, '')
            time.sleep(self.waittime)

        except Exception as e:
            self.fail('Execution oci-network-config attach detach has failed: %s' % str(e))

    def test_add_remove_secondary_ip_1(self):
        """
        Test adding and removing secondary ip address to vnic.

        Returns
        -------
            No return value.
        """
        try:
            self.assertIn('Creating', subprocess.check_output([self.oci_net_config, 'attach-vnic', '--name', self.vnic_name]).decode('utf-8'), 'attach vnic failed')
            time.sleep(self.waittime)
            vn_ocid = self._get_vnic_ocid(self.vnic_name)
            vn_pip = self._get_vnic_private_ip(self.vnic_name)
            new_ip = str(ip_address(vn_pip) + 1)
            print(new_ip)
            self.assertIn('Provisioning secondary private IP', subprocess.check_output([self.oci_net_config, 'add-secondary-addr', '--ocid', vn_ocid, '--ip-address', new_ip]).decode('utf-8'), 'adding secondary ip failed')
            time.sleep(self.waittime)
            self.assertIn('Deconfigure secondary private IP', subprocess.check_output([self.oci_net_config, 'remove-secondary-addr', '--ip-address', new_ip]).decode('utf-8'), 'remove secondary ip failed')
            time.sleep(self.waittime)
            detach_data = subprocess.check_output([self.oci_net_config, 'detach-vnic', '--ocid', vn_ocid]).decode('utf-8')
            self.assertIn('is detached', detach_data, '')
            time.sleep(self.waittime)
        except Exception as e:
            self.fail('Execution oci-network-config attach detach has  failed: %s' % str(e))

    def test_attach_detach_vnic_comp(self):
        """
        Test attach and detach a vnic in 0.11 compatibility.

        Returns
        -------
            No return value.
        """
        try:
            create_data = subprocess.check_output([self.oci_net_config, '--create-vnic']).decode('utf-8')
            self.assertIn('Creating', create_data, 'attach vnic failed')
            new_ipv4 = _get_ip_from_response(create_data)[0]
            time.sleep(self.waittime)
            detach_data = subprocess.check_output([self.oci_net_config, '--detach-vnic', new_ipv4]).decode('utf-8')
            self.assertIn('is detached', detach_data, '')
            time.sleep(self.waittime)
        except Exception as e:
            self.fail('Execution oci-network-config attach detach in 0.11 compatibility mode has failed: %s' % str(e))

    def test_attach_add_del_ip_detach_vnic_comp(self):
        """
        Test attach and detach a vnic in 0.11 compatibility.

        Returns
        -------
            No return value.
        """
        try:
            create_data = subprocess.check_output([self.oci_net_config, '--create-vnic', '--private-ip', self.new_ip, '--vnic-name', self.vnic_name]).decode('utf-8')
            self.assertIn('Creating', create_data, 'attach vnic failed')
            new_ipv4 = _get_ip_from_response(create_data)[0]
            time.sleep(self.waittime)
            new_oci = self._get_vnic_ocid(self.vnic_name)
            add_ip_data = subprocess.check_output([self.oci_net_config, '--add-private-ip', '--private-ip', self.extra_ip, '--vnic', new_oci]).decode('utf-8')
            self.assertIn('Provisioning secondary private IP', add_ip_data, 'add private ip failed.')
            time.sleep(self.waittime)
            del_ip_data = subprocess.check_output([self.oci_net_config, '--del-private-ip', self.extra_ip]).decode('utf-8')
            self.assertIn('Deconfigure secondary private IP', del_ip_data, 'remove private ip failed')
            time.sleep(self.waittime)
            detach_data =subprocess.check_output([self.oci_net_config, '--detach-vnic', new_ipv4]).decode('utf-8')
            self.assertIn('is detached', detach_data, '')
            time.sleep(self.waittime)
        except Exception as e:
            self.fail('Execution oci-network-config attach detach in 0.11 compatibility mode has failed: %s' % str(e))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCliOciNetworkConfig)
    unittest.TextTestRunner().run(suite)
