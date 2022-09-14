#!/bin/python3
"""
Create a kvm guest on a kvm image.
"""
import argparse
import os
import random
import re
import socket
import stat
import subprocess
import sys
import uuid
from ipaddress import IPv4Address
from ipaddress import IPv4Network

ip_path = '/sbin/ip'
oci_network_path = '/bin/oci-network-config'
oci_iscsi_path = '/bin/oci-iscsi-config'
oci_kvm_path = '/bin/oci-kvm'

vnic_fields = ['state',
               'link',
               'status',
               'ipaddress',
               'vnic',
               'mac',
               'hostname',
               'subnet',
               'routerip',
               'namespace',
               'index',
               'vlantag',
               'vlan']

pool_fields = ['name',
               'uuid',
               'autostart',
               'active',
               'persistent',
               'volumes',
               'state',
               'capacity',
               'allocation',
               'available']

volume_attached_fields = ['iqn',
                          'name',
                          'ocid',
                          'persistentportal',
                          'currentportal',
                          'state',
                          'device',
                          'size']

volume_all_fields = ['name',
                     'size',
                     'attached',
                     'ocid',
                     'iqn',
                     'compartment',
                     'availabilitydomain']

ks_templates = {
    'ol7':
        {
            'passthrough': 'kickstart_direct_template_ol7',
            'bridge' : 'kickstart_bridge_template_ol7'
        },
    'ol8':
        {
            'passthrough': 'kickstart_direct_template_ol8',
            'bridge': 'kickstart_bridge_template_ol8'
        },
    'ol9':
        {
            'passthrough': 'kickstart_direct_template_ol9',
            'bridge': 'kickstart_bridge_template_ol9'
        }
}

user_name = 'guest'
user_password = 'fXV[E<,8'
root_password = 'fXV[E<,8'
disk_name_prefix = 'oci_kvm_vm_disk_'
pool_name_prefix = 'oci_kvm_image_pool_'
pool_size = '128'
disk_size = '51'
# vcpus = '2'
# memory = '4096'
network_name = 'oci-kvm-bridge'
bridge_ip = '192.168.100.1'
log_output = ''


def parse_args():
    """
    Parse command line parameters.

    Returns
    -------
        namespace parsed arguments.
    """
    parser = argparse.ArgumentParser(description='Create kvm guest on kvm image.')
    parser.add_argument('-d', '--distro',
                        action='store',
                        type=str,
                        choices=['ol7', 'ol8', 'ol9'],
                        required=True,
                        help='Distribution to be installed, [ol7|ol8|ol9]')
    parser.add_argument('-t', '--network-type',
                        action='store',
                        type=str,
                        choices=['bridge', 'passthrough'],
                        required=True,
                        help='Type of network connection to vm, bridged or passthrough')
    parser.add_argument('-s', '--storage-type',
                        action='store',
                        type=str,
                        choices=['disk', 'pool'],
                        required=True,
                        help='Type of disk for the vm.')
    parser.add_argument('-i', '--iso-file',
                        action='store',
                        type=str,
                        required=True,
                        help='iso file name as stored in /isos')
    parser.add_argument('-o', '--os-variant',
                        action='store',
                        type=str,
                        required=True,
                        help='os-variant for kvm.')
    parser.add_argument('-c', '--cpus',
                        action='store',
                        default='2',
                        type=str,
                        help='Number of vcpus, default is 2.')
    parser.add_argument('-m', '--memory',
                        action='store',
                        default='4',
                        type=str,
                        help='Amount of memory in GBs, default is 4.')
    parser.add_argument('-v', '--volume-size',
                        action='store',
                        default='51',
                        type=str,
                        help='Size of root volume in GBs, default is 51.')
    parser.add_argument('-p', '--pool-size',
                        action='store',
                        default='128',
                        type=str,
                        help='Size of disk pool in GBs, default is 128.')
    parser.add_argument('-b', '--bare-metal',
                        action='store_true',
                        help='Is a bare-metal host.')
    return parser


def list_to_str(somelist):
    """
    Convert a list to a string.

    Parameters
    ----------
    somelist: list
        the list.

    Returns
    -------
        str: the converted list.
    """
    return ' '.join(str(x) for x in somelist)


def run_cmd(cmd):
    """
    Run a command using subprocess.

    Parameters
    ----------
    cmd: list
        The command.

    Returns
    -------
        The command output.
    """
    print_par_val('execute', '%s' % list_to_str(cmd))
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()


