# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

import os
import unittest

import oci_utils.iscsiadm
from tools.decorators import (skipUnlessOCI, skipUnlessRoot, skipItAsUnresolved)
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'

class TestIScsiAdm(OciTestCase):
    """ Test iscsiadm module.
    """

    @skipItAsUnresolved()
    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_discovery(self):
        """
        Tests iscsiadm.discovery. Test LUNs discovery from an OCI instance.

        Returns
        -------
            No return value.
        """
        iqns = oci_utils.iscsiadm.discovery(self.properties.get_property('discovery-address'))
        self.assertTrue(len(iqns) > 0,
                        'No LUNs discovered against [%s]' %
                        self.properties.get_property('discovery-address'))
        self.assertIn(self.properties.get_property('lun_iqn'), iqns[0],
                      '[%s] not the first IQN discovered: <> [%s]' %
                      (self.properties.get_property('lun_iqn'), iqns[0]))

    @skipItAsUnresolved()
    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_session(self):
        """
        Tests iscsiadm.session.

        Returns
        -------
            No return value.
        """
        iqns = oci_utils.iscsiadm.session()
        self.assertIn(self.properties.get_property('lun_iqn'), iqns,
                      'boot disk lun [%s] not found in IQN discovered [%s]' %
                      (self.properties.get_property('lun_iqn'), iqns))
        self.assertEqual(iqns['iqn.2015-02.oracle.boot:uefi']
                         ['current_portal_ip'], '169.254.0.2')


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestIScsiAdm)
    unittest.TextTestRunner().run(suite)
