#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2017 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

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