def get_route_info():
    """
    Collect route info.

    Returns
    -------
        str: the route info
    """
    cmd = [ip_path, '-4', 'route', 'ls']
    return run_cmd(cmd)


def get_default_gw(route_info):
    """
    Get the default gateway.

    Parameters
    ----------
    route_info: str
        ip route ls output.

    Returns
    -------
        The default gateway.
    """
    for iface in route_info:
        if 'default via' in iface:
            return re.findall(r"([\w.][\w.]*'?\w?)", iface)[2]
    return None


def get_ip_address():
    """
    Get the ipv4 address.

    Returns
    -------
        str: the ipv4 address.
    """
    return socket.gethostbyname(socket.gethostname())


def get_def_interface(route_info):
    """
    Get the default ipv4 interface.

    Parameters
    ----------
    route_info: str
        ip route ls output.

    Returns
    -------
        the default network interface.
    """
    for iface in route_info:
        if 'default via' in iface:
            return re.findall(r"([\w.][\w.]*'?\w?)", iface)[4]
    return None


def get_nameserver():
    """
    Get the nameserver from resolv.conf.

    Returns
    -------
        str: the nameserver ipv4
    """

    with open('/etc/resolv.conf', 'r') as fn:
        resolv = fn.read()
    for rec in resolv.splitlines():
        if rec.startswith('nameserver'):
            return rec.split()[1]
    return None


def get_netmask(route_info, ifc):
    """
    Generate the netmask.

    Parameters
    ----------
    route_info: str
        ip route ls output.
    ifc: str
        interface.

    Returns
    -------
        str: the netmask.
    """
    for iface in route_info:
        if 'dev %s proto kernel' % ifc in iface:
            return IPv4Network(iface.split()[0]).netmask.compressed
    return None


def validate_os_variant(variant):
    """
    Verify if the supplied os variant is valid on this server.

    Parameters
    ----------
    variant: str
        The os short variant.

    Returns
    -------
        bool: True or False.
    """
    cmd = ['osinfo-query', '--fields', 'short-id', 'os']
    os_variants = [x.strip() for x in run_cmd(cmd)]
    return variant in os_variants


def create_vnic(name):
    """
    Create a vnic.

    Parameters
    ----------
    name: str
        vnic name

    Returns
    -------
        str: create vnic output.
    """
    cmd = [oci_network_path, 'attach-vnic', '--name', name]
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()


def create_disk(name, size):
    """
    Create a iscsi volume.

    Parameters
    ----------
    name: str
        volume name.
    size: str
        volume size in GB

    Returns
    -------
        str: create volume output.
    """
    cmd = [oci_iscsi_path, 'create',
           '--attach-volume',
           '--volume-name', name,
           '--size', size]
    return run_cmd(cmd)


def create_pool(name, size):
    """
    Create a kvm pool.

    Parameters
    ----------
    name: str
        pool name
    size:
        str: size in GB

    Returns
    -------
        str: create pool output
    """
    pool_uuid = get_pool_data('name', name, 'uuid')
    if pool_uuid is None:
        create_disk_data = create_disk(name, size)
        print_par_val('create disk data', create_disk_data)
        get_iqn_ocid(name)
        disk = get_volume_data('name', name, 'device')
        cmd = [oci_kvm_path, 'create-pool',
               '--disk', '/dev/' + disk,
               '--name', name]
        return run_cmd(cmd)
    return name


def bridge_exists(bridge_name):
    """
    Verify if bridge exists.

    Parameters
    ----------
    bridge_name: str
        name

    Returns
    -------
        bool
    """
    # cmd = ['/sbin/brctl', 'show']
    cmd = ['/usr/sbin/bridge', 'link', 'show']
    bridges = run_cmd(cmd)
    for bridge in bridges:
        if bridge_name in bridge:
            print_par_val('%s' % bridge_name, 'exist')
            return True
    print_par_val('%s' % bridge_name, 'does not exist')
    return False


def gen_ip_address(bridge_ipx):
    """
    Generate a random ip address in range.

    Parameters
    ----------
    bridge_ipx: str
        bridge

    Returns
    -------
        str: the ip address.
    """
    bridge_ip_int = int(IPv4Address(bridge_ipx))
    ip_low = bridge_ip_int + 100
    ip_high = bridge_ip_int + 200
    return str(IPv4Address(random.randint(ip_low, ip_high)))


