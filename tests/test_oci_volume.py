# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import time
import unittest

import oci_utils
import oci_utils.oci_api
from tools.decorators import needsOCICLI
from tools.oci_test_case import OciTestCase
from oci_utils.exceptions import OCISDKError


class TestOCIVolume(OciTestCase):
    """ Test OCI block volume.
    """

    @needsOCICLI()
    def setUp(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.
        """
        super(TestOCIVolume, self).setUp()
        self.logger.info('creating test volume')
        self.testVol = None
        try:
            self.sess = oci_utils.oci_api.OCISession()
        except OCISDKError:
            self.fail("Failed to start OCI API session")
        self.testVol = self.sess.create_volume(
            availability_domain=self.sess.this_availability_domain(),
            compartment_id=self.sess.this_compartment().get_ocid(),
            size=53,
            display_name="oci-utils-unittest-vol")
        self.assertIsNotNone(self.testVol,
                             "Failed to create Volume for testing")
        print('new volume created [%s]' % self.testVol.get_ocid())

    @needsOCICLI()
    def tearDown(self):
        """
        Clean up test block volume.

        Returns
        -------
            No return value.
        """
        vol_id = self.testVol.get_ocid()
        if self.volume_attached:
            print('have to detach volume')
            self.testVol.detach(wait=True)
            print('volume detached')

        self.testVol.destroy()

        for n in range(10):
            # verify that it's gone
            vol = self.sess.get_volume(volume_id=vol_id, refresh=True)
            if vol is None:
                break
            else:
                time.sleep(2)
        self.assertIsNone(vol, 'Cannot get volume with ID [%s]' % vol_id)

    @needsOCICLI()
    def test__oci_instance__attach_volume(self):
        """
        Tests block volume attach.

        Returns
        -------
            No return value.
        """
        self.volume_attached = False
        inst = self.sess.this_instance()
        self.assertIsNotNone(inst, 'Cannot fetch OCI instance')
        try:
            self.testVol = inst.attach_volume(volume_id=self.testVol.get_ocid())
            self.volume_attached = True
        except OCISDKError as e:
            self.fail('attach of volume failed: %s' % str(e))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOCIVolume)
    unittest.TextTestRunner().run(suite)
