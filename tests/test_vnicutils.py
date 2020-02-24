
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import unittest

from tools.decorators import (skipUnlessOCI, skipUnlessRoot)
from tools.oci_test_case import OciTestCase


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

    @skipUnlessRoot()
    def test_get_network_config(self):
        """
        Test VNICUtils.get_network_config()

        Returns
        -------
            No return value.
        """
        import oci_utils.vnicutils
        vu = oci_utils.vnicutils.VNICUtils()

        print(vu.get_network_config())
