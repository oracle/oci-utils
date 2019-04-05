#!/usr/bin/env python2.7

# Copyright (c) 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

import os
import time
import unittest
import oci_utils
import oci_utils.oci_api
from oci_utils.exceptions import OCISDKError
from decorators import *
from common import *

def hostname():
    return os.popen("hostname").read().strip()

class TestOCIVolume(unittest.TestCase):

    @needsOCICLI()
    def setUp(self):
        self.testVol = None
        try:
            self.sess = oci_utils.oci_api.OCISession()
        except:
            self.fail("Failed to start OCI API session")
        self.testVol = self.sess.create_volume(
            availability_domain=self.sess.this_availability_domain(),
            compartment_id=self.sess.this_compartment().get_ocid(),
            size=53,
            display_name="oci-utils-unittest-vol")
        if self.testVol is None:
            raise unittest.SkipTest("Failed to create Volume for testing")

    @needsOCICLI()
    def tearDown(self):
        vol_id = self.testVol.get_ocid()
        self.testVol.detach(wait=True)
        self.testVol.destroy()
        for n in range(10):
            # verify that it's gone
            vol = self.sess.get_volume(volume_id=vol_id, refresh=True)
            if vol is None:
                break
            else:
                time.sleep(2)
        self.assertIsNone(vol)
        # also check using the oci cli
        (ret,out) = run_cmd(['oci', 'bv', 'volume', 'get',
                             '--volume-id', vol_id])
        self.assertIn('"TERMINATED"', out)
        
    @needsOCICLI()
    def test__oci_instance__attach_volume(self):
        sess = oci_utils.oci_api.OCISession()
        inst = sess.this_instance()
        self.testVol = inst.attach_volume(volume_id=self.testVol.get_ocid())
        
if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOCIVolume)
    unittest.TextTestRunner(verbosity=2).run(suite)