def create_bridge(name, net, bridge_ipx):
    """
    Create a kvm bridge.

    Parameters
    ----------
    name: str
        name
    net: str
        ip address
    bridge_ipx: str
        ip address

    Returns
    -------
        str: create command output.
    """
    print_par_val('create bridge', 'name %s net %s bridge_ipx %s' % (name, net, bridge_ipx))
    net_link = get_vnic_data('vnic', name, 'link')
    if net_link is None:
        bridge_ip_int = int(IPv4Address(bridge_ipx))
        start_ip = str(IPv4Address(bridge_ip_int + 100))
        end_ip = str(IPv4Address(bridge_ip_int + 200))
        net_ip = get_vnic_data('vnic', net, 'ipaddress')
        cmd = [oci_kvm_path, 'create-network',
               '--network-name', name,
               '--net', net_ip,
               '--ip-bridge', bridge_ip,
               '--ip-start', start_ip,
               '--ip-end', end_ip,
               '--ip-prefix', '24']
        return run_cmd(cmd)
    print_par_val('net link', net_link)
    return net_link


def get_vnic_data(index, val, field):
    """
        Return val for vnic based on index.

        Parameters
        ----------
            index: str
                base field name.
            val: str
                base field value.
            field: str
                requested field value.

        Returns
        -------
            str: the requested value, None if absent.
    """
    print_par_val('get vnic data', 'index %s val %s field %s' % (index, val, field))
    cmd = [oci_network_path, 'show', '--details', '--output-mode', 'parsable']
    all_vnic_data = run_cmd(cmd)

    try:
        for vnic in all_vnic_data:
            vnic_list = vnic.split('#')
            # write_log('vnic list: %s' % vnic_list)
            if index not in vnic_fields or field not in vnic_fields:
                return None
            if vnic_list[vnic_fields.index(index)] == val:
                return vnic_list[vnic_fields.index(field)]
    except IndexError:
        return None
    return None


def get_pool_data(index, val, field):
    """
    Return val for volume based on index.

    Parameters
    ----------
    index: str
        base field name.
    val: str
        base field value.
    field: str
        requested field value.

    Returns
    -------
        str: the requested value, None if absent.
    """
    print_par_val('get pool data', 'index %s val %s field %s' % (index, val, field))
    cmd = [oci_kvm_path, 'list-pool', '--output-mode', 'parsable']
    all_pool_data = run_cmd(cmd)

    for pool in all_pool_data:
        pool_list = pool.split('#')
        # write_log('pool list: %s' % pool_list)
        if index not in pool_fields or field not in pool_fields:
            return None
        if pool_list[pool_fields.index(index)] == val:
            return pool_list[pool_fields.index(field)]
    return None


def get_volume_data(index, val, field):
    """
    Return val for volume based on index.

    Parameters
    ----------
    index: str
        base field name.
    val: str
        base field value.
    field: str
        requested field value.

    Returns
    -------
        str: the requested value, None if absent.
    """
    print_par_val('get volume data', 'index %s val %s field %s' % (index, val, field))
    cmd = [oci_iscsi_path, 'show', '--detail', '--no-truncate', '--output-mode', 'parsable', '--all']
    all_volume_data = run_cmd(cmd)

    for vol in all_volume_data:
        vol_list = vol.split('#')
        if vol_list[2].startswith('ocid1.'):
            if index not in volume_attached_fields or field not in volume_attached_fields:
                continue
            # is a volume in the 'attached' list
            if vol_list[volume_attached_fields.index(index)] == val:
                return vol_list[volume_attached_fields.index(field)]
        else:
            if index not in volume_all_fields or field not in volume_all_fields:
                continue
            # is a volume in the 'all' list
            if vol_list[volume_all_fields.index(index)] == val:
                return vol_list[volume_all_fields.index(field)]
    return None


def create_kickstart(name, template, parameters):
    """
    Generate a kickstart file from a template.

    Parameters
    ----------
    name: str
        kickstart path
    template: str
        Template path
    parameters: dict
        values to replace
    Returns
    -------
        int: number of characters written.
    """
    with open(template, 'r') as ksf:
        ks_template_data = ksf.read()

    for pattern, value in parameters.items():
        ks_config_data = ks_template_data.replace(pattern, value)
        ks_template_data = ks_config_data

    with open(name, 'w') as ksc:
        ret = ksc.write(ks_config_data)
    return ret


