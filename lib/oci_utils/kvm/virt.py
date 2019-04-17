#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Python wrapper around libvirt.
"""

import subprocess
import time
import libvirt
from xml.etree import ElementTree
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import SubElement

from . import nic
from ..impl import IP_CMD, SUDO_CMD, PARTED_CMD, MK_XFS_CMD, print_choices, print_error, VIRSH_CMD
from ..impl import sudo_utils
from ..impl.network_helpers import get_interfaces
from ..impl.virt import sysconfig, virt_check, virt_utils
from ..metadata import InstanceMetadata


def _print_available_vnics(vnics):
    """
    Print the list of available virtual network interfaces.

    Parameters
    ----------
    vnics : list()
        The list of virtual network interfaces to print.

    Returns
    -------
        No return value.
    """
    if not vnics or len(vnics) == 0:
        print_error("All OCI VNICs are currently in use. "
                    "Please create a new VNIC via the OCI console.")
    else:
        print_choices("Available VNICs:", vnics)


def find_vnic_by_ip(ip_addr, vnics):
    """
    Given an ip address and a list of vnics, find the vnic that is
    assigned that ip.

    Parameters
    ----------
    ip_addr : str
        The ip address.
    vnics : dict
        The list of virtual network interface cards.

    Returns
    -------
        The matching vnic on success, None otherwise.
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
    Given a mac address and a list of vnics, find the vnic that is
    assigned that mac

    Parameters
    ----------
    mac : str
        The MAC address.
    vnics : dict
        The list of virtual network interface cards.

    Returns
    -------
        The matching vnic on success, None otherwise.
    """
    vnic = None
    for v in vnics:
        m = v['macAddr'].lower()
        if mac == m:
            vnic = v
            break

    return vnic


def _find_vlan(mac, domain_interfaces):
    """
    Given a mac address and a collection of domains and their network
    interfaces, find the domain that is assigned the interface with the
    desired mac address.

    Parameters
    ----------
    mac : str
        The MAC address.
    domain_interfaces : dict
        The list of domain interfaces.

    Returns
    -------
        The domain
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

    Parameters
    ----------
    phys : str
        The physical network interface card.
    domain_interfaces : dict
        The list of domain interfaces.
    desired_mac : str
        The MAC address.

    Returns
    -------
        tuple
            The virtual function if found, None,None otherwise.
    """
    configured = sysconfig.read_network_config()
    ifaces = nic.get_interfaces()
    virt_fns = ifaces[phys].get('virt_fns', {})
    vfs = {virt_fns[v]['mac']: (virt_fns[v]['pci_id'], v) for v in virt_fns}

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
    Uses information stored in the OCI VNIC metadata to find the physical
    interface that a VNIC is associated with.

    Parameters
    ----------
    vnic : dict
        The virtual interface card name.
    vnics : dict
        The list of virtual interface cards.
    nics : dict
        The list of available network interface cards.

    Returns
    -------
        str
            The interface name if found, None otherwise.

    """
    candidates = {}
    for v in vnics:
        if vnic['nicIndex'] == v['nicIndex']:
            candidates[v['macAddr'].lower()] = True

    for n, d in nics.iteritems():
        if d['physical'] and d['mac'] in candidates and not d.get('physfn'):
            return n
    return None


def _get_intf_used_by_guest():
    """
    Get dict of intf used by guests
    Returns
    -------
     dict : {<domain name>: {<MAC>: <intf name>}}
    """
    return {d: virt_utils.get_interfaces_from_domain(
        virt_utils.get_domain_xml(d)) for d
        in virt_utils.get_domains_name()}


