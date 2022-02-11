# Copyright (c) 2020, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest

from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'


class TestUpload(OciTestCase):
    """ Test image upload.
    """
    def setUp(self):
        super(TestUpload, self).setUp()
        self.oci_migrate_image_upload_path = self.properties.get_property('oci-image-migrate-upload')
        if not os.path.exists(self.oci_migrate_image_upload_path):
            raise unittest.SkipTest("%s not present" %
                                    self.oci_migrate_image_upload_path)

    def test_display_help(self):
        """ Display help message.
        """
        try:
            _ = subprocess.check_output([self.oci_migrate_image_upload_path, '--help'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestUpload)
    unittest.TextTestRunner().run(suite)
