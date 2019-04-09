#!/usr/bin/env python2.7

# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest


class TestCliKvm(unittest.TestCase):
    """ oci-kvm tests.
    """

    KVM = '/bin/oci-kvm'

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
        if not os.path.exists(TestCliKvm.KVM):
            raise unittest.SkipTest("%s not present" % TestCliKvm.KVM)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([TestCliKvm.KVM, '--help'])
        except Exception, e:
            self.fail('Execution has failed: %s' % str(e))
