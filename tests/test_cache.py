# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import json
import os
import tempfile
import time
import unittest
import uuid
from datetime import timedelta

from oci_utils.cache import get_newer, get_timestamp, load_cache, write_cache
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'

class testOciCache(OciTestCase):
    """ OCI cache test case.
    """
    file1_content = {'foo': 2}
    file2_content = {'bar': 4}

    def setUp(self):
        """
        Initialise the OCI cache test.

        Returns
        -------
            No return value.
        """
        super(testOciCache, self).setUp()
        # create 2 files, one newer than the other to verify get_newer()
        self.file1 = "/tmp/oci-test-%s" % uuid.uuid1()
        self.file2 = "/tmp/oci-test-%s" % uuid.uuid1()
        self.file3 = "/tmp/oci-test-%s" % uuid.uuid1()
        # this one won't be created
        self.nofile = "/tmp/oci-test-%s" % uuid.uuid1()
        with open(self.file1, "w") as _f:
            json.dump(testOciCache.file1_content, _f)
        _f.close()
        time.sleep(1)
        with open(self.file2, "w") as _f:
            json.dump(testOciCache.file2_content, _f)
        _f.close()

        self.ts1 = get_timestamp(self.file1)
        self.ts2 = get_timestamp(self.file2)

    def tearDown(self):
        """
        Clean up.

        Returns
        -------
            No return value.
        """
        for _p in (self.file1, self.file2, self.file3):
            if os.path.exists(_p):
                try:
                    os.remove(_p)
                except OSError as e:
                    print('warning, cannot delete %s: %s' % (_p, str(e)))

    def test_get_timestamp(self):
        """
        Tests cache.get_timestamp().

        Returns
        -------
            No return value.
        """
        self.assertEqual(get_timestamp(None), 0, 'get_timestamp(None) != 0')
        self.assertEqual(get_timestamp('file_path_which_do_not_exists '), 0,
                         'get_timestamp() on non-existing file did not return 0')
        self.assertGreater(get_timestamp(tempfile.gettempdir()), 0,
                           'get_timestamp() on existing path did not return '
                           'positive value')

    def test_get_newer(self):
        """
        Tests cache.get_newer().

        Returns
        -------
            No return value.
        """
        self.assertEqual(get_newer(self.file1, self.file2), self.file2, 'expected self.file2 to be the newer')
        self.assertEqual(get_newer(self.file2, self.file1), self.file2, 'expected self.file2 to be the newer')
        self.assertEqual(get_newer(self.file1, None), self.file1, 'get_newer(filename, None) != filename')
        self.assertEqual(get_newer(None, self.file1), self.file1, 'get_newer(None, filename) != filename')
        self.assertEqual(get_newer(self.file1, self.nofile), self.file1, 'get_newer(filename, \'no existing file\') != filename')
        self.assertEqual(get_newer(self.nofile, self.file2), self.file2, 'get_newer(\'no existing file\', filename, ) != filename')
        self.assertEqual(get_newer(self.nofile, None), None, 'get_newer(\'no existing file\', None) != None')
        self.assertEqual(get_newer(None, None), None, 'get_newer(None, None) != None')

    def test_load_cache(self):
        """
        Tests cache.load_cache().

        Returns
        -------
            No return value.
        """
        self.assertEqual(load_cache(self.file1, self.file2),
                         (self.ts2, testOciCache.file2_content))

        self.assertEqual(load_cache(self.file1, self.nofile),
                         (self.ts1, testOciCache.file1_content),
                         'load_cache(file1, NOFILE) did not return '
                         'content of file1')

        self.assertEqual(load_cache(self.file1,
                                    self.nofile,
                                    max_age=timedelta(minutes=100)),
                         (self.ts1, testOciCache.file1_content),
                         'load_cache(file1, NOFILE, max_age) did not return '
                         'content of file1')
        self.assertEqual(load_cache(self.nofile,
                                    max_age=timedelta(seconds=1)),
                         (0, None),
                         'load_cache(file1, NOFILE, small max age) did not '
                         'return None')

    def test_write_cache(self):
        """
        Test cache.write_cache().

        Returns
        -------
            No return value.
        """
        ts0 = write_cache(cache_fname=self.file3,
                          cache_content={'hello': 'world'})
        self.assertNotEqual(ts0, None,
                            "New cache write return None as timestamp")
        ts = get_timestamp(self.file3)
        self.assertEqual(ts0, ts,
                         "timestamp returned from get_timestamp differ form "
                         "one returned by write_cache")
        self.assertEqual(load_cache(self.file3),
                         (ts, {'hello': 'world'}),
                         'Unexpected return values from load_cache()')
        self.assertFalse(write_cache(cache_fname='/proc/foo1',
                                     cache_content={}))
        self.assertFalse(write_cache(cache_fname='/proc/foo1',
                                     fallback_fname='/proc/foo3',
                                     cache_content={}))
        self.assertTrue(write_cache(cache_fname='/proc/foo1',
                                    fallback_fname=self.file3,
                                    cache_content={'hello': 'again'}))
        ts = get_timestamp(self.file3)
        self.assertEqual(load_cache(self.file3),
                         (ts, {'hello': 'again'}))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(testOciCache)
    unittest.TextTestRunner().run(suite)
