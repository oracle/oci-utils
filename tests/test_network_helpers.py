#!/usr/bin/env python2.7

# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.


import socket
import unittest

from oci_utils.impl.network_helpers import is_ip_reachable


class TestNetworkHelpers(unittest.TestCase):
    """
    Test impl/network_helpers.py.

    Attributes
    ----------
    _discovery_address: str
        The IP address.
    _lun_iqn: str
        The iSCSI qualified name.
    _test_connect_remote: str
        The remote hostname.
    _test_connect_remote_port:
        The port to use for the test.
    """
    _discovery_address = '169.254.0.2'
    _lun_iqn = 'iqn.2015-02.oracle.boot:uefi'

    _test_connect_remote = 'localhost'
    _test_connect_remote_port = 10000

    def setUp(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.
        """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((TestNetworkHelpers._test_connect_remote,
                        TestNetworkHelpers._test_connect_remote_port))
        self.sock.listen(1)

    def tearDown(self):
        """
        Test removal.

        Returns
        -------
            No return value.
        """
        self.sock.close()

    def test_can_connect(self):
        """
        Test network connection.

        Returns
        -------
            No return value.
        """
        self.assertTrue(is_ip_reachable(
            TestNetworkHelpers._test_connect_remote,
            TestNetworkHelpers._test_connect_remote_port))
        self.assertFalse(is_ip_reachable('blabber', 80))
