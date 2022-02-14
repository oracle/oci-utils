# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import time
import unittest
from tools.oci_test_case import OciTestCase


os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'


class TestCliOciMetadataBugs(OciTestCase):
    """ oci-metadata tests.
    """

    def setUp(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.

        Raises
        ------
        unittest.Skiptest
            If the metadata_cli does not exist.
        """

        super().setUp()
        self.oci_metadata_path = self.properties.get_property('oci-metadata')
        if not os.path.exists(self.oci_metadata_path):
            raise unittest.SkipTest("%s not present" % self.oci_metadata_path)

    def test_linux11499(self):
        """
        Test oci-metadata --get ... --value-only; should not return None
        Returns
        -------
        No return value.
        """
        get_value = subprocess.check_output([self.oci_metadata_path, '--get', 'region', '--value-only']).decode('utf-8').strip()
        self.assertIsNotNone(get_value, 'Is None')

    def test_linux11505(self):
        """
        Test oci-metadata --get ... --export; should not return None
        Returns
        -------
        No return value.
        """
        get_value = subprocess.check_output([self.oci_metadata_path, '--get', 'canonicalregionname', '--export']).decode('utf-8').strip()
        self.assertIsNotNone(get_value, 'Is None')


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCliOciMetadataBugs)
    unittest.TextTestRunner().run(suite)
