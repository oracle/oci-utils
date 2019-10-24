# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

import unittest

import oci_utils.iscsiadm
from decorators import (skipUnlessOCI, skipUnlessRoot)


class TestIScsiAdm(unittest.TestCase):
    """ Test iscsiadm module.
    """
    _discovery_address = '169.254.0.2'
    _lun_iqn = 'iqn.2015-02.oracle.boot:uefi'

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_discovery(self):
        """
        Tests iscsiadm.discovery. Test LUNs discovery from an OCI instance.

        Returns
        -------
            No return value.
        """
        iqns = oci_utils.iscsiadm.discovery(TestIScsiAdm._discovery_address)
        self.assertTrue(len(iqns) > 0,
                        'No LUNs discovered against [%s]' %
                        TestIScsiAdm._discovery_address)
        self.assertIn(TestIScsiAdm._lun_iqn, iqns[0],
                      '[%s] not the first IQN discovered' %
                      TestIScsiAdm._lun_iqn)

    @skipUnlessOCI()
    def test_session(self):
        """
        Tests iscsiadm.session.

        Returns
        -------
            No return value.
        """
        iqns = oci_utils.iscsiadm.session()
        self.assertIn(TestIScsiAdm._lun_iqn, iqns,
                      '[%s] not the first IQN discovered' %
                      TestIScsiAdm._lun_iqn)
        self.assertEqual(iqns['iqn.2015-02.oracle.boot:uefi']
                         ['current_portal_ip'], '169.254.0.2')


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestIScsiAdm)
    unittest.TextTestRunner().run(suite)
