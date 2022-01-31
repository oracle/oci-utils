# oci-utils
#
# Copyright (c) 2018, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

"""
Verify if we have valid KVM environment on a BM with the following
   - Verify IOMMU is enabled
   - Verify it is a BM
   - Verify SR-IOV is enabled on primary ethernet device
   - Verify the bridge on primary ethernet device has VEPA link mode set
"""

import logging
import os

from oci_utils import lsblk
from . import virt_utils
from .. import BRIDGE_CMD
from .. import print_choices
from .. import sudo_utils
from ..platform_helpers import (get_block_devices, get_phys_device)

_logger = logging.getLogger('oci-utils.virt.virt-check')


def iommu_check():
    """
    Verify if the IOMMU is enabled. Linux kernel logs the message "IOMMU:
    enabled" at boot time.

    Returns
    -------
        bool
            True on success, False otherwise.
    """
    iommu_enabled_exp = "IOMMU.*enabled"
    output = sudo_utils.call_popen_output(
        ['/bin/dmesg', '|', 'egrep', '"{}"'.format(iommu_enabled_exp)])
    if not output:
        _logger.debug('IOMMU flag not set on kernel')
        return False
    return True


def sriov_numvfs_check(phys_dev):
    """
    Verify if the primary ethernet device has SR-IOV enabled.

    Parameters
    ----------
    phys_dev : str
        The primary ethernet device.

    Returns
    -------
       bool
            True on success, False otherwise.
    """
    sriov_fpath = '/sys/class/net/{}/device/sriov_numvfs'.format(phys_dev)
    try:
        f = open(sriov_fpath, "r")
        output = f.read()
        f.close()
        if int(output) > 0:
            return True
        _logger.debug('sriov_numvfs_check return false')
        return False
    except IOError as e:
        _logger.debug('error checking sriov_numvfs_check: %s' % str(e))
        return False


def br_link_mode_check(phys_dev):
    """
    Verify the bridge on primary ethernet device has VEPA link mode.

    Parameters
    ----------
    phys_dev : str
        The primary ethernet device.

    Returns
    -------
      bool
            True on success, False otherwise.
    """
    vepa = "VEPA"
    res = sudo_utils.call_popen_output(
        [BRIDGE_CMD, 'link', 'show', 'dev', '"{}"'.format(phys_dev)])
    if res and vepa == res.split()[-1].decode().upper():
        return True
    _logger.debug('br_link_mode_check, return False, server_type: %s ' % vepa)
    return False


def validate_kvm_env(check_for_bm_shape=True):
    """
    Verify if we have valid KVM environment on a BM with the following:
      - Verify IOMMU is enabled;
      - (for BM shapes) Verify SR-IOV is enabled on primary ethernet device;
      - (for BM shapes) Verify the bridge on primary ethernet device has VEPA link mode set.
    Parameters
    ----------
    check_for_bm_shape: boolean
        check for BM shape types ?
    Returns
    -------
        bool
            True on success, False otherwise.
    """
    phys_dev = get_phys_device()
    if phys_dev is None:
        _logger.debug('No physical device found')
        return False

    if not iommu_check():
        _logger.debug('iommu_check failed')
        return False

    if check_for_bm_shape:
        if not sriov_numvfs_check(phys_dev):
            _logger.debug('sriov_numvfs_check failed')
            return False
        if not br_link_mode_check(phys_dev):
            _logger.debug('br_link_mode_check failed')
            return False
    return True


def validate_domain_name(domain):
    """
    Checks if a domain name is already in use.  Returns False
    if it is, and True if not.

    Parameters
    ----------
    domain: str
        The domain name.

    Returns
    -------
        bool
             True on succes, False otherwise.
    """
    if domain in virt_utils.get_domains_name():
        return False
    return True


def validate_block_device(dev_orig):
    """
    Given a path, ensure that the path actually represents
    a device and that device is not currently assigned to
    a domain.

    Parameters
    ----------
    dev_orig: str
        The path to the block device.

    Returns
    -------
        bool
            True on success, False otherwise.
    """
    path_prefix = '/dev/disk/by-path'
    devices = lsblk.list_blk_dev()
    domains = virt_utils.get_domains_name()
    domain_disks = \
        {d: virt_utils.get_disks_from_domain(virt_utils.get_domain_xml(d))
         for d in domains}
    unused_devices = virt_utils.get_unused_block_devices(devices, domain_disks)
    dev = dev_orig

    if not dev_orig:
        # If not block device was provided, find one
        # that is not in use
        try:
            dev_orig = unused_devices.pop()
        except KeyError:
            _print_available_block_devices(unused_devices)
            return False
        dev = dev_orig

    try:
        os.stat(dev)
    except Exception:
        _logger.error("{} does not exist.".format(dev))
        _print_available_block_devices(unused_devices)
        return False

    # If the device is not already pointing to a consistent name,
    # convert it to one.
    if not dev.startswith(path_prefix) or dev == path_prefix:
        dev_orig = dev
        visited = []
        while True:
            try:

                dev = os.path.abspath(os.path.join(os.path.dirname(dev), os.readlink(dev)))
            except OSError as e:
                # Found  a real path.
                if e.errno == 22:
                    break
                _logger.error(
                        "Unexpected error occured while resolving {}.  Error reading {}: {}", dev_orig, dev, e)
                return False

            # Prevent infinite loops
            if dev in visited:
                _logger.error("Infinite loop encountered trying to resolve {}.", dev_orig)
                print_choices("Path:", visited + [dev])
                return False

            visited.append(dev)

        # Convert the resolved device into by-path format
        dev_map = get_block_devices()
        try:
            dev = dev_map[dev]
        except Exception:
            _logger.error("{} does not point to a block device.", dev_orig)
            _print_available_block_devices(unused_devices)
            return False

    # At this point, dev points to a file in /dev/disk/by-path'
    # and has been confirmed to exist.  It can be assumed
    # that the path is also a symlink
    dev_path = os.readlink(dev)
    dev_name = dev_path[dev_path.rfind('/') + 1:]
    if dev_name not in devices:
        _logger.error("{} is not a valid device", dev_orig)
        _print_available_block_devices(unused_devices)
        return False
    if virt_utils.block_device_has_mounts(devices[dev_name]):
        _logger.error("{} is in use by the host system", dev_orig)
        _print_available_block_devices(unused_devices)
        return False
    if not devices[dev_name].get('size'):
        _logger.error("{} is not a disk", dev_orig)
        _print_available_block_devices(unused_devices)
        return False

    for domain, disks in domain_disks.items():
        if dev in disks:
            _logger.error("{} is in use by \"{}\"", dev_orig, domain)
            _print_available_block_devices(unused_devices)
            return False

    return dev


def _print_available_block_devices(devices):
    """
    Display all available block devices.

    Parameters
    ----------
    devices: list
        List of available block devices.
    Returns
    -------
        No return value.
    """
    if not devices or len(devices) == 0:
        _logger.error("All block devices are currently in use.  Please attach a new block device via the OCI console.")
    else:
        print_choices("Available Block Devices:", devices)