def find_free_vnics(vnics, interfaces):
    """
    Finds the set of VNICS that are not in use by an existing guest or are
    being used by the host system.
    Used only when running on BM instance
    Parameters
    ----------
    vnics : dict
        The virtual network interface cards.
    interfaces : dict
        The available interfaces.

    Returns
    -------
        set
           The set of free virtual network interface cards.
    """
    domain_interfaces = _get_intf_used_by_guest()
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
    Based on the IP address of an OCI VNIC, ensure that the VNIC is not
    already assigned to a virtual machine. If that VNIC is available, find a
    free virtual function on the appropriate physical interface and return
    the necessary information.

    Parameters
    ----------
        ip_addr : str
            The ip address.
        free_vnics: list()
            The list of virtual network interfaces.

    Returns
    -------
        tuple
            The virtual network interface, the pci id, the virtual function
            id on success, False,False,False otherwise.
    """
    vnics = InstanceMetadata()['vnics']
    domains = virt_utils.get_domains_name()
    domain_interfaces = {d: virt_utils.get_interfaces_from_domain(
        virt_utils.get_domain_xml(d)) for d in domains}

    # First see if the given ip address belongs to a vnic
    vnic = find_vnic_by_ip(ip_addr, vnics)
    if vnic is None:
        print_error("{} is not the IP address of a VNIC.", ip_addr)
        _print_available_vnics(free_vnics)
        return False, False, False

    # Next check that the ip address is not already assigned to a vm
    vnic_mac = vnic['macAddr'].lower()
    dom = _find_vlan(vnic_mac, domain_interfaces)
    if dom:
        print_error("{} is in use by \"{}\".", ip_addr, dom)
        _print_available_vnics(free_vnics)
        return False, False, False

    phys_nic = get_phys_by_index(vnic, vnics, get_interfaces())

    vf_pci_id, vf_num = find_unassigned_vf_by_phys(phys_nic, domain_interfaces,
                                                   vnic_mac)
    if vf_pci_id is None:
        # This should never happen.  There are always at least as many virtual
        # Functions as there are potential creatable vnics
        print_error(
            "Could not find an unassigned virtual function on {}. Try using a "
            "VNIC on an alternate physical interface.", phys_nic)
        return False, False, False

    return vnic, vf_pci_id, vf_num


def create_networking(vf_device, vlan, mac):
    """
    Create a networking device.

    Parameters
    ----------
    vf_device : str
        The device name.
    vlan : str
        The VLAN name.
    mac : str
        The MAC address.

    Returns
    -------
        The return value from starting the networking interface.
    """
    vf_cfg = sysconfig.make_vf(vf_device, mac)
    vlan_cfg = sysconfig.make_vlan(vf_device, vlan, mac)

    cfg = {vf_cfg[0]: vf_cfg[1],
           vlan_cfg[0]: vlan_cfg[1]
           }
    sysconfig.write_network_config(cfg)
    return sysconfig.interfaces_up([vf_cfg[0], vlan_cfg[0]])


def destroy_networking(vf_device, vlan):
    """
    Destroy the configuration of network device.

    Parameters
    ----------
    vf_device : str
        The virtual device name.
    vlan : str
        The VLAN name.

    Returns
    -------
        No return value.
    """
    # These configs are created just to harvest the interface
    # name.  The config itself is not relevant, and neither is
    # the final argument as that is the mac address.
    vf_name = sysconfig.make_vf(vf_device, '')[0]
    vlan_name = sysconfig.make_vlan(vf_device, vlan, '')[0]

    sysconfig.delete_network_config([vlan_name, vf_name])


def destroy_interface(name):
    """
    Deletes an ip link.

    Parameters
    ----------
    name : str
        The interface name.

    Returns
    -------
         The return value from the link delete command.
    """
    return sudo_utils.call([IP_CMD, 'link', 'delete', name])


def destroy_domain_vlan(domain):
    """
    Deletes the virtual network infrastructure for a domain.

    Parameters
    ----------
    domain : str
        The domain name.

    Returns
    -------
        No return value.
    """
    ifaces, all_ifaces = virt_utils.get_domain_interfaces(domain)

    to_del = []
    conf = sysconfig.read_network_config()
    for n, c in conf.iteritems():
        if c.get('DEVICE', '') in all_ifaces:
            to_del.append(n)

    sysconfig.delete_network_config(to_del)


def get_interface_by_pci_id(pci_id, interfaces):
    """
    Returns the list of network interfaces by pci id.

    Parameters
    ----------
    pci_id : str
        The pci id.
    interfaces : dict
        The name of of the network interface if a match is found,
        None otherwise.

    Returns
    -------

    """
    for i, d in interfaces.iteritems():
        if d['physical'] and d['pci'] == pci_id:
            return i
    return None


def create(**kargs):
    """
    Creates a libvirt domain with the appropriate configuration and
    OCI resources.  Performs sanity checks to ensure that requested
    resources actually exist and are not assigned to other domains.

    Parameters
    ----------
    kargs: dict
      arguments
         expected keys:
            name : str
               The domain name.
            root_disk : str
                The block device to be used as root disk.
            pool: str
                storage pool name
            disk_size:int
                root disk size in GB
            network : str
             The ip address or VNIC name
            extra_args : list()
             Extra options.

    Returns
    -------
        int
            0 on success, 1 otherwise.
    """

    _instance_shape = InstanceMetadata()['instance']['shape']
    _is_bm_shape = _instance_shape.startswith('BM')

    if not virt_check.validate_kvm_env(_is_bm_shape):
        print_error("Server does not have supported environment "
                    "for guest creation")
        return 1

    if not virt_check.validate_domain_name(kargs['name']):
        print_error("Domain name \"{}\" is already in use.".format(kargs['name']))
        return 1

    if kargs['root_disk']:
        _root_disk = virt_check.validate_block_device(kargs['root_disk'])
        if not _root_disk:
            return 1
        _disk_virt_install_args = _root_disk
    else:
        _disk_virt_install_args = 'pool=%s,size=%d' % (kargs['pool'], kargs['disk_size'])

    args = [SUDO_CMD, '/usr/bin/virt-install',
            '--name', kargs['name'],
            '--cpu', 'host',
            '--disk', _disk_virt_install_args]

    vnics = InstanceMetadata()['vnics']

    interfaces = get_interfaces()

    if _is_bm_shape:
        free_vnics = find_free_vnics(vnics, interfaces)
        if not kargs['network']:
            try:
                free_vnic_ip_addr = free_vnics.pop()
            except KeyError:
                _print_available_vnics(free_vnics)
                return 1
        else:
            free_vnic_ip_addr = kargs['network']
            print "Assigned IP address {}".format(free_vnic_ip_addr)

        vnic, vf, vf_num = test_vnic_and_assign_vf(free_vnic_ip_addr, free_vnics)
        if not vnic:
            return 1

        vf_dev = get_interface_by_pci_id(vf, interfaces)
        if not create_networking(vf_dev, vnic['vlanTag'], vnic['macAddr']):
            destroy_networking(vf_dev, vnic['vlanTag'])
            return 1
        args.append('--hvm')
        args.append('--network')
        args.append('type=direct,source={}.{},source_mode=passthrough,mac={},'
                    'model=e1000'.format(
                        vf_dev, vnic['vlanTag'], vnic['macAddr']))
    else:
        # VM shape case
        if kargs['network']:
            args.append('--network')
            args.append('type=direct,model=virtio,source=%s' % kargs['network'])
        else:
            # have to find one free interface. i.e not already used by a guest
            # and not the primary one. the VNICs returned by metadata service is sorted list
            # i.e the first one is the primary VNICs
            domains_nics = _get_intf_used_by_guest()
            intf_to_use = None
            for intf_name, intf_info in interfaces.iteritems():
                # skip non physical intf
                if not intf_info['physical']:
                    continue
                # if used by a guest, skip it
                if intf_name in [m.values()[0] for m in domains_nics.values()]:
                    continue
                # if primary one (primary VNIC), skip it
                if vnics[0]['macAddr'].upper() == intf_info['mac'].upper():
                    continue
                # we've found one
                intf_to_use = intf_name
                break

            if not intf_to_use:
                print_error('no free VNIC available')
                return 1

            args.append('--network')
            args.append('type=direct,model=virtio,source=%s' % intf_to_use)

    args.extend(kargs['extra_args'])

    if '--console' in kargs['extra_args']:
        args.append('--noautoconsole')
        print "Autoconsole has been disabled. To view the console, issue "
        "'virsh console {}'".format(kargs['name'])

    dev_null = open('/dev/null', 'w')
    virt_install = subprocess.Popen(args, stdout=dev_null)

    # Check for errors
    while virt_install.poll() is None:
        time.sleep(.1)
        if kargs['name'] in virt_utils.get_domains_name():
            break

    if virt_install.returncode is not None and virt_install.returncode != 0:
        if _is_bm_shape:
            destroy_networking(vf_dev, vnic['vlanTag'])
        return 1

    return 0


def destroy(name):
    """
    Destroys a libvirt domain by name, and de-allocates any assigned resources.

    Parameters
    ----------
        name : str
            The domain name.

    Returns
    -------
        int
            1 if domain does not exist or is running.
            Return value form virsh undefine.
    """
    state = virt_utils.get_domain_state(name)
    if not state:
        domains = virt_utils.get_domains_name()
        print_error("Domain {} does not exist.", name)
        if len(domains):
            print_choices("Domains:", domains)
        else:
            print_error("No domains are defined.")
        return 1
    elif state == "running":
        print_error(
            "Domain {} is running.  Only domains that are not running can be "
            "destroyed.",
            name)
        return 1

    destroy_domain_vlan(name)

    return subprocess.call([SUDO_CMD, VIRSH_CMD, 'undefine', name])


def create_netfs_pool(netfs_server, resource_path, name):
    """
    Create a libvirt netfs based storage pool.
    The target of the newly created pool is /oci-<pool name>

    Parameters
    ----------
        netfs_server : str
            IP or hostname of the netFS server
        resource_path : str
            the resource path
    Returns
    -------
        int
            return 0 on success, 1 otherwise
    """
    poolXML = Element('pool', type='netfs')
    pname = SubElement(poolXML, 'name')
    pname.text = name
    psource = SubElement(poolXML, 'source')
    SubElement(psource, 'host', name=netfs_server)
    SubElement(psource, 'dir', path=resource_path)
    SubElement(psource, 'format', type='nfs')
    ptarget = SubElement(poolXML, 'target')
    ppath = SubElement(ptarget, 'path')
    ppath.text = '/oci-%s' % name

    conn = libvirt.open(None)
    if conn is None:
        print_error('Failed to open connection to qemu:///system')
        return 1

    pool = conn.storagePoolDefineXML(ElementTree.tostring(poolXML), 0)
    if pool is None:
        print_error('Failed to create StoragePool object.')
        return 1
    try:
        pool.setAutostart(1)
        pool.build()
        pool.create()
    except libvirt.libvirtError, e:
        pool.undefine()
        print_error('Failed to setup the pool: %s' % e.get_error_message())
        return 1
    finally:
        conn.close()
    return 0


def create_fs_pool(disk, name):
    """
    Create a libvirt filesystem based storage pool.
    The target of the newly created pool is /oci-<pool name>

    Parameters
    ----------
        disk : str
            the disk name (device name) to use
        name : str
            the storage pool name.
    Returns
    -------
        int
            return 0 on success, 1 otherwise
    """

    # first cleanup the block device
    if subprocess.call([SUDO_CMD, PARTED_CMD, '--script', disk, 'mklabel', 'gpt']):
        print_error('Failed to label the block volume')
        return 1

    if subprocess.call([SUDO_CMD, PARTED_CMD, '--align', 'optimal', '--script', disk, 'mkpart', 'primary', 'xfs', '1MiB', '100%']):
        print_error('Failed to make primary partition on the block volume')
        return 1

    _new_part = "%s1" % disk

    if subprocess.call([MK_XFS_CMD, '-q', _new_part]):
        print_error('Failed to make xfs filesystem on new prtition')
        return 1

    poolXML = Element('pool', type='fs')
    pname = SubElement(poolXML, 'name')
    pname.text = name
    psource = SubElement(poolXML, 'source')
    # we create a primary partition: device will be named devname1 (i.e /dev/sda -> /dev/sda1)
    SubElement(psource, 'device', path=_new_part)
    ptarget = SubElement(poolXML, 'target')
    ppath = SubElement(ptarget, 'path')
    ppath.text = '/oci-%s' % name

    conn = libvirt.open(None)
    if conn is None:
        print_error('Failed to open connection to qemu:///system')
        return 1

    pool = conn.storagePoolDefineXML(ElementTree.tostring(poolXML), 0)
    if pool is None:
        print_error('Failed to create StoragePool object.')
        return 1
    try:
        pool.setAutostart(1)
        pool.build()
        pool.create()
    except libvirt.libvirtError, e:
        pool.undefine()
        print_error('Failed to setup the pool: %s' % e.get_error_message())
        return 1
    finally:
        conn.close()
    return 0
