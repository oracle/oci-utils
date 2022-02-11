
# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import unittest

from tools.decorators import (skipUnlessOCI, skipUnlessRoot)
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'


class TestVnicUtils(OciTestCase):
    """
    VNICUtils Test cases.
    """

    @skipUnlessOCI()
    def test_create_instance(self):
        """
        Test VNICUtils.new.

        Returns
        -------
            No return value.
        """
        import oci_utils.vnicutils
        self.assertIsNotNone(oci_utils.vnicutils.VNICUtils())

    def test_get_network_config(self):
        """
        Test VNICUtils.get_network_config()

        Returns
        -------
            No return value.
        """
        import oci_utils.vnicutils
        vu = oci_utils.vnicutils.VNICUtils()

        for nc in vu.get_network_config():
            print(nc)


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVnicUtils)
    unittest.TextTestRunner().run(suite)