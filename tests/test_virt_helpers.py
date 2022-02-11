
# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import unittest

from tools.decorators import skipUnlessOCI
from tools.decorators import skipUnlessVirSHInstalled
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'


class TestVirtHelpers(OciTestCase):
    """
    Virt helpers Test cases.
    These are really basic tests to insure code runs well.
    """

    @skipUnlessOCI()
    def test_sysconfig_read_network_config(self):
        """
        Test sysconfig.read_network_config.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.sysconfig
        self.assertIsNotNone(oci_utils.impl.virt.sysconfig.read_network_config())

    @skipUnlessOCI()
    def test_virt_check_iommu_check(self):
        """
        Test virt_check.iommu_check.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.virt_check
        oci_utils.impl.virt.virt_check.iommu_check()

    @skipUnlessOCI()
    def test_virt_check_sriov_numvfs_check(self):
        """
        Test virt_check.sriov_numvfs_check.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.virt_check
        oci_utils.impl.virt.virt_check.sriov_numvfs_check('lo')

    @skipUnlessOCI()
    def test_virt_check_br_link_mode_check(self):
        """
        Test virt_check.br_link_mode_check.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.virt_check
        oci_utils.impl.virt.virt_check.br_link_mode_check('lo')

    @skipUnlessVirSHInstalled()
    @skipUnlessOCI()
    def test_virt_check_validate_kvm_env(self):
        """
        Test virt_check.validate_kvm_env.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.virt_check
        oci_utils.impl.virt.virt_check.validate_kvm_env()

    @skipUnlessOCI()
    def test_virt_check_validate_domain_name(self):
        """
        Test validate_domain_name.
        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.virt_check
        oci_utils.impl.virt.virt_check.validate_domain_name('__ff__')

    @skipUnlessVirSHInstalled()
    @skipUnlessOCI()
    def test_virt_check_validate_block_device(self):
        """
        Test validate_block_device.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.virt_check
        oci_utils.impl.virt.virt_check.validate_block_device(None)

    @skipUnlessVirSHInstalled()
    @skipUnlessOCI()
    def test_virt_virt_utils_get_domains_name(self):
        """
        Test read_network_config.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.virt_utils
        oci_utils.impl.virt.virt_utils.get_domains_name()

    @skipUnlessVirSHInstalled()
    @skipUnlessOCI()
    def test_virt_virt_utils_get_domains_state(self):
        """
        Test get_domains_state.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.virt_utils
        _all = oci_utils.impl.virt.virt_utils.get_domains_name()
        if len(_all) > 0:
            oci_utils.impl.virt.virt_utils.get_domains_state(_all[0])

    @skipUnlessVirSHInstalled()
    @skipUnlessOCI()
    def test_virt_virt_utils_get_domains_interfaces(self):
        """
        Test get_domains_interfaces.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.virt_utils
        _all = oci_utils.impl.virt.virt_utils.get_domains_name()
        if len(_all) > 0:
            oci_utils.impl.virt.virt_utils.get_domains_interfaces(_all[0])

    @skipUnlessVirSHInstalled()
    @skipUnlessOCI()
    def test_virt_virt_utils_get_domains_xml(self):
        """
        Test get_domain_xml.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.virt_utils
        _all = oci_utils.impl.virt.virt_utils.get_domains_name()
        if len(_all) > 0:
            oci_utils.impl.virt.virt_utils.get_domain_xml(_all[0])

    @skipUnlessVirSHInstalled()
    @skipUnlessOCI()
    def test_virt_virt_utils_get_interfaces_from_domain(self):
        """
        Test get_interfaces_from_domain.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.virt_utils
        _all = oci_utils.impl.virt.virt_utils.get_domains_name()
        if len(_all) > 0:
            oci_utils.impl.virt.virt_utils.get_interfaces_from_domain(
                oci_utils.impl.virt.virt_utils.get_domain_xml(_all[0]))

    @skipUnlessVirSHInstalled()
    @skipUnlessOCI()
    def test_virt_virt_utils_get_disks_from_domain(self):
        """
        Test get_domains_name.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.virt.virt_utils
        _all = oci_utils.impl.virt.virt_utils.get_domains_name()
        if len(_all) > 0:
            oci_utils.impl.virt.virt_utils.get_disks_from_domain(
                oci_utils.impl.virt.virt_utils.get_domain_xml(_all[0]))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVirtHelpers)
    unittest.TextTestRunner().run(suite)