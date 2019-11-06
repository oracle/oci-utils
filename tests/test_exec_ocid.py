# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest
from decorators import skipUnlessRoot


class TestExecOcid(unittest.TestCase):
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
        if not os.path.exists(TestExecOcid.OCID):
            raise unittest.SkipTest("%s not present" % TestExecOcid.OCID)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([TestExecOcid.OCID, '--help'])
        except Exception, e:
            self.fail('Execution has failed: %s' % str(e))
