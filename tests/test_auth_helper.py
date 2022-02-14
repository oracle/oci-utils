# Copyright (c) 2019, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import unittest
from oci_utils.impl.auth_helper import OCIAuthProxy
import os
from tools.decorators import skipUnlessOCI
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'

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


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAuthHelpers)
    unittest.TextTestRunner().run(suite)
