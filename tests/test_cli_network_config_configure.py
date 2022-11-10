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
from pprint import pformat

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


class TestCliOciNetworkConfigConfigure(OciTestCase):
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

    def test_configure_comp(self):
        """
        Test basic run of configure command in compatibility mode. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            create_data = subprocess.check_output([self.oci_net_config, '--create-vnic']).decode('utf-8').splitlines()
            print(create_data[0])
            self.assertIn('Creating', create_data[0], 'attach vnic failed')
            new_ipv4 = _get_ip_from_response(create_data[0])[0]
            print(new_ipv4)
            time.sleep(self.waittime)
            deconfig_data = subprocess.check_output([self.oci_net_config, '--deconfigure']).decode('utf-8').splitlines()
            print(deconfig_data)
            time.sleep(self.waittime)
            config_data = subprocess.check_output([self.oci_net_config, '--configure']).decode('utf-8').splitlines()
            print(config_data)
            time.sleep(self.waittime)
            exclude_output = subprocess.check_output([self.oci_net_config, '--configure', '-X', new_ipv4]).decode('utf-8').splitlines()
            print(exclude_output)
            include_output = subprocess.check_output([self.oci_net_config, '--configure', '-I', new_ipv4]).decode('utf-8').splitlines()
            print(include_output)
            delete_data = subprocess.check_output([self.oci_net_config, '--detach-vnic', new_ipv4]).decode('utf-8').splitlines()
            print(delete_data[0])
            detach_data = subprocess.check_output([self.oci_net_config, '--show']).decode('utf-8').splitlines()
            self.assertNotIn(new_ipv4, detach_data[0], 'detach vnic failed')
        except Exception as e:
            self.fail('Execution oci-network-config configure in compatibility mode has failed: %s' % str(e))

    def test_configure(self):
        """
        Test basic run of configure command. We do not check out.

        Returns

            No return value.
        """
        try:
            create_data = subprocess.check_output([self.oci_net_config, 'attach-vnic', '--name', self.vnic_name]).decode('utf-8').splitlines()
            print(create_data)
            self.assertIn('Creating', create_data[0], 'attach vnic failed')
            time.sleep(self.waittime)
            vn_ocid = self._get_vnic_ocid(self.vnic_name)
            print(vn_ocid)
            new_ipv4 = _get_ip_from_response(create_data[0])[0]
            print(new_ipv4)
            print(subprocess.check_output([self.oci_net_config, 'show']).decode('utf-8').splitlines())
            config_output = subprocess.check_output([self.oci_net_config, 'configure']).decode('utf-8').splitlines()
            print(config_output[0])
            self.assertNotIn('ADD', config_output, 'configuration failed')
            time.sleep(self.waittime)
            print(subprocess.check_output([self.oci_net_config, 'show']).decode('utf-8').splitlines())
            unconfig_output = subprocess.check_output([self.oci_net_config, 'unconfigure']).decode('utf-8').splitlines()
            print(pformat(unconfig_output, indent=4))
            show_output = subprocess.check_output([self.oci_net_config, 'show']).decode('utf-8')
            print(pformat(show_output.splitlines(), indent=4))
            self.assertIn('ADD', show_output, 'un-configuration failed')
            print(new_ipv4)
            exclude_output = subprocess.check_output([self.oci_net_config, 'configure', '--exclude', new_ipv4]).decode('utf-8').splitlines()
            print(pformat(exclude_output, indent=4))
            time.sleep(self.waittime)
            show_output = subprocess.check_output([self.oci_net_config, 'show']).decode('utf-8')
            print(pformat(show_output.splitlines(), indent=4))
            self.assertIn('EXCL', show_output, 'Exclusion of %s failed' % new_ipv4)
            include_output = subprocess.check_output([self.oci_net_config, 'configure', '--include', new_ipv4]).decode('utf-8').splitlines()
            print(pformat(include_output, indent=4))
            time.sleep(self.waittime)
            show_output = subprocess.check_output([self.oci_net_config, 'show']).decode('utf-8')
            print(pformat(show_output.splitlines(), indent=4))
            # self.assertNotIn('EXCL', show_output, 'Exclusion of %s failed' % new_ipv4)
            delete_data = subprocess.check_output([self.oci_net_config, 'detach-vnic', '--ocid', vn_ocid]).decode('utf-8').splitlines()
            print(pformat(delete_data, indent=4))
        except Exception as e:
            self.fail('Execution oci-network-config configure has failed: %s' % str(e))

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCliOciNetworkConfigConfigure)
    unittest.TextTestRunner().run(suite)

