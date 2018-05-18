#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

"""
Python wrapper around libvirt
"""

import os
import pty
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from .. import lsblk
from .. import metadata
from . import nic
from . import sysconfig
from . import utils
from . import virt_check

ipcmd = '/usr/sbin/ip'
virshcmd = '/usr/bin/virsh'

def _print_error(msg, *args):
    sys.stderr.write(msg.format(*args))
    sys.stderr.write('\n')

def _print_choices(header, choices, sep="\n  "):
    _print_error("{}{}{}", header, sep, sep.join(choices))

def _print_available_block_devices(devices):
    if not devices or len(devices) == 0:
        _print_error("All block devices are currently in use.  Please attach a new block device via the OCI console.")
    else:
        _print_choices("Available Block Devices:", devices)

def _print_available_vnics(vnics):
    if not vnics or len(vnics) == 0:
        _print_error("All OCI VNICs are currently in use.  Please create a new VNIC via the OCI console.")
    else:
        _print_choices("Available VNICs:", vnics)

def get_domains():
    """
    Returns the list of libvirt domain names
    """
    ret = []
    domains = utils._call_output([virshcmd, 'list', '--name', '--all']).splitlines()

    for d in domains:
        if len(d) > 0:
            ret.append(d)

    return ret

def get_domain_xml(domain):
    """
    Retrieves the XML representation of a libvirt domain as an ElementTree
    """
    return ET.fromstring(utils._call_output([virshcmd, 'dumpxml', domain]))

def get_domain_state(domain):
    r = utils._call_output([virshcmd, 'domstate', domain], False)
    if not r:
        return None
    return r.strip()

def get_domains_no_libvirtd():
    """
    Returns the list of libvirt domains.  Functions when libvirtd is
    not running.  If libvirtd *is* running, prefer get_domains().
    """
    ret = []
    try:
        for ent in os.listdir('/etc/libvirt/qemu'):
            # If this file ends in .xml, it represents a domain.  The file
            # itself will be named for the domain definition it contains.
            if ent[-4:] == ".xml":
                ret.append(ent[:-4])
    except:
        return []
    return ret

def get_domain_xml_no_libvirtd(domain):
    """
    Retrieves the XML representation of a libvirt domain as an ElementTree.
    Functions when libvirtd is not running.  If libvirtd *is* running,
    prefer get_domain_xml(domain).
    """
    try:
        return ET.parse('/etc/libvirt/qemu/{}.xml'.format(domain))
    except ET.ParseError:
        return None

def save_domain_xml(domain, domain_xml):
    """
    Writes the contents of domain_xml to the appropriate location,
    effectively updating the definition of the domain.  It would be unwise
    to invoked this method while libvirtd is running.
    """
    domain_xml.write('/etc/libvirt/qemu/{}.xml'.format(domain))

def get_interfaces_from_domain(domain_xml):
    """
    From the ElementTree of a domain, return a map of all network interfaces
    with the format {mac_address: device_name}
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
        ifaces[mac.attrib['address'].lower()] = source.attrib['dev']
    return ifaces

def get_disks_from_domain(domain_xml):
    """
    From the ElementTree of a domain, return the set of device
    names for all disks assigned to the domain
    """
    devices = domain_xml.find('./devices')
    if devices is None:
        return None

    devices[0]
    disks = []
    for disk in devices.findall('./disk'):
        src = disk.find('./source')
        try:
            disks.append(disk.find('./source').attrib['dev'])
        except:
            pass
    return set(disks)

def update_interfaces_for_domain(domain_xml, ifaces):
    """
    Updates the ElementTree for a domain, assigning a new interface
    name for an interface with a particular mac address for all
    provided interfaces.
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

def validate_domain_name(domain):
    """
    Checks if a domain name is already in use.  Returns False
    if it is, and True if not.
    """
    if domain in get_domains():
        return False
    return True

