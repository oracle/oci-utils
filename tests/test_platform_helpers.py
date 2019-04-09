# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import unittest

from decorators import skipUnlessOCI


class TestPlatformHelpers(unittest.TestCase):
    """ Test around lib/oci_utils/impl/platform_helpers.py.
    """

    @skipUnlessOCI()
    def test_get_phys_device(self):
        """
        Test get_phys_device.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.platform_helpers
        self.assertIsNotNone(oci_utils.impl.platform_helpers.get_phys_device(),
                             'None returned by get_block_device()')

    @skipUnlessOCI()
    def test_get_block_device(self):
        """
        Test get_block_devices.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.platform_helpers
        self.assertIsNotNone(
            oci_utils.impl.platform_helpers.get_block_devices(),
            'None returned by get_block_devices()')
