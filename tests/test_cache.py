#!/usr/bin/python

# Copyright (c) 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

import os
import unittest
from oci_utils.cache import get_newer, get_timestamp, load_cache, write_cache
from datetime import datetime, timedelta
import uuid
import time

class testOciCache(unittest.TestCase):
    def setUp(self):
        # create 2 files, one newer than the other to verify get_newer()
        self.file1 = "/tmp/oci-test-%s" % uuid.uuid1()
        self.file2 = "/tmp/oci-test-%s" % uuid.uuid1()
        self.file3 = "/tmp/oci-test-%s" % uuid.uuid1()
        # this one won't be created
        self.nofile = "/tmp/oci-test-%s" % uuid.uuid1()
        os.system("echo '{\"foo\":2}' > %s" % self.file1)
        time.sleep(1)
        os.system("echo '{\"bar\":4}' > %s" % self.file2)
        self.ts1 = get_timestamp(self.file1)
        self.ts2 = get_timestamp(self.file2)

    def tearDown(self):
        os.system("rm -f %s %s %s" % (self.file1, self.file2, self.file3))

    def test_get_newer(self):
        self.assertEqual(get_newer(self.file1, self.file2), self.file2)
        self.assertEqual(get_newer(self.file2, self.file1), self.file2)
        self.assertEqual(get_newer(self.file1, None), self.file1)
        self.assertEqual(get_newer(None, self.file1), self.file1)
        self.assertEqual(get_newer(self.file1, self.nofile), self.file1)
        self.assertEqual(get_newer(self.nofile, self.file2), self.file2)
        self.assertEqual(get_newer(self.nofile, None), None)
        self.assertEqual(get_newer(None, None), None)

    def test_load_cache(self):
        self.assertEqual(load_cache(self.file1, self.file2),
                         (self.ts2, {'bar':4}))
        self.assertEqual(load_cache(self.file1, self.nofile),
                         (self.ts1, {'foo':2}))
        self.assertEqual(load_cache(self.file1, self.nofile,
                                    max_age=timedelta(minutes = 100)),
                         (self.ts1, {'foo':2}))
        self.assertEqual(load_cache(self.nofile,
                                    max_age=timedelta(seconds = 1)),
                         (0, None))

    def test_write_cache(self):
        ts0 = write_cache(cache_fname=self.file3,
                          cache_content={'hello':'world'})
        self.assertNotEqual(ts0, None)
        ts = get_timestamp(self.file3)
        self.assertEqual(ts0, ts)
        self.assertEqual(load_cache(self.file3),
                         (ts, {'hello':'world'}))
        self.assertFalse(write_cache(cache_fname='/proc/foo1',
                                     cache_content={}))
        self.assertFalse(write_cache(cache_fname='/proc/foo1',
                                     fallback_fname='/proc/foo3',
                                     cache_content={}))
        self.assertTrue(write_cache(cache_fname='/proc/foo1',
                                    fallback_fname=self.file3,
                                     cache_content={'hello':'again'}))
        ts = get_timestamp(self.file3)
        self.assertEqual(load_cache(self.file3),
                         (ts, {'hello':'again'}))

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(testOciCache)
    unittest.TextTestRunner(verbosity=2).run(suite)