def get_iqn_ocid(name):
    """
    Get iqn and ocid from volume with name name.

    Parameters
    ----------
    name: str
        Volume name.

    Returns
    -------
        No return value.
    """

    iqn = get_volume_data('name', name, 'iqn')
    print_par_val('volume iqn', iqn)
    ocid = get_volume_data('name', name, 'ocid')
    print_par_val('volume ocid', ocid)


def print_par_val(parameter, value):
    """
    Formatted output and log.

    Parameters
    ----------
    parameter: str
        key
    value: str
        value

    Returns
    -------
        No return value
    """
    global log_output
    logdata = '%25s: %s' % (parameter, value)
    print(logdata)
    write_log(logdata)


def write_log(msg):
    """
    Write a line to the logfile.

    Parameters
    ----------
    msg: str
        The message.

    Returns
    -------
        No return value
    """
    with open(log_output, 'a') as log:
        log.write('%s\n' % msg)
        log.flush()


def main():
    """
    main

    Returns
    -------
        No return value.
    """
    global log_output
    #
    parser = parse_args()
    args = parser.parse_args()
    #
    memory = str(int(args.memory) * 1024)
    vcpus = args.cpus
    disk_size = args.volume_size
    pool_size = args.pool_size
    #
    # hostname
    hostname = 'guest-' + uuid.uuid4().hex[:6]
    log_output = '/var/tmp/' + hostname + '.log'
    #
    # verify if iso exists
    iso_file = '/isos/' + args.iso_file
    if not os.path.exists(iso_file):
        sys.exit('%s not found' % iso_file)
    print_par_val('iso file', iso_file)
    print_par_val('hostname', hostname)
    #
    # verify os variant
    if not validate_os_variant(args.os_variant):
        sys.exit('%s is not a valid os variant.' % args.os_variant)
    print_par_val('os variant', args.os_variant)
    #
    print_par_val('network type', args.network_type)
    print_par_val('network type', args.storage_type)
    #
    # verify ks template exists
    ks_template = 'templates/%s' % ks_templates[args.distro][args.network_type]
    if not os.path.exists(ks_template):
        sys.exit('template %s does not exist.' % ks_template)
    print_par_val('kickstart template', ks_template)
    #
    domain_cmd = ['--domain', hostname]
    print_par_val('domain cmd', list_to_str(domain_cmd))
    #
    # kickstart file
    ks_file = hostname + '_ks.cfg'
    print_par_val('kickstart file', ks_file)
    route_info = get_route_info()
    # print_par_val('route_info', route_info)
    #
    # default interface
    default_intf = get_def_interface(route_info)
    print_par_val('default interface', default_intf)
    #
    # default gateway
    default_gw = get_default_gw(route_info)
    print_par_val('gateway', default_gw)
    #
    # primary ip address
    this_ip = get_ip_address()
    print_par_val('ip address', this_ip)
    #
    # network mask
    netmask = get_netmask(route_info, default_intf)
    print_par_val('netmask', netmask)
    #
    # nameserver
    nameserver = get_nameserver()
    print_par_val('nameserver', nameserver)
    #
    # vnic
    vnic_name='vnic_' + uuid.uuid4().hex[:4]
    print_par_val('vnic name', vnic_name)
    #
    # if bridged, create network, if not already exists.
    if args.network_type == 'bridge':
        if not bridge_exists(network_name):
            #
            # vnic ip
            vnic_output = create_vnic(vnic_name)
            print_par_val('vnic_output', list_to_str(vnic_output))
            vnic_ip = get_vnic_data('vnic', vnic_name, 'ipaddress')
            print_par_val('vnic_ip', vnic_ip)
            create_bridge_output = create_bridge(network_name, vnic_name, bridge_ip)
            print_par_val('create bridge', list_to_str(create_bridge_output))
        default_gw = bridge_ip
        vnic_ip = gen_ip_address(bridge_ip)
        nameserver = bridge_ip
        netmask = '255.255.255.0'
        print_par_val('guest network', '%s %s %s %s' % (vnic_ip, netmask, default_gw, nameserver))
        net_cmd = ['--virtual-network', network_name]
    #
    # passthrough
    elif args.network_type == 'passthrough':
        #
        # vnic link
        vnic_output = create_vnic(vnic_name)
        print_par_val('vnic_output', list_to_str(vnic_output))
        vnic_link = get_vnic_data('vnic', vnic_name, 'link')
        print_par_val('vnic_link', vnic_link)
        # net_cmd = ['--net', vnic_link]
        #
        # vnic ip
        vnic_ip = get_vnic_data('vnic', vnic_name, 'ipaddress')
        print_par_val('vnic_ip', vnic_ip)
        #
        # network option
        net_cmd = ['--net', vnic_ip] if args.bare_metal else ['--net', vnic_link]
    #
    # false
    else:
        sys.exit('Invalid network type')
    print_par_val('network cmd', list_to_str(net_cmd))
    #
    # if disk, create disk
    if args.storage_type == 'disk':
        name = disk_name_prefix + uuid.uuid4().hex[:6]
        create_disk_data = create_disk(name, disk_size)
        print_par_val('create disk', list_to_str(create_disk_data))
        get_iqn_ocid(name)
        disk = get_volume_data('name', name, 'device')
        disk_name = '/dev/' + disk
        print_par_val('device name', disk_name)
        storage_cmd = ['--disk', disk_name]
        disk_cmd = []
        pool_name = ' '
    #
    # create pool
    else:
        pool_name = pool_name_prefix + uuid.uuid4().hex[:6]
        create_pool_data = create_pool(pool_name, pool_size)
        print_par_val('create pool', list_to_str(create_pool_data))
        storage_cmd = ['--pool', pool_name]
        disk_cmd = ['--disk-size', disk_size]
    print_par_val('storage cmd', list_to_str(storage_cmd))
    print_par_val('disk cmd', list_to_str(disk_cmd))
    #
    # root password
    print_par_val('root password', root_password)
    #
    # user name
    print_par_val('user_name', user_name)
    #
    # user password
    print_par_val('user_password', user_password)
    #
    # pool name
    print_par_val('pool name', pool_name)
    #
    # create kickstart file
    params = {
        '__DEVICE__': 'ens2',
        '__GATEWAY__': default_gw,
        '__IPADDRESS__': vnic_ip,
        '__NAMESERVER__': nameserver,
        '__NETMASK__': netmask,
        '__HOSTNAME__': hostname,
        '__ROOTPASSWORD__': root_password,
        '__USERNAME__': user_name,
        '__USERPASSWORD__': user_password
    }
    # ks_template = 'templates/%s' % ks_templates[args.distro][args.network_type]
    # print_par_val('kickstart template', ks_template)
    create_kickstart(ks_file, ks_template, params)
    ks_path = os.getcwd() + '/' + ks_file
    print_par_val('kickstart file path', ks_path)
    virt_cmd = ['--virt', '--vcpus', vcpus, '--memory', memory, '--boot', 'cdrom,hd']
    print_par_val('virt cmd', list_to_str(virt_cmd))
    iso_cmd = ['--location', '/isos/' + args.iso_file]
    print_par_val('iso cmd', list_to_str(iso_cmd))
    console_cmd = ['--nographics', '--console', 'pty,target_type=serial', '--console', 'pty,target_type=virtio']
    print_par_val('console cmd', list_to_str(console_cmd))
    os_cmd = ['--os-variant', args.os_variant]
    print_par_val('os variant', list_to_str(os_cmd))
    ks_cmd = ['--initrd-inject', ks_path]
    print_par_val('ks cmd', list_to_str(ks_cmd))
    ks_str = 'inst.ks=file:/%s' % ks_file
    extra_args = ['--extra-args="%s"' % ks_str, '--extra-args="console=ttyS0,115200n8"']
    print_par_val('extra args', list_to_str(extra_args))
    autoconsole_cmd = ['--noautoconsole']
    print_par_val('autoconsole', list_to_str(autoconsole_cmd))
    create_vm_cmd = [oci_kvm_path, 'create'] \
                    + domain_cmd \
                    + disk_cmd \
                    + storage_cmd \
                    + net_cmd \
                    + virt_cmd \
                    + iso_cmd \
                    + autoconsole_cmd \
                    + console_cmd \
                    + os_cmd \
                    + ks_cmd \
                    + extra_args
    print_par_val('create vm', list_to_str(create_vm_cmd))

    try:
       createvm = open(hostname, 'w')
       createvm.write('%s \n'% list_to_str(create_vm_cmd))
       createvm.write('virsh console %s\n' % hostname)
       os.chmod(hostname, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
    except Exception as e:
       print('*** ERROR *** failed to write to %s' % hostname)
    finally:
        createvm.close()


    # create_vm = run_cmd(create_vm_cmd)
    # print_par_val('vm create', list_to_str(create_vm))
    print('\n run bash %s/%s\n' % (os.getcwd(), hostname))


if __name__ == "__main__":
    sys.exit(main())
