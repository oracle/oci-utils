# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import time
import unittest
from tools.oci_test_case import OciTestCase


os.environ['LC_ALL'] = 'en_US.UTF8'


class TestCliOciMetadata(OciTestCase):
    """ oci-metadata tests.
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
            If the metadata_cli does not exist.
        """

        super().setUp()
        self.oci_metadata_path = self.properties.get_property('oci-metadata')
        if not os.path.exists(self.oci_metadata_path):
            raise unittest.SkipTest("%s not present" % self.oci_metadata_path)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--help'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_human_readable(self):
        """
        Test displaying metadata values .

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--human-readable'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_display_json(self):
        """
        Test displaying metadata values in JSON .

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--json'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_metadata(self):
        """
        Test displaying 'instance' metadata

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--get', 'instance'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/availabilityDomain'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/faultDomain'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/compartmentId'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/displayName'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/hostname'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/id'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/image'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/metadata'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/metadata/ssh_authorized_keys'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/region'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/canonicalRegionName'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/ociAdName'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/regionInfo'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/regionInfo/realmKey'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/regionInfo/realmDomainComponent'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/regionInfo/regionKey'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/regionInfo/regionIdentifier'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/shape'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/state'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/timeCreated'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/agentConfig'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/0'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_definedtags(self):
        """
        Test get instance defined tags

        Returns
        -------
        No return value
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/definedTags'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_metadata_this_instance(self):
        """
        Test displaying 'instance' metadata

        Returns
        -------
        No return value.
        """
        try:
            this_instance_id = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/id', '--value-only', '--trim']).decode('utf-8')

            _ = subprocess.check_output([self.oci_metadata_path, '--get', 'instance', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/availabilityDomain', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/compartmentId', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/dedicated_vm_host_id', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/definedTags', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/displayName', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/freeformTags', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/id', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/imageId', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/ipxeScript', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/launchMode', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/launchOptions', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/instance_options', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/availability_config', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/state', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/metadata', '--instance-id', this_instance_id])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/time_maintenance_reboot_due', '--instance-id', this_instance_id])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_metadata_only_values(self):
        """
        Test displaying 'instance' metadata

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--get', 'instance', '--value-only'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_all_vnics(self):
        """
        Test displaying instance VNICs metadata

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--get', 'vnics', '--value-only', '--trim'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_single_key(self):
        """
        Test displaying data for single key

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/privateip', '--trim'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/0/privateip', '--trim'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/privateip', '--get', '/instance/id', '--trim'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/0/privateip', '--get', '/instance/id', '--trim'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/privateip', '--trim', '--value-only'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/0/privateip', '--trim', '--value-only'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_update_key(self):
        """
        Test update an instance metadata key

        Returns
        -------
        No return value.
        """
        try:
            this_displayname = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/displayName', '--value-only', '--trim']).decode('utf-8').strip()
            _ = subprocess.check_output([self.oci_metadata_path, '--update', 'displayName=AutoTest'])
            _ = subprocess.check_output([self.oci_metadata_path, '--update', 'displayName=%s' % this_displayname])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_instance_id_data(self):
        """
        Test metadata retrieval via instance id
        """
        try:
            instance_ocid = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/id',
                                                     '--value-only', '--trim']).decode('utf-8').strip()
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics', '--instance-id', instance_ocid])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_vnic_data(self):
        """
        Test metadata display cidr block
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/vnicid'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/vlantag'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/privateip'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/macaddr'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/subnetcidrblock'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/virtualrouterip'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCliOciMetadata)
    unittest.TextTestRunner().run(suite)
