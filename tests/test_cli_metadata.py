#!/usr/bin/env python2.7

# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest


class TestCliOciMetadata(unittest.TestCase):
    """ oci-metadata tests.
    """

    metadata_cli = '/bin/oci-metadata'

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
        if not os.path.exists(TestCliOciMetadata.metadata_cli):
            raise unittest.SkipTest("%s not present" %
                                    TestCliOciMetadata.metadata_cli)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([TestCliOciMetadata.metadata_cli,
                                         '--help'])
        except Exception, e:
            self.fail('Execution has failed: %s' % str(e))
