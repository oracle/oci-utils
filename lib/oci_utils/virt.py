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
import tempfile
import time
import xml.etree.ElementTree as ET

from . import lsblk
from . import metadata
from . import nic

ipcmd = '/usr/sbin/ip'
virshcmd = '/usr/bin/virsh'

def _call(cmd, log_output=True):
    """
    Executes a comand and returns the exit code
    """
    cmd.insert(0, 'sudo')
    try:
        subprocess.check_call(cmd, stderr=subprocess.STDOUT)
    except OSError as e:
        return 404
    except subprocess.CalledProcessError as e:
        if log_output:
            print "Error executing {}: {}\n{}\n".format(cmd, e.returncode, e.output)
        return e.returncode
    return 0

def _call_output(cmd, log_output=True):
    """
    Executes a command and returns stdout and stderr in a single string
    """
    cmd.insert(0, 'sudo')
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except OSError as e:
        return 404
    except subprocess.CalledProcessError as e:
        if log_output:
            print "Error execeuting {}: {}\n{}\n".format(cmd, e.returncode, e.output)
        return None
    return None

def get_domains():
    """
    Returns the list of libvirt domain names
    """
    ret = []
    domains = _call_output([virshcmd, 'list', '--name', '--all']).splitlines()

    for d in domains:
        if len(d) > 0:
            ret.append(d)

    return ret

def get_domain_xml(domain):
    """
    Retrieves the XML representation of a libvirt domain as an ElementTree
    """
    return ET.fromstring(_call_output([virshcmd, 'dumpxml', domain]))

def get_domain_state(domain):
    r = _call_output([virshcmd, 'domstate', domain], False)
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
    return ET.parse('/etc/libvirt/qemu/{}.xml'.format(domain))

def get_interfaces_from_domain(domain_xml):
    """
    From the ElementTree of a domain, return a map of all network interfaces
    with the format {mac_address: device_name}
    """
    devices = domain_xml.find('./devices')
    if devices is None:
        return None

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

def validate_domain_name(domain):
    """
    Checks if a domain name is already in use.  Returns False
    if it is, and True if not.
    """
    if domain in get_domains():
        print "Domain name \"{}\" is already in use".format(domain)
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
        dev_test = re.compile(r'/dev/[a-zA-Z]+')
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

def get_unused_block_device(devices, domain_disks):
    """
    Finds a block device that is neither assigned to an existing
    domain nor is in use by the host system.
    """
    used_devices = {}

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
            # This check captures two cases: a block volume not having
            # a size, as well as when that size is zero.
            continue
        if block_device_has_mounts(data):
            continue
        if device in used_devices:
            continue

        # No entity appears to be using this block device,
        # leaving it open to the new guest
        return '/dev/{}'.format(device)

    return None

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
    dev = dev_orig

    if not dev_orig:
        # If not block device was provided, find one
        # that is not in use
        dev_orig = get_unused_block_device(devices, domain_disks)
        if not dev_orig:
            print "All block devices currently in use"
            return False
        dev = dev_orig

    try:
        os.stat(dev)
    except:
        print "{} does not exist".format(dev)
        return False

    # If the device is not already pointing to a consistent name,
    # convert it to one.
    if not dev.startswith(path_prefix) or dev == path_prefix:
        dev_orig = dev
        visited = {}
        while True:
            try:
                lnk = os.readlink(dev)
                dev = os.path.abspath(os.path.join(os.path.dirname(dev), os.readlink(dev)))
            except OSError as e:
                # Found  a real path.
                if e.errno == 22:
                    break
                else:
                    print "Exception reading {}: {}".format(dev, e)
                    return False
            # Prevent infinite loops
            if dev in visited:
                print "Infinite loop while trying to resolve {}".format(dev_orig)
                return False

        # Convert the resolved device into by-path format
        dev_map = get_block_devices()
        try:
            dev = dev_map[dev]
        except:
            print "{} does not point to a block device".format(dev_orig)
            return False

    # At this point, dev points to a file in /dev/disk/by-path'
    # and has been confirmed to exist.  It can be assumed
    # that the path is also a symlink
    dev_path = os.readlink(dev)
    dev_name = dev_path[dev_path.rfind('/')+1:]
    if dev_name not in devices:
        print "{} is not a valid device".format(dev_orig)
        return False
    elif block_device_has_mounts(devices[dev_name]):
        print "{} is in use by the host system".format(dev_orig)
        return False
    elif not devices[dev_name].get('size'):
        print "{} does not represent a disk".format(dev_orig)
        return False

    for domain, disks in domain_disks.iteritems():
        if dev in disks:
            print "{} is in use by \"{}\"".format(dev, domain)
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
    ifaces = nic.get_interfaces()
    virtFns = ifaces[phys]['virtfns']
    vfs = {virtFns[v]['mac']: (virtFns[v]['pciId'], v) for v in virtFns}

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

