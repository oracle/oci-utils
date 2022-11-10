# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import time
import unittest
from tools.oci_test_case import OciTestCase


os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'

instance_key_set = ('availabilitydomain',
                    'faultdomain',
                    'compartmentid',
                    'displayname',
                    'hostname',
                    'id',
                    'image',
                    'metadata',
                    'region',
                    'canonicalregionname',
                    'ociadname',
                    'regioninfo',
                    'shape',
                    'shapeconfig',
                    'state',
                    'timecreated',
                    'agentconfig',
                    'definedtags',
                    )

metadata_key_set = ('ssh_authorized_keys',
                    )

regioninfo_key_set = ('realmkey',
                      'realmdomaincomponent',
                      'regionkey',
                      'regionidentifier'
                      )

shape_key_set = ('ocpus',
                 'memoryingbs',
                 'networkingbandwidthingbps',
                 'maxvnicattachments',
                 )

agentconfig_key_set = ('monitoringdisabled',
                       'managementdisabled',
                       'allpluginsdisabled',
                       )
pluginsconfig_key_set = ('name',
                         'desiredstate',
                        )

definedtags_key_set = ('oracle-tags',
                      )

oracletags_key_set = ('createdby',
                      'createdon',
                     )

vnic_key_set = ('vnicid',
                'privateip',
                'vlantag',
                'macaddr',
                'virtualrouterip',
                'subnetcidrblock'
                )

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

    def test_get_metadata_instance(self):
        """
        Test displaying instance metadata.

        Returns
        -------
        No return value.
        """
        try:
            key_data = subprocess.check_output([self.oci_metadata_path, '--get', 'instance'])
            print(key_data.decode('utf-8'))
            self.assertIsNotNone(key_data)
        except Exception as e:
                self.fail('Execution has failed: %s' % str(e))

        for key in instance_key_set \
                   + regioninfo_key_set \
                   + shape_key_set \
                   + agentconfig_key_set \
                   + definedtags_key_set \
                   + metadata_key_set \
                   + pluginsconfig_key_set :
#                   + oracletags_key_set :
            with self.subTest(key=key):
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', key])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', key, '--value-only'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', key, '--human-readable'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', key, '--json'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', key, '--trim'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))

    def test_get_metadata_instance_keys(self):
        """
        Test displaying instance metadata.

        Returns
        -------
        No return value.
        """
        for key in instance_key_set:
            with self.subTest(key=key):
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/%s' % key])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/%s' % key, '--value-only'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/%s' %  key, '--human-readable'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/%s' %  key, '--json'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/%s' % key, '--trim'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))

    def test_get_metadata_instance_regioninfo_keys(self):
        """
        Test displaying instance metadata.

        Returns
        -------
        No return value.
        """

        for key in regioninfo_key_set:
            with self.subTest(key=key):
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/regioninfo/%s' % key])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/regioninfo/%s' % key, '--value-only'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/regioninfo/%s' %  key, '--human-readable'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/regioninfo/%s' %  key, '--json'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/regioninfo/%s' % key, '--trim'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))

    def test_get_metadata_instance_shapeconfig_keys(self):
        """
        Test displaying instance metadata.

        Returns
        -------
        No return value.
        """

        for key in shape_key_set:
            with self.subTest(key=key):
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/shapeconfig/%s' % key])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/shapeconfig/%s' % key, '--value-only'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/shapeconfig/%s' %  key, '--human-readable'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/shapeconfig/%s' %  key, '--json'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/shapeconfig/%s' % key, '--trim'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))

    def test_get_metadata_instance_agentconfig_keys(self):
        """
        Test displaying instance metadata.

        Returns
        -------
        No return value.
        """

        for key in agentconfig_key_set:
            with self.subTest(key=key):
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/agentconfig/%s' % key])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/agentconfig/%s' % key, '--value-only'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/agentconfig/%s' %  key, '--human-readable'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/agentconfig/%s' %  key, '--json'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/agentconfig/%s' % key, '--trim'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))

    def test_get_metadata_instance_definedtags_keys(self):
        """
        Test displaying instance metadata.

        Returns
        -------
        No return value.
        """
        for key in definedtags_key_set:
            with self.subTest(key=key):
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/definedtags/%s' % key])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/definedtags/%s' % key, '--value-only'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/definedtags/%s' %  key, '--human-readable'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/definedtags/%s' %  key, '--json'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/definedtags/%s' % key, '--trim'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))


    def test_get_metadata_vnic(self):
        """
        Test displaying instance metadata.

        Returns
        -------
        No return value.
        """
        try:
            key_data = subprocess.check_output([self.oci_metadata_path, '--get', 'vnics'])
            print(key_data.decode('utf-8'))
            self.assertIsNotNone(key_data)
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

        for key in vnic_key_set:
            with self.subTest(key=key):
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', key])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', key, '--value-only'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', key, '--human-readable'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', key, '--json'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', key, '--trim'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))

    def test_get_metadata_vnic_keys(self):
        """
        Test displaying instance metadata.

        Returns
        -------
        No return value.
        """
        for key in vnic_key_set:
            with self.subTest(key=key):
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/%s' % key])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/%s' % key, '--value-only'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/%s' % key, '--human-readable'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/%s' % key, '--json'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
                except Exception as e:
                    self.fail('Execution has failed: %s' % str(e))
                try:
                    key_data = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/%s' % key, '--trim'])
                    print(key_data.decode('utf-8'))
                    self.assertIsNotNone(key_data)
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
            this_instance_id = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/id', '--value-only', '--trim']).decode('utf-8').strip()

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
            time.sleep(120)
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
