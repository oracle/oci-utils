# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest
from tools.oci_test_case import OciTestCase


class TestCliKvm(OciTestCase):
    """ oci-kvm tests.
    """

    def setUp(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.

        Raises
        ------
        unittest.SkipTest
            If the KVM config file does not exists.
        """
        super(TestCliKvm, self).setUp()
        self.oci_kvm_path = self.properties.get_property('oci-kvm-path')
        if not os.path.exists(self.oci_kvm_path):
            raise unittest.SkipTest("%s not present" %
                                    self.oci_kvm_path)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_kvm_path, '--help'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))
