# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import unittest
from oci_utils.impl.auth_helper import OCIAuthProxy
from tools.decorators import skipUnlessOCI
from tools.oci_test_case import OciTestCase

class TestAuthHelpers(OciTestCase):
    """
    Auth helpers Test cases.
    """

    @skipUnlessOCI()
    def test_get_config(self):
        """
        Test OCIAuthProxy.get_config.

        Returns
        -------
            No return value.
        """
        unittest.skip('Need user password')
        # print(OCIAuthProxy('opc').get_config())
