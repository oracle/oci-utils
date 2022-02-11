# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest
from tools.decorators import skipUnlessRoot
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'

class TestExecOcid(OciTestCase):
    """ libexec/ocid tests.
    """

    OCID = '/usr/libexec/ocid'

    @skipUnlessRoot()
    def setUp(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.
        """
        super(TestExecOcid, self).setUp()
        self.ocid = self.properties.get_property('ocid-path')
        if not os.path.exists(self.ocid):
            raise unittest.SkipTest("%s not present" % self.ocid)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.ocid, '--help'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_refresh_vnic(self):
        """
        Test refresh all.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.ocid, '--refresh', 'vnic'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_refresh_iscsi(self):
        """
        Test refresh all.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.ocid, '--refresh', 'iscsi'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_refresh_public_ip(self):
        """
        Test refresh all.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.ocid, '--refresh', 'public_ip'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_refresh_all(self):
        """
        Test refresh all.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.ocid, '--refresh'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestExecOcid)
    unittest.TextTestRunner().run(suite)