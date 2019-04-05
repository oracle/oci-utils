#!/usr/bin/env python2.7

# Copyright (c) 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

import os
import unittest
import oci_utils
import oci_utils.oci_api
from oci_utils.exceptions import OCISDKError
from decorators import *
from common import *

class TestOCISession(unittest.TestCase):
    @skipUnlessOCI()
    def test__config_file_auth(self):
        s = oci_utils.oci_api.OCISession(auth_method=oci_utils.oci_api.DIRECT)
        self.assertIsNotNone(s)
        self.assertEqual(s.auth_method, oci_utils.oci_api.DIRECT)
        self.assertIsNone(s.signer)
        i = s.this_instance()
        self.assertIsNotNone(i)
        self.assertEqual(i.data.display_name, get_hostname())

    @skipUnlessOCI()
    def test__instance_principal_auth(self):
        s = oci_utils.oci_api.OCISession(auth_method=oci_utils.oci_api.IP)
        self.assertIsNotNone(s)
        self.assertEqual(s.auth_method, oci_utils.oci_api.IP)
        self.assertIsNotNone(s.signer)
        i = s.this_instance()
        self.assertIsNotNone(i)
        self.assertEqual(i.data.display_name, get_hostname())

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test__proxy_auth(self):
        s = oci_utils.oci_api.OCISession(auth_method=oci_utils.oci_api.PROXY)
        self.assertIsNotNone(s)
        self.assertEqual(s.auth_method, oci_utils.oci_api.PROXY)
        i = s.this_instance()
        self.assertIsNotNone(i)
        self.assertEqual(i.data.display_name, get_hostname())

    @skipUnlessOCI()
    def test__oci_session(self):
        # invalid config file -> should fail
        with self.assertRaisesRegexp(OCISDKError, 'Failed to authenticate'):
            s = oci_utils.oci_api.OCISession(
                config_file='/dev/null',
                auth_method=oci_utils.oci_api.DIRECT)

        # any form of auth
        s = oci_utils.oci_api.OCISession()
        self.assertIsNotNone(s)
        i = s.this_instance()
        self.assertIsNotNone(i)
        self.assertEqual(i.data.display_name, get_hostname())

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOCISession)
    unittest.TextTestRunner(verbosity=2).run(suite)
