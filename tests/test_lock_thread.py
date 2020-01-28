# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

import unittest

from oci_utils.impl import lock_thread, release_thread
from tools.oci_test_case import OciTestCase

class TestLockThread(OciTestCase):
    """ Test lock thread.
    """
    def test_unlock_unlocked(self):
        """Tests unlock behavior for not locked object
        """
        with self.assertRaises(AssertionError):
            release_thread()

    def test_lock_twise(self):
        """Tests lock behavior for re-entrant attempt
        """
        lock_thread()
        with self.assertRaises(AssertionError):
            lock_thread()
        release_thread()


if __name__ == '__main__':
    unittest.main()
