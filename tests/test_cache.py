#!/usr/bin/python

# Copyright (c) 2017, 2018 Oracle and/or its affiliates. All rights reserved.
#
# The Universal Permissive License (UPL), Version 1.0
#
# Subject to the condition set forth below, permission is hereby granted to
# any person obtaining a copy of this software, associated documentation
# and/or data (collectively the "Software"), free of charge and under any
# and all copyright rights in the Software, and any and all patent rights
# owned or freely licensable by each licensor hereunder covering either
# (i) the unmodified Software as contributed to or provided by such licensor, or
# (ii) the Larger Works (as defined below), to deal in both
# (a) the Software, and
# (b) any piece of software and/or hardware listed in the lrgrwrks.txt
# file if one is included with the Software (each a "Larger Work" to which
# the Software is contributed by such licensors),
#
# without restriction, including without limitation the rights to copy,
# create derivative works of, display, perform, and distribute the Software
# and make, use, sell, offer for sale, import, export, have made, and have
# sold the Software and the Larger Work(s), and to sublicense the foregoing
# rights on either these or other terms.
#
# This license is subject to the following condition:
#
# The above copyright notice and either this complete permission notice or
# at a minimum a reference to the UPL must be included in all copies or
# substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

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
