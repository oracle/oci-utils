# oci-utils
#
# Copyright (c) 2017, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Python wrapper around lsblk.
"""

import logging
import os
import re
import subprocess

__lsblk_logger = logging.getLogger('oci-utils.lsblk')

_LSBLK_PATTERN = re.compile(r'^NAME="([^"]*)" FSTYPE="([^"]*)" MOUNTPOINT="([^"]*)" SIZE="([^"]*)" PKNAME="([^"]*)"',
                            flags=re.UNICODE)


def list():
    """
    Run lsblk, list block devices.

    Returns
    -------
        dict
            A dict representing the scsi devices:
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
        with open(os.devnull, 'w') as DEVNULL:
            # output = subprocess.check_output(['/bin/lsblk',
            #                                   '--scsi',
            #                                   '--pairs',
            #                                   '--noheadings',
            #                                   '-o', 'NAME,FSTYPE,MOUNTPOINT,SIZE,PKNAME'],
            #                                  stderr=DEVNULL).decode('utf-8')
            output = subprocess.check_output(['/bin/lsblk',
                                              '--pairs',
                                              '--noheadings',
                                              '-o', 'NAME,FSTYPE,MOUNTPOINT,SIZE,PKNAME'],
                                             stderr=DEVNULL).decode('utf-8')
        devices = {}
        # with python3, output id byte-like object, cast it to str
        for line in output.splitlines():
            match = _LSBLK_PATTERN.match(line.strip())
            if match:
                dev = match.group(1)
                devdict = {}
                devdict['fstype'] = match.group(2)
                devdict['mountpoint'] = match.group(3)
                devdict['size'] = match.group(4)
                pkname = match.group(5)
                if len(pkname) != 0:
                    if pkname not in devices:
                        devices[pkname] = {}
                    if 'partitions' not in devices[pkname]:
                        devices[pkname]['partitions'] = {}
                    devices[pkname]['partitions'][dev] = devdict
                else:
                    devices[dev] = devdict
        return devices
    except subprocess.CalledProcessError:
        __lsblk_logger.exception('error running lsblk')
        return {}
