# oci-utils
#
# Copyright (c) 2018, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import logging
import os
import re

from oci_utils.metadata import InstanceMetadata
from . import IP_CMD
from . import sudo_utils

_logger = logging.getLogger('oci-utils.impl.platform-helpers')


def get_phys_device():
    """
    Find the primary ethernet device interface name.

    Returns
    -------
    str
        The primary ethernet device name.
    """
    try:
        # TODO : it seems that it is private_ip now
        private_ip = InstanceMetadata().refresh()['vnics'][0]['privateIp']
    except Exception as e:
        _logger.debug('error checking metadata: %s', str(e))
        return None
    phys_dev = None
    output = sudo_utils.call_output([IP_CMD, '-o', '-4', 'addr', 'show'])
    lines = output.splitlines()
    for line in lines:
        _l = line.decode().strip()
        if private_ip in _l:
            phys_dev = _l.split()[1]
    _logger.debug('%s physical devices found', len(phys_dev))
    return phys_dev


def get_block_devices():
    """
    Get all block devices.

    Returns
    -------
    dict
        Dictionary of {'/dev/sbX': '/dev/disk/by-path/XXX'}, where the value
        of the key-value pair is a symlink to the key, if successful,
        None otherwise
    """
    path_prefix = '/dev/disk/by-path'
    ret = {}
    try:
        dev_test = re.compile(r'/dev/[a-zA-Z]+$')
        for ent in os.listdir(path_prefix):
            path = '{}/{}'.format(path_prefix, ent)
            dev = os.path.abspath(os.path.join(path_prefix, os.readlink(path)))
            # Only include entries that point to a block device,
            # rather than a partition
            if dev_test.match(dev):
                ret[dev] = path
    except OSError as e:
        print(e)
        return None
    return ret