def get_block_devices():
    """
    Returns a dictionary of {'/dev/sbX': '/dev/disk/by-path/XXX'}, where
    the value of the key-value pair is a symlink to the key.
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
        print e
        return None
    return ret

def block_device_has_mounts(device):
    """
    Determines if a block device has filesystems mounted on any of its
    partitions.  Returns True if at least one partitions is mounted, or
    False under any other conditions.
    """
    parts = device.get('partitions')
    if not parts:
        return False
    return sum([len(x['mountpoint']) for x in parts.values()]) != 0

def get_unused_block_devices(devices, domain_disks):
    """
    Finds the set of block devices that are neither used by the host
    nor assigned to a libvirt domain.
    """
    used_devices = {}
    unused_devices = []

    for domain, disks in domain_disks.iteritems():
        for disk in disks:
            try:
                lnk = os.readlink(disk)
                dev = lnk[lnk.rfind('/')+1:]
                used_devices[dev] = True
            except:
                continue

    for device, data in devices.iteritems():
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

def validate_block_device(dev_orig):
    """
    Given a path, ensure that the path actually represents
    a device and that device is not currently assigned to
    a domain.
    """
    path_prefix = '/dev/disk/by-path'
    devices = lsblk.list()
    domains = get_domains()
    domain_disks = {d: get_disks_from_domain(get_domain_xml(d)) for d in domains}
    unused_devices = get_unused_block_devices(devices, domain_disks)
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
    except:
        _print_error("{} does not exist.".format(dev))
        _print_available_block_devices(unused_devices)
        return False

    # If the device is not already pointing to a consistent name,
    # convert it to one.
    if not dev.startswith(path_prefix) or dev == path_prefix:
        dev_orig = dev
        visited = []
        while True:
            try:
                lnk = os.readlink(dev)
                dev = os.path.abspath(os.path.join(os.path.dirname(dev), os.readlink(dev)))
            except OSError as e:
                # Found  a real path.
                if e.errno == 22:
                    break
                else:
                    _print_error("Unexpected error occured while resolving {}.  Error reading {}: {}", dev_orig, dev, e)
                    return False

            # Prevent infinite loops
            if dev in visited:
                _print_error("Infinite loop encountered trying to resolve {}.", dev_orig)
                _print_choices("Path:", visited + [dev])
                return False

            visited.append(dev)

        # Convert the resolved device into by-path format
        dev_map = get_block_devices()
        try:
            dev = dev_map[dev]
        except:
            _print_error("{} does not point to a block device.", dev_orig)
            _print_available_block_devices(unused_devices)
            return False

    # At this point, dev points to a file in /dev/disk/by-path'
    # and has been confirmed to exist.  It can be assumed
    # that the path is also a symlink
    dev_path = os.readlink(dev)
    dev_name = dev_path[dev_path.rfind('/')+1:]
    if dev_name not in devices:
        _print_error("{} is not a valid device", dev_orig)
        _print_available_block_devices(unused_devices)
        return False
    elif block_device_has_mounts(devices[dev_name]):
        _print_error("{} is in use by the host system", dev_orig)
        _print_available_block_devices(unused_devices)
        return False
    elif not devices[dev_name].get('size'):
        _print_error("{} is not a disk", dev_orig)
        _print_available_block_devices(unused_devices)
        return False

    for domain, disks in domain_disks.iteritems():
        if dev in disks:
            _print_error("{} is in use by \"{}\"", dev_orig, domain)
            _print_available_block_devices(unused_devices)
            return False

    return dev

def find_vnic_by_ip(ip_addr, vnics):
    """
    Given an ip address and a list of vnics, find the vnic that is assigned that ip
    """
    vnic = None
    for v in vnics:
        ip = v['privateIp']
        if ip == ip_addr:
            vnic = v
            break

    return vnic

def find_vnic_by_mac(mac, vnics):
    """
    Given a mac address and a list of vnics, find the vnic that is assigned that mac
    """
    vnic = None
    for v in vnics:
        m = v['macAddr'].lower()
        if mac == m:
            vnic = v
            break

    return vnic

def find_domain_by_mac(mac, domain_interfaces):
    """
    Given a mac address and a collection of domains and their
    network interfaces, find the domain that is assigned the
    interface with the desired mac address.
    """
    for d, i in domain_interfaces.iteritems():
        if i.get(mac):
            return d

    return None

def find_unassigned_vf_by_phys(phys, domain_interfaces, desired_mac):
    """
    Find an unused virtual function on the proper physical nic.  Attempt to
    re-use a virtual function if it is already assigned the appropriate mac
    address and is not in use by a domain.
    """
    configured = sysconfig.read_network_config()
    ifaces = nic.get_interfaces()
    virtFns = ifaces[phys]['virtfns']
    vfs = {virtFns[v]['mac']: (virtFns[v]['pciId'], v) for v in virtFns}

    # First, remove entries where the mac address is configured via sysconfig
    for c in configured:
        i = ifaces.get(c)
        if not i:
            continue
        mac = i['mac']
        if mac == "00:00:00:00:00:00":
            # Configured interfaces with zero as a mac address are almost
            # certainly loopback interfaces of some variety.  Not suitable
            # for a VM to use.
            continue
        vf = vfs.get(mac)
        if vf:
            del vfs[mac]

    # Next, remove entries where the mac address is already in use manually
    for d, i in domain_interfaces.iteritems():
        for mac in i:
            vf = vfs.get(mac)
            if vf:
                del vfs[mac]

    if len(vfs) == 0:
        return None, None

    # try to re-use a vf if it has the desired mac
    prev = vfs.get(desired_mac)
    if prev:
        return prev

    return vfs.values()[0]

def get_phys_by_index(vnic, vnics, nics):
    """
    Uses information stored in the OCI VNIC metadata to find the
    physical interface that a VNIC is associated with.
    """
    candidates = {}
    for v in vnics:
        if vnic['nicIndex'] == v['nicIndex']:
            candidates[v['macAddr'].lower()] = True

    for n, d in nics.iteritems():
        if d['physical'] and d['mac'] in candidates and not d.get('physfn'):
            return n
    return None

def find_free_vnics(vnics, interfaces):
    """
    Finds the set of VNICS that are not in use by an exsting
    guest or are being used by the host system.
    """
    domains = get_domains()
    domain_interfaces = {d: get_interfaces_from_domain(get_domain_xml(d)) for d in domains}
    iface_by_mac = {}
    phys_iface = {}
    ret = []

    for d, ifaces in domain_interfaces.iteritems():
        for i in ifaces:
            iface_by_mac[i] = d

    for i, d in interfaces.iteritems():
        if d.get('physfn'):
            continue
        phys_iface[d['mac']] = d

    for v in vnics:
        m = v['macAddr'].lower()
        if m in iface_by_mac:
            continue
        if m in phys_iface:
            continue
        ret.append(v['privateIp'])

    return set(ret)

def test_vnic_and_assign_vf(ip_addr, free_vnics):
    """
    Based on the IP address of an OCI VNIC, ensure that the VNIC is not already assigned to
    a virtual machine.  If that VNIC is available, find a free virtual function on the appropriate
    physical interface and return the necessary information.
    """
    vnics = metadata()['vnics']
    domains = get_domains()
    domain_interfaces = {d: get_interfaces_from_domain(get_domain_xml(d)) for d in domains}
    used_macs = []

    # First see if the given ip address belongs to a vnic
    vnic = find_vnic_by_ip(ip_addr, vnics)
    if vnic is None:
        _print_error("{} is not the IP address of a VNIC.", ip_addr)
        _print_available_vnics(free_vnics)
        return (False, False, False)

    # Next check that the ip address is not already assigned to a vm
    vnicMac = vnic['macAddr'].lower()
    dom = find_domain_by_mac(vnicMac, domain_interfaces)
    if dom:
        _print_error("{} is in use by \"{}\".", ip_addr, dom)
        _print_available_vnics(free_vnics)
        return (False, False, False)

    physNic = get_phys_by_index(vnic, vnics, nic.get_interfaces())

    vf_pci_id, vf_num = find_unassigned_vf_by_phys(physNic, domain_interfaces, vnicMac)
    if vf_pci_id is None:
        # This should never happen.  There are always at least as many virtual
        # Functions as there are potential creatable vnics
        _print_error("Could not find an unassigned virtual function on {}." +
                     "  Try using a VNIC on an alternate physical interface.",
                     physNic)
        return (False, False, False)

    return (vnic, vf_pci_id, vf_num)

def disable_spoof_check(device, vf, mac):
    """
    Turns spoofchk off for a specific virtual function
    """
    return utils._call([ipcmd, 'link', 'set', device, 'vf', vf, 'mac', mac, 'spoofchk', 'off'])

def find_vlan(domain):
    """
    Find the vlan id for the VNIC assigned to a domain
    """
    domain_ifaces = get_interfaces_from_domain(get_domain_xml(domain))
    vnics = metadata()['vnics']

    for m in domain_ifaces:
        for v in vnics:
            if m == v['macAddr'].lower():
                return int(v['vlanTag'])

    return 0

def get_domain_interfaces(domain):
    """
    Returns the list of all network interfaces that are assigned
    to the provided domain.
    """
    domain_ifaces = get_interfaces_from_domain(get_domain_xml(domain))
    vnics = metadata()['vnics']
    nics = nic.get_interfaces()

    ret = []
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
        for i, d in nics.iteritems():
            if d['mac'] == v['macAddr'].lower():
                full.append(i)

    return (set(directly_assigned), set(full))

def create_networking(vf_device, vlan, mac):
    vf_cfg = sysconfig.make_vf(vf_device, mac)
    vlan_cfg = sysconfig.make_vlan(vf_device, vlan, mac)

    cfg = {vf_cfg[0]: vf_cfg[1],
           vlan_cfg[0]: vlan_cfg[1]
          }
    sysconfig.write_network_config(cfg)
    return sysconfig.interfaces_up([vf_cfg[0], vlan_cfg[0]])

def destroy_networking(vf_device, vlan):
    # These configs are created just to harvest the interface
    # name.  The config itself is not relevant, and neither is
    # the final argument as that is the mac address.
    vf_name = sysconfig.make_vf(vf_device, '')[0]
    vlan_name = sysconfig.make_vlan(vf_device, vlan, '')[0]

    sysconfig.delete_network_config([vf_name, vlan_name])

def destroy_interface(name):
    """
    Deletes an ip link
    """
    return utils._call([ipcmd, 'link', 'delete', name])

def destroy_domain_vlan(domain):
    """
    Deletes the virtual network infrastructure for a domain
    """
    ifaces, all_ifaces = get_domain_interfaces(domain)

    to_del = []
    conf = sysconfig.read_network_config()
    for n, c in conf.iteritems():
        if c.get('DEVICE', '') in all_ifaces:
            to_del.append(n)

    sysconfig.delete_network_config(to_del)

def get_interface_by_pci_id(pci_id, interfaces):
    for i, d in interfaces.iteritems():
        if d['physical'] and d['pci'] == pci_id:
            return i
    return None

def create(name, root_disk, ip_addr, extra):
    """
    Creates a libvirt domain with the appropriate configuration and
    OCI resources.  Performs sanity checks to ensure that requested
    resources actually exist and are not assigned to other domains.
    """
    if not virt_check.validate_kvm_env():
        _print_error("Server does not have supported environment for guest creation")
        return 1

    if not validate_domain_name(name):
        _print_error("Domain name \"{}\" is already in use.".format(name))
        return 1

    root_disk = validate_block_device(root_disk)
    if not root_disk:
        return 1

    if '--network' in extra:
        _print_error("--network is not a supported option. Please retry without --network option.")
        return 1

    # If an ip address was not provided, pick one.
    interfaces = nic.get_interfaces()
    vnics = metadata()['vnics']
    free_vnics = find_free_vnics(vnics, interfaces)
    if not ip_addr:
        try:
            ip_addr = free_vnics.pop()
        except KeyError:
            _print_available_vnics(free_vnics)
            return 1
        else:
            print "Assigned IP address {}".format(ip_addr)

    vnic, vf, vf_num = test_vnic_and_assign_vf(ip_addr, free_vnics)
    if not vnic:
        return 1

    vfDev = get_interface_by_pci_id(vf, interfaces)
    if not create_networking(vfDev, vnic['vlanTag'], vnic['macAddr']):
        destroy_networking(vfDev, vnic['vlanTag'])
        return 1

    args = ['sudo', '/usr/bin/virt-install',
            '--hvm',
            '--name', name,
            '--cpu', 'host',
            '--disk', root_disk,
            '--network', 'type=direct,source={}.{},source_mode=passthrough,mac={},model=e1000'.format(vfDev, vnic['vlanTag'], vnic['macAddr'])] + extra

    if '--console' in extra:
        args.append('--noautoconsole')
        print  "Autoconsole has been disabled.  To view the console, issue 'virsh console {}'".format(name)

    dev_null = open('/dev/null', 'w')
    virt_install = subprocess.Popen(args, stdout=dev_null)

    # Check for errors
    while virt_install.poll() is None:
        time.sleep(.1)
        if name in get_domains():
            break

    if virt_install.returncode is not None and virt_install.returncode != 0:
        destroy_networking(vfDev, vnic['vlanTag'])
        return 1

    return 0

def destroy(name):
    """
    Destroys a libvirt domain by name, and de-allocates any assigned resources.
    """
    state = get_domain_state(name)
    if not state:
        domains = get_domains()
        _print_error("Domain {} does not exist.", name)
        if len(domains):
            _print_choices("Domains:", domains)
        else:
            _print_error("No domains are defined.")
        return 1
    elif state == "running":
        _print_error("Domain {} is running.  Only domains that are not running can be destroyed.", name)
        return 1

    destroy_domain_vlan(name)

    return subprocess.call(['sudo', '/usr/bin/virsh', 'undefine', name])
