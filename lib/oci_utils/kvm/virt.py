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
import logging
import libvirt
from xml.etree import ElementTree
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import SubElement
import logging
import StringIO

from . import nic
from ..impl import IP_CMD, SUDO_CMD, PARTED_CMD, MK_XFS_CMD, print_choices, print_error, VIRSH_CMD
from ..impl import sudo_utils
from ..impl.network_helpers import get_interfaces
from ..impl.network_helpers import add_route_table
from ..impl.network_helpers import delete_route_table
from ..impl.network_helpers import add_static_ip_route, remove_static_ip_routes
from ..impl.network_helpers import add_static_ip_rule, remove_static_ip_rules
from ..impl.network_helpers import add_firewall_rule, remove_firewall_rule
from ..impl.virt import sysconfig, virt_check, virt_utils
from ..metadata import InstanceMetadata

_logger = logging.getLogger('oci-utils.kvm.virt')

_logger = logging.getLogger('oci-utils.kvm.virt')


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


def create_networking(vf_device, vlan, mac, ip=None, prefix=None):
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
    ip : str (optional)
       the IP to eb set on the new intf
    prefix : int
       the prefix used to compute ip netmask
    Returns
    -------
        The return value from starting the networking interface.
    """
    vf_cfg = sysconfig.make_vf(vf_device, mac)
    if ip and prefix:
        vlan_cfg = sysconfig.make_vlan_with_ip(vf_device, vlan, mac, ip, prefix)
    else:
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
            virtual_network : str
              Name of libvirt virtual network (has precedence over 'network')
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

    if kargs['virtual_network']:
        args.append('--network')
        args.append('network=%s,model=e1000' % kargs['virtual_network'])
    else:
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
                        'model=e1000'.format(vf_dev, vnic['vlanTag'], vnic['macAddr']))
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
        print "Autoconsole has been disabled. To view the console, issue " \
              "'virsh console {}'".format(kargs['name'])

    _logger.debug('create: executing [%s]' % ' '.join(args))

    dev_null = open('/dev/null', 'w')
    virt_install = subprocess.Popen(args, stdout=dev_null)

    # Check for errors
    while virt_install.poll() is None:
        time.sleep(.1)
        if kargs['name'] in virt_utils.get_domains_name():
            break

    if virt_install.returncode is not None and virt_install.returncode != 0:
        if _is_bm_shape and not kargs['virtual_network']:
            destroy_networking(vf_dev, vnic['vlanTag'])
        return 1

    return 0


def destroy(name, delete_disks):
    """
    Destroys a libvirt domain by name, and de-allocates any assigned resources.

    Parameters
    ----------
        name : str
            The domain name.
        delete_disks : bool
            Do we also delette to storage pool based disks ?
    Returns
    -------
        int
            1 if domain does not exist or is running.
            Return value form virsh undefine.
    """

    libvirtConn = libvirt.open(None)
    if libvirtConn is None:
        print_error('Failed to open connection to qemu:///system')
        return 1
    dom = None
    try:
        dom = libvirtConn.lookupByName(name)
    except libvirt.libvirtError, e:
        domains = virt_utils.get_domains_name()
        print_error("Domain {} does not exist.", name)
        if len(domains):
            print_choices("Domains:", domains)
        else:
            print_error("No domains are defined.")
        libvirtConn.close()
        return 1

    # from here , domain exists
    if dom.isActive():
        print_error(
            "Domain {} is running.  Only domains that are not running can be "
            "destroyed.",
            name)
        libvirtConn.close()
        return 1

    # check that domains is on libvirt network or not
    # if so we have nothing to do about networking
    # interface XML is like the following . locate the network and check
    # if 'source' is of type network
    # <interface type='network'>
    #   <mac address='...'/>
    #   <source network='xxx' bridge='xxx'/>
    #   ...
    # </interface>
    _use_virtual_network = False
    try:
        raw_xml = ElementTree.fromstring(dom.XMLDesc())
        all_devices = raw_xml.findall('devices')
        # we expect only one 'devices' section
        net_intfs = [intf for intf in all_devices[0].findall('interface') if intf.get('type') == 'network']
        if len(net_intfs) > 0:
            vnet = net_intfs[0].findall('source')[0].get('network')
            if vnet:
                _logger.debug('destroy: use of virtual network [%s] detected' % vnet)
                _use_virtual_network = True
    except libvirt.libvirtError, e:
        print_error('Failed to get domain information: %s' % e.get_error_message())
        libvirtConn.close()
        return 1

    if not _use_virtual_network:
        _logger.debug('destroy: destroying network of domain')
        destroy_domain_vlan(name)

    if delete_disks:
        _logger.debug('looking for used libvirt volume')
        for device in raw_xml.findall('devices'):
            for disk in device.findall('disk'):
                for source in disk.findall('source'):
                    file_as_source = source.get('file')
                    if file_as_source:
                        _vol = virt_utils.find_storage_pool_volume_by_path(libvirtConn, file_as_source)
                        if _vol:
                            _logger.debug('libvirt volume found [%s]' % _vol.name())
                            try:
                                _vol.wipe(0)
                                _vol.delete(0)
                                _logger.debug('libvirt volume deleted')
                            except libvirt.libvirtError, e:
                                _logger.error('Cannot delete volume [%s]: %s' % (_vol.name(), str(e)))

    libvirtConn.close()

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
    if sudo_utils.call([PARTED_CMD, '--script', disk, 'mklabel', 'gpt']):
        print_error('Failed to label the block volume')
        return 1

    if sudo_utils.call([PARTED_CMD, '--align', 'optimal', '--script', disk, 'mkpart', 'primary', 'xfs', '1MiB', '100%']):
        print_error('Failed to make primary partition on the block volume')
        return 1

    _new_part = "%s1" % disk

    if sudo_utils.call([MK_XFS_CMD, '-f', '-q', _new_part]):
        print_error('Failed to make xfs filesystem on new prtition')
        return 1

    if sudo_utils.call([VIRSH_CMD, '--quiet', 'pool-define-as', '--name=%s'%name, '--type=fs', '--source-dev=%s'%_new_part,'--target=/oci-%s'%name]):
        print_error('Failed to define pool')
        return 1

    if sudo_utils.call([VIRSH_CMD, '--quiet','pool-build', name]):
        print_error('Failed to build pool')
        sudo_utils.call([VIRSH_CMD, 'pool-undefine', name])
        return 1

    if sudo_utils.call([VIRSH_CMD, '--quiet','pool-start', name]):
        sudo_utils.call([VIRSH_CMD, 'pool-undefine', name])
        print_error('Failed to build pool')
        return 1

    if sudo_utils.call([VIRSH_CMD, '--quiet', 'pool-autostart', name]):
        sudo_utils.call([VIRSH_CMD, 'pool-destroy', name])
        sudo_utils.call([VIRSH_CMD, 'pool-undefine', name])
        print_error('Failed to build pool')
        return 1

    return 0


def create_virtual_network(**kargs):
    """
    Creates a libvirt network on a secondary OCI vNIC

    Parameters
    ----------
    kargs: dict
      arguments
         expected keys:
            network : str
              The ip address of the VNIC
            vcn_cidr : str
            the CIDR block of the VCN of the VNIC used to build the network on
            network_name : str
              The name for the new virtual network
            ip_bridge :
               The bridge IP of virtual network
            ip_start
               The first IP of virtual network IP range dedicated to guest
            ip_end
               The last IP of virtual network IP range dedicated to guest
            ip_prefix
               The IP netmask of virtual network
    Returns
    -------
        StringIO.StringIO()
            An instance of StringIO populated with command lines which can be used to persist the network creation, None on failure
    """

    _persistence_script = StringIO.StringIO()
    _persistence_script.write('#/bin/bash\n')

    # get the given IP used to find vNIC to use
    _vnic_ip_to_use = kargs['network']

    _logger.debug('in create_virtual_network, given IP : %s ' % _vnic_ip_to_use)

    # get all vNIC of the current system
    _all_vnics = InstanceMetadata()['vnics']

    # get all current system network interfaces
    _all_system_interfaces = get_interfaces()

    libvirtConn = libvirt.open(None)
    if libvirtConn is None:
        print_error('Failed to open connection to qemu:///system')
        return None

    free_vnics = find_free_vnics(_all_vnics, _all_system_interfaces)

    # based on given PI adress, find free VF.
    vnic, vf, vf_num = test_vnic_and_assign_vf(_vnic_ip_to_use, free_vnics)
    if not vnic:
        _logger.debug('choosen vNIC is not free')
        return None
    _logger.debug('ready to write network configuration for (%s, %s, %s)' % (vnic, vf, vf_num))

    vf_dev = get_interface_by_pci_id(vf, _all_system_interfaces)
    _logger.debug('vf device for %s: %s' % (vf, vf_dev))
    if not create_networking(vf_dev,
                             vnic['vlanTag'],
                             vnic['macAddr'],
                             vnic['privateIp'],
                             int(vnic['subnetCidrBlock'].split('/')[1])):
        print_error('cannot create networking')
        destroy_networking(vf_dev, vnic['vlanTag'])
        return None

    _logger.debug('Networking succesfully created')

    # define a routing table for the new VF.
    _logger.debug('add new routing table [%s]' % vf_dev)
    add_route_table(vf_dev)

    # add routes and ip rules

    # ip route add default via <secondary VNIC default gateway> dev <VF network device>.<VLAN tag> table <VF network device>
    _persistence_script.write('# Add routes\n')
    routing_cmd = ['default', 'via']
    routing_cmd.append(vnic['virtualRouterIp'])
    routing_cmd.append('dev')
    routing_cmd.append('%s.%s' % (vf_dev, vnic['vlanTag']))
    routing_cmd.append('table')
    routing_cmd.append(vf_dev)
    (_c, _msg) = add_static_ip_route(
        script=_persistence_script,
        device='%s.%s' % (vf_dev, vnic['vlanTag']), *routing_cmd)
    if _c != 0:
        print_error('Failed to set ip default route: %s' % _msg)
        delete_route_table(vf_dev)
        destroy_networking(vf_dev, vnic['vlanTag'])
        return None

    #  ip rule add from <secondary VNIC IP address> lookup <VF network device>
    ip_rule_cmd = ['from']
    ip_rule_cmd.append(vnic['privateIp'])
    ip_rule_cmd.append('lookup')
    ip_rule_cmd.append(vf_dev)
    (_c, _msg) = add_static_ip_rule(script=_persistence_script,
                                    device=vf_dev, *ip_rule_cmd)
    if _c != 0:
        print_error('Failed to set ip rule: %s' % _msg)
        delete_route_table(vf_dev)
        destroy_networking(vf_dev, vnic['vlanTag'])
        return None

    # define the libvirt network
    netXML = Element('network')
    SubElement(netXML, 'name').text = kargs['network_name']
    SubElement(netXML, 'forward', dev='%s.%s' % (vf_dev, vnic['vlanTag']), mode='route')
    SubElement(netXML, 'bridge', name='%s0' % kargs['network_name'], stp='on', delay='0')
    ip = SubElement(netXML, 'ip', address=kargs['ip_bridge'], prefix=kargs['ip_prefix'])
    dhcp = SubElement(ip, 'dhcp')
    ip_range = SubElement(dhcp, 'range', start=kargs['ip_start'], end=kargs['ip_end'])

    _logger.debug('defining network as [%s]' % ElementTree.tostring(netXML))

    virtual_network = libvirtConn.networkDefineXML(ElementTree.tostring(netXML))
    if virtual_network is None:
        print_error('Failed to create virtual network')
        delete_route_table(vf_dev)
        destroy_networking(vf_dev, vnic['vlanTag'])
        return None
    _logger.debug('network defined')
    try:
        virtual_network.create()
        _logger.debug('network created')
    except libvirt.libvirtError, e:
        virtual_network.undefine()
        delete_route_table(vf_dev)
        destroy_networking(vf_dev, vnic['vlanTag'])
        print_error('Failed to setup the network: %s' % e.get_error_message())
        return None
    finally:
        if libvirtConn:
            libvirtConn.close()

    _persistence_script.write('# Start the KVM network\n')
    _persistence_script.write('/bin/virsh net-start --network %s\n' % kargs['network_name'])

    # Add a route for the KVM network to the local routing table for the secondary VNIC
    _persistence_script.write('# Add routes for KVM\n')
    routing_cmd = [kargs['vcn_cidr']]
    routing_cmd.append('dev')
    routing_cmd.append('%s0' % kargs['network_name'])
    routing_cmd.extend(['scope', 'link', 'proto', 'kernel', 'table'])
    routing_cmd.append(vf_dev)
    (_c, _msg) = add_static_ip_route(script=_persistence_script,
                                     device='%s0' % kargs['network_name'], *routing_cmd)
    if _c != 0:
        print_error('Failed to set ip route: %s' % _msg)
        delete_route_table(vf_dev)
        destroy_networking(vf_dev, vnic['vlanTag'])
        virtual_network.destroy()
        virtual_network.undefine()
        return None

    # Add a routing rule for the KVM network to the routing table for the secondary VNIC
    ip_rule_cmd = ['iif']
    ip_rule_cmd.append('%s0' % kargs['network_name'])
    ip_rule_cmd.append('lookup')
    ip_rule_cmd.append(vf_dev)
    (_c, _msg) = add_static_ip_rule(script=_persistence_script,
                                    device=vf_dev, *ip_rule_cmd)
    if _c != 0:
        print_error('Failed to set ip rule: %s' % _msg)
        delete_route_table(vf_dev)
        destroy_networking(vf_dev, vnic['vlanTag'])
        virtual_network.destroy()
        virtual_network.undefine()
        return None

    ip_rule_cmd = ['oif']
    ip_rule_cmd.append('%s0' % kargs['network_name'])
    ip_rule_cmd.append('lookup')
    ip_rule_cmd.append(vf_dev)
    (_c, _msg) = add_static_ip_rule(script=_persistence_script,
                                    device=vf_dev, *ip_rule_cmd)
    if _c != 0:
        print_error('Failed to set ip rule: %s' % _msg)
        delete_route_table(vf_dev)
        destroy_networking(vf_dev, vnic['vlanTag'])
        virtual_network.destroy()
        virtual_network.undefine()
        return None

    _logger.debug('add FW rules')
    # Add firewall rules for the address space of the KVM network to allow address rewriting
    _persistence_script.write('# Add firewall rules\n')
    fw_cmd = ['-t', 'nat', '-A', 'POSTROUTING', '-s']
    fw_cmd.append('%s/%s' % (kargs['ip_bridge'], kargs['ip_prefix']))
    fw_cmd.extend(['-d', '224.0.0.0/24', '-j', 'ACCEPT'])
    (_c, _msg) = add_firewall_rule(script=_persistence_script, *fw_cmd)
    if _c != 0:
        print_error('Failed to set firewall rule [%s]' % _msg)
        _logger.debug('Failed to execute [%s]' % ' '.join(fw_cmd))

    fw_cmd = ['-t', 'nat', '-A', 'POSTROUTING', '-s']
    fw_cmd.append('%s/%s' % (kargs['ip_bridge'], kargs['ip_prefix']))
    fw_cmd.extend(['-d', '255.255.255.255/32', '-j', 'ACCEPT'])
    (_c, _msg) = add_firewall_rule(script=_persistence_script, *fw_cmd)
    if _c != 0:
        print_error('Failed to set firewall rule [%s]' % _msg)
        _logger.debug('Failed to execute [%s]' % ' '.join(fw_cmd))

    fw_cmd = ['-t', 'nat', '-A', 'POSTROUTING', '-s']
    fw_cmd.append('%s/%s' % (kargs['ip_bridge'], kargs['ip_prefix']))
    fw_cmd.extend(['!', '-d', '%s/%s' % (kargs['ip_bridge'], kargs['ip_prefix']), '-j', 'MASQUERADE'])
    (_c, _msg) = add_firewall_rule(script=_persistence_script, *fw_cmd)
    if _c != 0:
        print_error('Failed to set firewall rule [%s]' % _msg)
        _logger.debug('Failed to execute [%s]' % ' '.join(fw_cmd))

    return _persistence_script


def delete_virtual_network(**kargs):
    """
    Deletes a libvirt network.

    Parameters
    ----------
    kargs: dict
      arguments
         expected keys:
            network_name : str
              The name for the new virtual network
    Returns
    -------
        int
            0 on success, 1 otherwise.
    """
    libvirtConn = libvirt.open(None)
    if libvirtConn is None:
        print_error('Cannot find network named [%s]' % kargs['network_name'])
        return 1
    net = None
    try:
        net = libvirtConn.networkLookupByName(kargs['network_name'])
    except libvirt.libvirtError:
        print_error('Cannot find network named [%s]' % kargs['network_name'])
        return 1

    root = ElementTree.fromstring(net.XMLDesc())
    _interface_elem = None
    # we have only one element per iteration
    for _f in root.findall('forward'):
        for _i in _f.findall('interface'):
            _interface_elem = _i
    if _interface_elem is None:
        print_error('Cannot find any interface in network XML description')
        return 1

    device_name = _interface_elem.get('dev')
    if device_name is None:
        print_error('Cannot find device information in interface node')
        return 1

    bridge_name = root.findall('bridge')[0].get('name')

    ip_bridge = root.findall('ip')[0].get('address')
    ip_prefix = root.findall('ip')[0].get('prefix')

    (vf_dev, vlanTag) = device_name.split('.')

    fw_cmd = ['-t', 'nat', '-A', 'POSTROUTING', '-s']
    fw_cmd.append('%s/%s' % (ip_bridge, ip_prefix))
    fw_cmd.extend(['-d', '224.0.0.0/24', '-j', 'ACCEPT'])
    remove_firewall_rule(*fw_cmd)

    fw_cmd = ['-t', 'nat', '-A', 'POSTROUTING', '-s']
    fw_cmd.append('%s/%s' % (ip_bridge, ip_prefix))
    fw_cmd.extend(['-d', '255.255.255.255/32', '-j', 'ACCEPT'])
    remove_firewall_rule(*fw_cmd)

    fw_cmd = ['-t', 'nat', '-A', 'POSTROUTING', '-s']
    fw_cmd.append('%s/%s' % (ip_bridge, ip_prefix))
    fw_cmd.extend(['!', '-d', '%s/%s' % (ip_bridge, ip_prefix), '-j', 'MASQUERADE'])
    remove_firewall_rule(*fw_cmd)

    remove_static_ip_routes(bridge_name)
    remove_static_ip_rules(vf_dev)
    remove_static_ip_routes(device_name)

    delete_route_table(vf_dev)

    if net.isActive():
        _logger.debug('stopping the virtual network')
        net.destroy()

    _logger.debug('unbdefining the virtual network')
    net.undefine()

    # do not needd that anymore
    libvirtConn.close()

    _logger.debug('destroying VF interfaces')
    destroy_networking(vf_dev, vlanTag)

    _logger.debug('Virtual network deleted')
    return 0
