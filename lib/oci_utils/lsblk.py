#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2017 Oracle and/or its affiliates. All rights reserved.
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

"""
Python wrapper around lsblk
"""

import os
import socket
import subprocess
import logging
import re

__lsblk_logger = logging.getLogger('lsblk')
__lsblk_logger.setLevel(logging.INFO)
__handler = logging.StreamHandler()
__lsblk_logger.addHandler(__handler)

def set_logger(logger):
    global __lsblk_logger
    __lsblk_logger = logger

def list():
    """
    run lsblk, return a dict representing the scsi devices:
    {device:
        {'mountpoint':mountpoint,
         'fstype':fstype,
         'size':size,
         'partitions':
               {device1:
                   {'mountpoint':mountpoint1,
                    'fstype':fstype1,
                    'size':size1}
                device2:     
                   {'mountpoint':mountpoint2,
                    'fstype':fstype2,
                    'size':size2}
                ...
               }
        }
    }    
    """
    try:
        DEVNULL = open(os.devnull, 'w')
        output = subprocess.check_output(['/bin/lsblk',
                                          '-P', '-n',
                                          '-o', 'NAME,FSTYPE,MOUNTPOINT,SIZE',
                                          '-a'],
                                         stderr=DEVNULL)
        devices = {}
        pattern = re.compile(r'^NAME="([^"]*)" FSTYPE="([^"]*)" MOUNTPOINT="([^"]*)" SIZE="([^"]*)"')
        for line in output.split('\n'):
            match = pattern.match(line.strip())
            if (match):
                dev = match.group(1)
                devdict = {}
                devdict['fstype'] = match.group(2)
                devdict['mountpoint'] = match.group(3)
                devdict['size'] = match.group(4)
                if len(dev) > 3:
                    if not dev[:3] in devices:
                        devices[dev[:3]] = {}
                    if not 'partitions' in devices[dev[:3]]:
                        devices[dev[:3]]['partitions'] = {}
                    devices[dev[:3]]['partitions'][dev] = devdict
                else:
                    devices[dev] = devdict
        return devices
    except subprocess.CalledProcessError as e:
        return {}
