# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import unittest

from tools.decorators import skipUnlessRoot
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'

class TestExecHelpers(OciTestCase):
    """ Test around lib/oci_utils/impl/sudo_utils.py.
    """

    def setUp(self):
        """
        Initialisation.

        Returns
        -------
            No return value.
        """
        super().setUp()
        self.execute_cmd = self.properties.get_property('exec_cmd').split(' ')

    def test_execute(self):
        """
        Test execute.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.sudo_utils
        self.assertTrue(oci_utils.impl.sudo_utils.execute(self.execute_cmd))

    def test_call_output(self):
        """
        Test execute.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.sudo_utils
        self.assertTrue(oci_utils.impl.sudo_utils.execute(self.execute_cmd))

    @skipUnlessRoot()
    def test_call(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.sudo_utils
        self.assertFalse(oci_utils.impl.sudo_utils.call(['/bin/ls', '/']))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestExecHelpers)
    unittest.TextTestRunner().run(suite)