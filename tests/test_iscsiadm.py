#!/usr/bin/python

import os
import unittest
import oci_utils.iscsiadm
from oci_utils.iscsiadm import __can_connect as can_connect

# skip tests that require an OCI instance if not running on an OCI instance
def skipUnlessOCI():
    if not oci_utils.iscsiadm.__can_connect('169.254.169.254', 80):
        return unittest.skip("must be run on an OCI instance")
    return lambda func: func
def skipUnlessRoot():
    if os.geteuid() != 0:
        return unittest.skip("must be root")
    return lambda func: func

class TestIScsiAdm(unittest.TestCase):
    def test__can_connect(self):
        self.assertTrue(can_connect('www.google.com', 80))
        self.assertTrue(can_connect('www.oracle.com', 443))
        self.assertFalse(can_connect('www.google.com', 123))
        self.assertFalse(can_connect('blabber', 80))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_discovery(self):
        iqns = oci_utils.iscsiadm.discovery('169.254.0.2')
        self.assertTrue(len(iqns)>0)
        self.assertIn('iqn.2015-02.oracle.boot:uefi', iqns[0])

    @skipUnlessOCI()
    def test_session(self):
        iqns = oci_utils.iscsiadm.session()
        self.assertIn('iqn.2015-02.oracle.boot:uefi', iqns)
        self.assertEqual(iqns['iqn.2015-02.oracle.boot:uefi']['current_portal_ip'], '169.254.0.2')

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestIScsiAdm)
    unittest.TextTestRunner(verbosity=2).run(suite)
