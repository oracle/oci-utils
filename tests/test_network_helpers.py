# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

import os
import socket
import unittest

from oci_utils.impl.network_helpers import is_ip_reachable
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'


class TestNetworkHelpers(OciTestCase):
    """
    Test impl/network_helpers.py.

    Attributes
    ----------
    _test_connect_remote: str
        The remote hostname.
    _test_connect_remote_port:
        The port to use for the test.
    """

    def setUp(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.
        """
        super(TestNetworkHelpers, self).setUp()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.properties.get_property('connect_remote'),
                        int(self.properties.get_property('connect_remote_port'))))
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
            str(self.properties.get_property('connect_remote')),
            int(self.properties.get_property('connect_remote_port'))))
        self.assertFalse(is_ip_reachable('blabber', 80))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNetworkHelpers)
    unittest.TextTestRunner().run(suite)
