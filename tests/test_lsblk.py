#!/usr/bin/env python2.7

# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import unittest

import oci_utils.lsblk


class TestLsBlk(unittest.TestCase):
    """ Test the lsblk module.
    """

    def test_list_root(self):
        """
        Tests lsblk.list give us the root filesystem.

        Returns
        -------
            No return value.
        """
        dev_list = oci_utils.lsblk.list()
        self.assertIsNotNone(dev_list, 'None returned as device list')
        self.assertTrue(len(dev_list), 'empty device list returned ')