def find_free_vnic(vnics, interfaces):
    """
    Finds a VNIC that is not in use by an existing guest or used
    by the host system.
    """
    domains = get_domains()
    domain_interfaces = {d: get_interfaces_from_domain(get_domain_xml(d)) for d in domains}
    iface_by_mac = {}
    for d, ifaces in domain_interfaces.iteritems():
        for i in ifaces:
            iface_by_mac[i] = d

    phys_iface = {}
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
        return v['privateIp']
    return None

def test_vnic_and_assign_vf(ip_addr):
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
        print "{} is not the IP address of a VNIC.  Choices are:\n{}".format(ip_addr, "\n".join([v['privateIp'] for v in vnics]))
        return (False, False, False)

    # Next check that the ip address is not already assigned to a vm
    vnicMac = vnic['macAddr'].lower()
    dom = find_domain_by_mac(vnicMac, domain_interfaces)
    if dom:
        print "{} is in use by \"{}\"".format(ip_addr, dom)
        return (False, False, False)

    physNic = get_phys_by_index(vnic, vnics, nic.get_interfaces())

    vf_pci_id, vf_num = find_unassigned_vf_by_phys(physNic, domain_interfaces, vnicMac)
    if vf_pci_id is None:
        print "Could not find an unassigned virtual function on {}".format(physNic)
        return (False, False, False)

    return (vnic, vf_pci_id, vf_num)

def disable_spoof_check(device, vf, mac):
    """
    Turns spoofchk off for a specific virtual function
    """
    return _call([ipcmd, 'link', 'set', device, 'vf', vf, 'mac', mac, 'spoofchk', 'off'])

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

def create_vlan(vf_device, vlan):
    """
    Creates a VLAN network interface parented by a virtual function.  In addition to that,
    sets the MTU for both interfaces to 9000, thus matching the physical interface.
    """
    # Do the hokey-pokey
    if _call([ipcmd, 'link', 'set', vf_device, 'down']):
        return 1
    if _call([ipcmd, 'link', 'set', vf_device, 'up']):
        return 1
    if _call([ipcmd, 'link', 'set', vf_device, 'down']):
        return 1
    if _call([ipcmd, 'link', 'set', vf_device, 'up']):
        return 1

    # MTU must match that of the parent device
    if _call([ipcmd, 'link', 'set', 'dev', vf_device, 'mtu', '9000']):
        return 1

    # Create VLAN, make sure its MTU matches that of the hardware, and bring the whole mess up
    if _call([ipcmd, 'link', 'add', 'link', vf_device, 'name', 'vlan{}'.format(vlan), 'type', 'vlan', 'id', str(vlan)]) != 0:
        return 1

    if _call([ipcmd, 'link', 'set', vf_device, 'up']):
        return 1

    if _call([ipcmd, 'link', 'set', 'dev', 'vlan{}'.format(vlan), 'mtu', '9000']):
        return 1

    return _call([ipcmd, 'link', 'set', 'vlan{}'.format(vlan), 'up'])

def destroy_vlan(vlan):
    """
    Deletes a VLAN network interface.
    """
    return _call([ipcmd, 'link', 'delete', 'vlan{}'.format(vlan)])

def destroy_domain_vlan(domain):
    """
    Deletes the VLAN network interface assigned to a domain
    """
    v = find_vlan(domain)
    if not v:
        return

    return destroy_vlan(v)

