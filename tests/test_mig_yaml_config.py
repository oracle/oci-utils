# Copyright (c) 2020, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import unittest
from oci_utils.migrate import migrate_tools

from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'


class TestYamlConfig(OciTestCase):
    """ Test yaml config ufle
    """
    def setUp(self):
        super().setUp()
        self.oci_migrate_image_import_path = self.properties.get_property('oci-image-migrate-import')
        if not os.path.exists(self.oci_migrate_image_import_path):
            raise unittest.SkipTest("%s not present" %
                                    self.oci_migrate_image_import_path)

    def test_read_single_value(self):
        """
        Test read a single value from the config file.

        Returns
        -------
            No return value.
        """
        mig_single_values = ['dummy_format_key',
                             'ociconfigfile',
                             'lc_all',
                             'result_filepath',
                             'default_interfaces',
                             'default_netplan',
                             'default_nwmconfig',
                             'default_nwconnections',
                             'default_systemd_file',
                             'cloudconfig_file',
                             'ol_os_oracle_cloud_agent_base',
                             'ol_os_oracle_cloud_agent_store',
                             'oracle_cloud_agent_doc',
                             'ol_os_oci_region_script',
                             'ubuntu_os_snap_install_script',
                             'reinitialise_cloud_init_script']
        for mig_single_value in mig_single_values:
            self.assertIsNotNone(migrate_tools.get_config_data(mig_single_value))

    def test_read_list(self):
        """
        Test read list.

        Returns
        -------
            No return value.
        """
        mig_list_values = ['filesystem_types',
                           'partition_to_skip',
                           'valid_boot_types',
                           'essential_dir_list',
                           'default_ifcfg_config',
                           'default_interfaces_config',
                           'default_nwm_conf_file',
                           'default_systemd',
                           'default_systemd_config',
                           'valid_os',
                           'ol_os_packages_to_install',
                           'ol_os_for_cloud_agent',
                           'ol_os_oci_region_bash',
                           'ubuntu_os_packages_to_install_apt',
                           'ubuntu_os_packages_to_install_snap',
                           'ubuntu_os_snapd_bash',
                           'reinitialise_cloud_init']
        for mig_list in mig_list_values:
            test_res = migrate_tools.get_config_data(mig_list)
            self.assertIsNotNone(test_res)
            self.assertIsInstance(test_res, list)

    def test_read_dict(self):
        """
        Test read a dict.

        Returns
        -------
            No return value.
        """
        mig_dict_values = ['helpers_list',
                           'partition_types',
                           'ol_version_id_dict',
                           'ol_os_oracle_cloud_agent']
        for mig_dict in mig_dict_values:
            test_res = migrate_tools.get_config_data(mig_dict)
            self.assertIsNotNone(test_res)
            self.assertIsInstance(test_res, dict)
            

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestYamlConfig)
    unittest.TextTestRunner().run(suite)
