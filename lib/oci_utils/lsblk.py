# oci-utils
#
# Copyright (c) 2017, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Python wrapper around lsblk.
"""

import logging
import os
import re
import subprocess

from oci_utils import find_exec_in_path

_logger = logging.getLogger('oci-utils.lsblk')
# _LSBLK_PATTERN = re.compile(r'^NAME="([^"]*)" FSTYPE="([^"]*)" MOUNTPOINT="([^"]*)" SIZE="([^"]*)" PKNAME="([^"]*)"', flags=re.UNICODE)

_LSBLK_PATTERN = re.compile(r'^NAME="([^"]*)" FSTYPE="([^"]*)" MOUNTPOINT="([^"]*)" SIZE="([^"]*)" PKNAME="([^"]*)" TYPE="([^"]*)"', flags=re.UNICODE)


def list_blk_dev():
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
    cmd = [find_exec_in_path('lsblk'), '--scsi', '--pairs', '--noheadings', '-o', 'NAME,FSTYPE,MOUNTPOINT,SIZE,PKNAME,TYPE']
    _logger.debug('Running %s', cmd)
    try:
        with open(os.devnull, 'w') as DEVNULL:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8')
            _logger.debug('subprocess output %s', output)
        devices = dict()
        # with python3, output id byte-like object, cast it to str
        for line in output.splitlines():
            match = _LSBLK_PATTERN.match(line.strip())
            _logger.debug(match)
            if match:
                dev = match.group(1)
                devdict = dict()
                devdict['fstype'] = match.group(2)
                devdict['mountpoint'] = match.group(3)
                devdict['size'] = match.group(4)
                devdict['type'] = match.group(6)
                pkname = match.group(5)
                if len(pkname) != 0:
                    if pkname not in devices:
                        devices[pkname] = {}
                    if 'partitions' not in devices[pkname]:
                        devices[pkname]['partitions'] = dict()
                    devices[pkname]['partitions'][dev] = devdict
                else:
                    devices[dev] = devdict
                thoseparts = lsblk_partitions(dev)
                devices[dev]['partitions'] = dict()
                for part in thoseparts:
                    partdetail = lsblk_partition_data(part)
                    devices[dev]['partitions'][re.sub(r'/dev/', '', part)] = partdetail
        return devices
    except subprocess.CalledProcessError:
        _logger.exception('Error running lsblk', exc_info=True, stack_info=True)
        return {}


def lsblk_partitions(device):
    """
    Collect the partitions of a device.

    Parameters
    ----------
    device: str
        The device name.

    Returns
    -------
        list: The list of the partitons.
    """
    cmd = [find_exec_in_path('lsblk'), '--pairs', '--noheadings', '-o', 'NAME,TYPE', '/dev/' + device]
    _logger.debug('Running %s', cmd)
    try:
        with open(os.devnull, 'w') as DEVNULL:
            output = subprocess.check_output(cmd, stderr=DEVNULL).decode('utf-8')
        _logger.debug('subprocess output %s', output)
        partitions = list()
        for line in output.splitlines():
            if re.search(r'TYPE="([^"]*)"', line).group(1) == 'part':
                partitions.append('/dev/' + re.search(r'^NAME="([^"]*)"', line).group(1))
        return partitions
    except subprocess.CalledProcessError:
        _logger.exception('Error running fdisk', exc_info=True, stack_info=True)
        return []


def lsblk_partition_data(part):
    """
    Collect the data of a partition.

    Parameters
    ----------
    part: str
        The partition name.

    Returns
    -------
        dict: the partition data.
    """
    if not bool(part) or not(os.path.exists(part)):
        _logger.error('Partition %s does not exist.', part)
        return {}
    cmd = [find_exec_in_path('lsblk'), '--pairs', '--noheadings', '-o', 'NAME,FSTYPE,MOUNTPOINT,SIZE,PKNAME,TYPE', part]
    _logger.debug('Running %s', cmd)
    try:
        with open(os.devnull, 'w') as DEVNULL:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8')
            _logger.debug('subprocess output %s', output)
        partdict = dict()
        for line in output.splitlines():
            match = _LSBLK_PATTERN.match(line.strip())
            if match:
                partition = match.group(0)
                partdict['fstype'] = match.group(2)
                partdict['mountpoint'] = match.group(3)
                partdict['size'] = match.group(4)
                partdict['type'] = match.group(6)
                pkname = match.group(5)
        return partdict
    except subprocess.CalledProcessError:
        _logger.exception('Error running lsblk', exc_info=True, stack_info=True)
        return {}


def show_blk(ddd, depth):
    """
    Print the partition tree.

    Parameters
    ----------
    ddd: dict
        The tree.
    depth: int
        The level in the tree.

    Returns
    -------
        No return value.
    """
    if isinstance(ddd, dict):
        print('')
        for key, value in ddd.items():
            print('%s%s' % ('  '*depth, key.ljust(12, ' ')), end='')
            show_blk(value, depth+1)
    else:
        print('%s' % ddd)
