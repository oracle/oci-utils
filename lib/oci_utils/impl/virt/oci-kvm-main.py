#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
This utility automates the creation and configuration of KVM virtual
machines on Oracle Cloud Infrastructure instances.  See the manual
page for more information.
"""

import argparse
import sys
import os
import os.path
import libvirt
import oci_utils.kvm.virt
import xml.dom.minidom

_create = 'create'
_destroy = 'destroy'
_create_pool = 'create-pool'
_create_network = 'create-network'
_delete_network = 'delete-network'


def _disk_size_in_gb(_string):
    try:
        value = int(_string)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))
    if value <= 0:
        raise argparse.ArgumentTypeError('size must be positive value')
    return value


def parse_args():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args()).

    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(description='Utility for creating and '
                                                 'managing KVM virtual '
                                                 'machines on an OCI '
                                                 'instance.',
                                     add_help=False)
    subparser = parser.add_subparsers(dest='mode')
    create_parser = subparser.add_parser(_create,
                                         help='Create a new virtual machine')
    destroy_parser = subparser.add_parser(_destroy,
                                          help='Destroy an existing virtual '
                                               'machine')
    create_pool_parser = subparser.add_parser(_create_pool,
                                              help='Create a filesystem storage pool')
    create_network_parser = subparser.add_parser(_create_network,
                                                 help='Create a libvirt network on an OCI vNIC')
    delete_network_parser = subparser.add_parser(_delete_network,
                                                 help='Delete a libvirt network on an OCI vNIC')

    create_parser.add_argument('-d', '--disk', action='store', type=str,
                               help='Path to the root disk of the VM')
    create_parser.add_argument('-p', '--pool', action='store', type=str,
                               help='Name a of storage pool to be used for root disk')
    create_parser.add_argument('-s', '--disk-size', action='store', type=_disk_size_in_gb,
                               help='Size of the disk in GB to be created when using storage pool')
    create_parser.add_argument('-n', '--net', action='store', type=str,
                               help='IP or name of the VNIC that should be attached '
                                    'to the VM')
    create_parser.add_argument('-v', '--virtual-network', action='store', type=str,
                               help='The name of libvirt nework to attach the guest to')
    create_parser.add_argument('-D', '--domain', action='store', type=str,
                               help='Name of the virtual machine',
                               required=True)
    create_parser.add_argument('-V', '--virt', nargs=argparse.REMAINDER,
                               help='Additional arguments to provide to '
                                    'virt-install.  All arguments that appear '
                                    'after this one will be passed unmodified '
                                    'into virt-install, even if they are '
                                    'arguments that oci-kvm would otherwise '
                                    'understand.',
                               required=True)

    destroy_parser.add_argument('-D', '--domain', action='store', type=str,
                                help='Name of the virtual machine',
                                required=True)
    destroy_parser.add_argument('--destroy-disks', action='store_true',
                                help='Also delete storage pool based disks')

    dbp_group = create_pool_parser.add_argument_group(
        title='disk pool', description='Options for disk based storage pool')
    dbp_group.add_argument('-d', '--disk', action='store', type=str,
                           help='Path to the root disk of the storage pool')
    nfsp_group = create_pool_parser.add_argument_group(
        title='NETFS pool', description='Options for NETFS based storage pool')
    nfsp_group.add_argument('-N', '--netfshost', action='store', type=str,
                            help='name or IP of the NFS server')
    nfsp_group.add_argument('-p', '--path', action='store', type=str,
                            help='path of the NETFS resource')
    create_pool_parser.add_argument('-n', '--name', action='store', type=str,
                                    help='name of the pool', required=True)

    create_network_parser.add_argument('-n', '--net', action='store', required=True, type=str,
                                       help='IP of the VNIC used to build the network')
    create_network_parser.add_argument('-N', '--network-name', action='store', required=True, type=str,
                                       help='the name of the network')
    create_network_parser.add_argument('-B', '--ip-bridge', action='store', required=True, type=str,
                                       help='Bridge IP for virtual network address space')
    create_network_parser.add_argument('-S', '--ip-start', action='store', required=True, type=str,
                                       help='guest first IP range in virtual network address space')
    create_network_parser.add_argument('-E', '--ip-end', action='store', required=True, type=str,
                                       help='guest last IP range in virtual network address space')
    create_network_parser.add_argument('-P', '--ip-prefix', action='store', required=True, type=str,
                                       help='IP prefix to be used in virtual network')

    delete_network_parser.add_argument('-N', '--network-name', action='store', required=True, type=str,
                                       help='the name of the network')

    parser.add_argument('--help', action='help',
                        help='Display this help')

    return parser


def create_vm(args):
    """
    Create a KVM virtual machine.

    Parameters
    ----------
    args : namespace
        The command line namespace.

    Returns
    -------
        int
            The return value provided by the kvm virtual machine create
            call, 0 on success, 1 otherwise.
    """
    if not args.disk and not args.pool:
        print("either --disk or --pool option must be specified", file=sys.stderr)
        return 1

    if args.disk and args.pool:
        print("--disk and --pool options are exclusive", file=sys.stderr)
        return 1
    if args.pool and not args.disk_size:
        print("must specify a disk size", file=sys.stderr)
        return 1

    if args.net and args.virtual_network:
        print("--net and --virtual_network option are exclusive", file=sys.stderr)
        return 1

    if '--network' in args.virt:
        sys.stderr.write(
            "--network is not a supported option. Please retry without "
            "--network option.\n")
        return 1
    return oci_utils.kvm.virt.create(name=args.domain,
                                     root_disk=args.disk,
                                     pool=args.pool,
                                     disk_size=args.disk_size,
                                     network=args.net, virtual_network=args.virtual_network, extra_args=args.virt)


def destroy_vm(args):
    """
    Destroys a KVM virtual machine.

    Parameters
    ----------
    args :
        The command line namespace.

    Returns
    -------
        int
            The return value provided by the kvm virtual machine destroy
            call, 0 on success, 1 otherwise.
    """
    return oci_utils.kvm.virt.destroy(args.domain, args.destroy_disks)


def _delete_network_vm(args):
    """
    Deletes a libvirt network

    Parameters
    -----------
    args :
        dict as the one returned by argparse.ArgumentParser().parse_args()
        expected key :
            net : the IP of the vNIC to be used.
    Returns
    -------
        int
            The return value provided by the kvm storage pool create
            call, 0 on success, 1 otherwise.
    """
    libvirtConn = libvirt.openReadOnly(None)
    if libvirtConn is None:
        print('Cannot contact hypervisor', file=sys.stderr)
        return 1
    net = None
    try:
        net = libvirtConn.networkLookupByName(args.network_name)
    except libvirt.libvirtError:
        print('Cannot find network named [%s]' % args.network_name, file=sys.stderr)
        return 1
    print('Network found:\n')
    print(xml.dom.minidom.parseString(net.XMLDesc()).toprettyxml(indent=" ", newl=''))
    print('')

    if input('Really destroy this network ?').strip().lower() in ('y', 'yes'):
        return oci_utils.kvm.virt.delete_virtual_network(network_name=args.network_name)
    return 1


def _create_network_vm(args):
    """
    Creates a libvirt network

    Parameters
    -----------
    args :
        dict as the one returned by argparse.ArgumentParser().parse_args()

    Returns
    -------
        int
            The return value provided by the kvm storage pool create
            call, 0 on success, 1 otherwise.
    """
    # check network  name unicity
    conn = libvirt.openReadOnly(None)
    _vnets = []
    if conn:
        _vnets = [n.name() for n in conn.listAllNetworks() if n.name() == args.network_name]
        conn.close()
    else:
        print('Cannot contact hypervisor', file=sys.stderr)
        return 1
    if len(_vnets) != 0:
        print("Network with name [%s] already exists" % args.network_name, file=sys.stderr)
        return 1

    return oci_utils.kvm.virt.create_virtual_network(network=args.net,
                                                     network_name=args.network_name,
                                                     ip_bridge=args.ip_bridge,
                                                     ip_prefix=args.ip_prefix,
                                                     ip_start=args.ip_start,
                                                     ip_end=args.ip_end)


def _create_pool_vm(args):
    """
    create a filesystem pool

    Parameters
    ----------
    args :
        dict as the one returned by argparse.ArgumentParser().parse_args()

    Returns
    -------
        int
            The return value provided by the kvm storage pool create
            call, 0 on success, 1 otherwise.
    """
    # check storage pool name unicity
    conn = libvirt.open(None)
    _sps = []
    if conn:
        _sps = [sp for sp in conn.listAllStoragePools() if sp.name() == args.name]
        conn.close()
    else:
        print('Cannot contact hypervisor', file=sys.stderr)
        return 1

    if len(_sps) != 0:
        print("Storage pool with name [%s] already exists" % args.name, file=sys.stderr)
        return 1

    if args.disk and args.netfshost:
        print("--disk and --host option are exclusive", file=sys.stderr)
        return 1

    if not args.disk and not args.netfshost:
        print("Either --disk or --host must be specified.", file=sys.stderr)
        return 1

    if args.netfshost and not args.path:
        print("must specify the remote resource path with the --path option", file=sys.stderr)
        return 1

    _pool_name = args.name
    if args.disk:
        return oci_utils.kvm.virt.create_fs_pool(args.disk, _pool_name)
    if args.netfshost:
        return oci_utils.kvm.virt.create_netfs_pool(args.netfshost, args.path, _pool_name)


def main():
    """
    Main

    Returns
    -------
        int
            0 on success, 1 otherwise.
    """
    subcommands = {_create: create_vm,
                   _destroy: destroy_vm,
                   _create_pool: _create_pool_vm,
                   _create_network: _create_network_vm,
                   _delete_network: _delete_network_vm}

    parser = parse_args()
    args = parser.parse_args()
    if args.mode is None:
        parser.print_help()
        sys.exit(0)

    return subcommands[args.mode](args)


if __name__ == "__main__":
    sys.exit(main())
