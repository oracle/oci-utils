# oci-utils
#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import xml.etree.ElementTree as ET

import oci_utils.metadata
from . import block_device_has_mounts
from .. import VIRSH_CMD
from .. import sudo_utils
from ..network_helpers import get_interfaces

__all__ = ['get_domains_name', 'get_domain_state', 'get_domain_xml',
           'get_interfaces_from_domain', 'get_disks_from_domain', 'get_domains_no_libvirtd', 'get_domain_xml_no_libvirtd',
           'find_storage_pool_volume_by_path']


def get_domains_name():
    """
    Get all domains names.

    Returns
    -------
    list
        All domains names as list of string.
    """
    ret = []
    domains = sudo_utils.call_output([VIRSH_CMD, 'list', '--name', '--all'])
    if domains is not None:
        for d in domains.decode('utf-8').splitlines():
            if len(d) > 0:
                ret.append(d)

    return ret


def get_domain_state(domain):
    """
    Get the domain status.

    Parameters
    ----------
    domain : str
        The domain name.

    Returns
    -------
        str
            The domain state.
    """
    r = sudo_utils.call_output([VIRSH_CMD, 'domstate', domain], False)
    if not r:
        return None
    return r.strip()


def get_domain_interfaces(domain):
    """
    Get the list of all network interfaces that are assigned to the provided
    domain.

    Parameters
    ----------
    domain: str
        The domain name.

    Returns
    -------
        list
            The list of all network interfaces that are assigned to the
            provided domain.
    """
    domain_ifaces = get_interfaces_from_domain(
        get_domain_xml(domain))
    vnics = oci_utils.metadata.InstanceMetadata().refresh()['vnics']
    nics = get_interfaces()

    directly_assigned = []
    full = []
    for v in vnics:
        iface = domain_ifaces.get(v['macAddr'].lower())
        if not iface:
            continue

        # Found an assigned interface.  This interface should be a vlan
        # that is ultimately parented by some virtual function.  The
        # virtual function must be returned as well.  To keep things
        # simple, take the stupid approach and just add anything to the
        # list that shares a mac address
        directly_assigned.append(iface)
        full.append(iface)
        for i, d in nics.items():
            if d['mac'] == v['macAddr'].lower():
                full.append(i)

    return set(directly_assigned), set(full)


def get_domain_xml(domain):
    """
    Retrieves the XML representation of a libvirt domain as an ElementTree.

    Parameters
    ----------
    domain: str
        The domain name.

    Returns
    -------
        The Element Tree.
    """
    return ET.fromstring(sudo_utils.call_output([VIRSH_CMD, 'dumpxml', domain]))


def get_interfaces_from_domain(domain_xml):
    """
    From the ElementTree of a domain, get a map of all network interfaces.

    Parameters
    ----------
    domain_xml: ElementTree
        The xml representation of the domain.

    Returns
    -------
        dict
            All the network interfaces, as {mac_address: device_name}.
    """
    if domain_xml is None:
        return {}

    devices = domain_xml.find('./devices')
    if devices is None:
        return {}

    ifaces = {}
    for iface in devices.findall('./interface'):
        mac = iface.find('./mac')
        source = iface.find('./source')
        ifaces[mac.attrib['address'].lower()] = source.attrib.get('dev', '')
    return ifaces


def get_disks_from_domain(domain_xml):
    """
    From the ElementTree of a domain, get the set of device names for all
    disks assigned to the domain.

    Parameters
    ----------
    domain_xml: ElementTree
        The xml representation of the domain.

    Returns
    -------
        set
            The set of device names for all disks assigned to the domain.
    """
    devices = domain_xml.find('./devices')
    if devices is None:
        return None

    disks = []
    for disk in devices.findall('./disk'):
        try:
            disks.append(disk.find('./source').attrib['dev'])
        except Exception:
            pass
    return set(disks)


def get_unused_block_devices(devices, domain_disks):
    """
    Get the set of block devices that are neither used by the host nor
    assigned to a libvirt domain.

    Parameters
    ----------
    devices: dict
        The list of block devices.
    domain_disks: dict
        The list of block devices of the domain.

    Returns
    -------
        set
            The set of unused block devices.
    """
    used_devices = {}
    unused_devices = []

    for _, disks in domain_disks.items():
        for disk in disks:
            try:
                lnk = os.readlink(disk)
                dev = lnk[lnk.rfind('/') + 1:]
                used_devices[dev] = True
            except Exception:
                continue

    for device, data in devices.items():
        if not data.get('size'):
            # This check captures two cases: a block volume that lacks
            # a size, as well as block volumes that have zero size.
            continue
        if block_device_has_mounts(data):
            # If a block device has a mounted partition, that device
            # is being used by the host.
            continue
        if device in used_devices:
            # This device is in use by a domain.
            continue

        unused_devices.append("/dev/{}".format(device))

    return set(unused_devices)


def _not_used_update_interfaces_for_domain(domain_xml, ifaces):
    """
    Updates the ElementTree for a domain, assigning a new interface name for
    an interface with a particular mac address for all provided interfaces.

    Parameters
    ----------
    domain_xml: ElementTree
        The xml representation of the domain.
    ifaces: dict
        List of network interface.
    Returns
    -------
        No return value.
    """
    devices = domain_xml.find('./devices')
    if devices is None:
        return

    for iface in devices.findall('./interface'):
        mac = iface.find('./mac').attrib['address']
        new_name = ifaces.get(mac.lower())

        # Skip interfaces that aren't in the changeset
        if not new_name:
            continue

        source = iface.find('./source')
        source.set('dev', new_name)


def get_domains_no_libvirtd():
    """
    Get the list of libvirt domains.  Functions when libvirtd is not running.
     If libvirtd *is* running, prefer get_domains().

    Returns
    -------
        list
            The list of unused domains.
    """
    ret = []
    try:
        for ent in os.listdir('/etc/libvirt/qemu'):
            # If this file ends in .xml, it represents a domain.  The file
            # itself will be named for the domain definition it contains.
            if ent[-4:] == ".xml":
                ret.append(ent[:-4])
    except Exception:
        return []
    return ret


def get_domain_xml_no_libvirtd(domain):
    """
    Retrieves the XML representation of a libvirt domain as an ElementTree.
    Functions when libvirtd is not running.  If libvirtd *is* running,
    prefer get_domain_xml(domain).

    Parameters
    ----------
    domain: str
        The domain name.

    Returns
    -------
        ElementTree
            The xml representation of the domain.
    """
    try:
        return ET.parse('/etc/libvirt/qemu/{}.xml'.format(domain))
    except ET.ParseError:
        return None


def find_storage_pool_volume_by_path(conn, path):
    """
    find a libvirt Storage pool volume by path
    parameters
    ----------
      conn : libvirt.virConnect
            an active connection to hypervisor
      path : str
            volume path
    Returns:
        an instance of libvirt.virStorageVol or None if not found
    """
    for pool in conn.listAllStoragePools():
        for volume in pool.listAllVolumes():
            if volume.path() == path:
                return volume
    return None