def attach_interface(name, port, slot, vf, vlan, mac):
    """
    Attaches a virtual function and VLAN network interface to a domain post-creation.
    """
    tmpl = ("<interface type='hostdev' managed='yes'>"
           " <source>"
           "  <address type='pci' domain='0x0000' bus='0x{}' slot='0x{}' function='0x{}'/>"
           " </source>"
           " <vlan><tag id='{}'/></vlan>"
           " <mac address='{}'/>"
           "</interface>")
    config = tmpl.format(port, slot, vf, vlan, mac)

    tmp = tempfile.NamedTemporaryFile()
    tmp.write(config)
    tmp.flush()

    r = _call([virshcmd, 'attach-device', name, tmp.name, '--config'])

    tmp.close()

    return r

def get_interface_by_pci_id(pci_id, interfaces):
    for i, d in interfaces.iteritems():
        if d['physical'] and d['pci'] == pci_id:
            return i
    return None

def construct_vlan(mac, vnics, domain_interfaces):
    interfaces = nic.get_interfaces()
    mac = mac.lower()

    # First find the vnic that has this mac address
    vnic = None
    for v in vnics:
        if v['macAddr'].lower() == mac:
            vnic = v
            break
    if not vnic:
        return False

    # Make sure a vlan doesn't already exist with the appropriate
    # mac and name
    vlanName = 'vlan{}'.format(str(vnic['vlanTag']))
    for i, d in interfaces.iteritems():
        if i == vlanName and mac == d['mac']:
            return True

    # Find the physical nic that the vnic is attached to
    physNic = get_phys_by_index(vnic, vnics, nic.get_interfaces())

    # Find a free vf to use
    vf_pci_id, vf_num = find_unassigned_vf_by_phys(physNic, domain_interfaces, mac)
    if vf_pci_id is None:
        print "Could not find an unassigned virtual function on {}".format(physNic)
        return False

    # Disable spoof check
    if disable_spoof_check(physNic, str(vf_num), mac):
        return False

    # Create the vlan
    vfDev = get_interface_by_pci_id(vf_pci_id, interfaces)
    return create_vlan(vfDev, str(vnic['vlanTag']))

#def create(name, cpus, mem, root_disk, ip_addr, media, vnc_password):
def create(name, root_disk, ip_addr, extra):
    """
    Creates a libvirt domain with the appropriate configuration and
    OCI resources.  Performs sanity checks to ensure that requested
    resources actually exist and are not assigned to other domains.
    """
    if not validate_domain_name(name):
        return 1

    root_disk = validate_block_device(root_disk)
    if not root_disk:
        return 1

    # If an ip address was not provided, pick one.
    interfaces = nic.get_interfaces()
    vnics = metadata()['vnics']
    if not ip_addr:
        ip_addr = find_free_vnic(vnics, interfaces)
        if not ip_addr:
            print "All VNICs are currently in use.  Please create a new one."
            return 1
        else:
            print "Assigned IP address {}".format(ip_addr)

    vnic, vf, vf_num = test_vnic_and_assign_vf(ip_addr)
    if not vnic:
        return 1

    physNic = get_phys_by_index(vnic, vnics, interfaces)

    if disable_spoof_check(physNic, str(vf_num), vnic['macAddr']):
        return 1

    vfDev = get_interface_by_pci_id(vf, interfaces)
    if create_vlan(vfDev, str(vnic['vlanTag'])):
        return 1

    args = ['sudo', '/usr/bin/virt-install',
            '--hvm',
            '--name', name,
            '--cpu', 'host',
            '--disk', root_disk,
            '--network', 'type=direct,source=vlan{},source_mode=passthrough,mac={},model=e1000'.format(vnic['vlanTag'], vnic['macAddr'])] + extra

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
        destroy_vlan(str(vnic['vlanTag']))
        return 1

    return 0

def destroy(name):
    """
    Destroys a libvirt domain by name, and de-allocates any assigned resources.
    """
    state = get_domain_state(name)
    if not state:
        print "Domain {} does not exist".format(name)
        return 1
    elif state == "running":
        print "Domain {} is running".format(name)
        return 1
    destroy_domain_vlan(name)
    return subprocess.call(['sudo', '/usr/bin/virsh', 'undefine', name])
