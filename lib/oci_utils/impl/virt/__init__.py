# oci-utils
#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.


def block_device_has_mounts(device):
    """
    Determines if a block device has filesystems mounted on any of its
    partitions.

    Parameters
    ----------
    device: str
        The block device.

    Returns
    -------
    bool:
        True if at least one partitions is mounted;
        False under any other conditions.
    """
    parts = device.get('partitions')
    if not parts:
        return False
    return sum([len(x['mountpoint']) for x in list(parts.values())]) != 0
