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
import logging
import xml.dom.minidom
import libvirt
import oci_utils.kvm.virt
from oci_utils.impl.row_printer import get_row_printer_impl

_logger = logging.getLogger("oci-utils.oci-kvm")

_create = 'create'
_destroy = 'destroy'
_pool = 'pool'
_create_pool = 'create-pool'
_list_pool = 'list-pool'
_create_network = 'create-network'
_delete_network = 'delete-network'


def _disk_size_in_gb(_string):
    """
    Convert string to int.

    Parameters
    ----------
    _string: str
        string containing a positive integer.

    Returns
    -------
        int: the integer value.
    """
    try:
        value = int(_string)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))
    if value <= 0:
        raise argparse.ArgumentTypeError('Size must be positive value')
    return value


def parse_args():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args()).

    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(description='Utility for creating and managing KVM virtual machines '
                                                 'on an OCI instance.')
    subparser = parser.add_subparsers(dest='mode')
    #
    create_parser = subparser.add_parser(_create,
                                         help='Create a new virtual machine.')
    create_parser.add_argument('-d', '--disk',
                               action='store',
                               type=str,
                               help='The path to the root disk of the VM.')
    create_parser.add_argument('-p', '--pool',
                               action='store',
                               type=str,
                               help='The name a of storage pool to be used for root disk.')
    create_parser.add_argument('-s', '--disk-size',
                               action='store',
                               type=_disk_size_in_gb,
                               help='The size of the disk in GB to be created when using storage pool.')
    create_parser.add_argument('-n', '--net',
                               action='append',
                               type=str,
                               help='The IP or name of the VNIC that should be attached to the VM.')
    create_parser.add_argument('-v', '--virtual-network',
                               action='append',
                               type=str,
                               help='The name of libvirt network to attach the guest to.')
    create_parser.add_argument('-D', '--domain',
                               action='store',
                               type=str,
                               help='The name of the virtual machine.',
                               required=True)
    create_parser.add_argument('-V', '--virt',
                               nargs=argparse.REMAINDER,
                               help='Additional arguments to provide to virt-install. '
                                    'All arguments that appear after this one will be passed unmodified into '
                                    'virt-install, even if they are arguments that oci-kvm would otherwise understand.',
                               required=True)
    #
    destroy_parser = subparser.add_parser(_destroy,
                                          help='Destroy an existing virtual machine.')
    destroy_parser.add_argument('-D', '--domain',
                                action='store',
                                type=str,
                                help='The name of the virtual machine.',
                                required=True)
    destroy_parser.add_argument('--destroy-disks',
                                action='store_true',
                                help='Also delete storage pool based disks.')
    destroy_parser.add_argument('-s', '--stop',
                                action='store_true',
                                default=False,
                                help='First stop the guess if it is running.')
    destroy_parser.add_argument('-f', '--force',
                                action='store_true',
                                default=False,
                                help='Forced operation, no gracefull shutdown.')
    #
    create_pool_parser = subparser.add_parser(_create_pool, help='Create a filesystem storage pool.')
    dbp_group = create_pool_parser.add_argument_group(title='disk pool',
                                                      description='The options for disk based storage pool.')
    dbp_group.add_argument('-d', '--disk',
                           action='store',
                           type=str,
                           help='The path to the root disk of the storage pool.')
    #
    nfsp_group = create_pool_parser.add_argument_group(title='NETFS pool',
                                                       description='The options for NETFS based storage pool.')
    nfsp_group.add_argument('-N', '--netfshost',
                            action='store',
                            type=str,
                            help='The name or IP of the NFS server.')
    nfsp_group.add_argument('-p', '--path',
                            action='store',
                            type=str,
                            help='The path of the NETFS resource.')
    create_pool_parser.add_argument('-n', '--name',
                                    action='store',
                                    type=str,
                                    help='The name of the pool.',
                                    required=True)
    #
    list_pool_parser = subparser.add_parser(_list_pool, help='Show the filesystem storage pools.')
    list_pool_parser.add_argument('--output-mode',
                                  choices=('parsable', 'table', 'json', 'text'),
                                  help='Set output mode.',
                                  default='table')
    #
    create_network_parser = subparser.add_parser(_create_network,
                                                 help='Create a libvirt network on an OCI vNIC.')
    create_network_parser.add_argument('-n', '--net',
                                       action='store',
                                       required=True, type=str,
                                       help='The IP of the VNIC used to build the network.')
    create_network_parser.add_argument('-N', '--network-name',
                                       action='store',
                                       required=True,
                                       type=str,
                                       help='The name of the network.')
    create_network_parser.add_argument('-B', '--ip-bridge',
                                       action='store',
                                       required=True,
                                       type=str,
                                       help='The bridge IP for virtual network address space.')
    create_network_parser.add_argument('-S', '--ip-start',
                                       action='store',
                                       required=True,
                                       type=str,
                                       help='The guest first IP range in virtual network address space.')
    create_network_parser.add_argument('-E', '--ip-end',
                                       action='store',
                                       required=True,
                                       type=str,
                                       help='The guest last IP range in virtual network address space.')
    create_network_parser.add_argument('-P', '--ip-prefix',
                                       action='store',
                                       required=True,
                                       type=str,
                                       help='The IP prefix to be used in virtual network.')
    #
    delete_network_parser = subparser.add_parser(_delete_network,
                                                 help='Delete a libvirt network on an OCI vNIC.')
    delete_network_parser.add_argument('-N', '--network-name',
                                       action='store',
                                       required=True, type=str,
                                       help='The name of the network.')
    delete_network_parser.add_argument('-y', '--yes',
                                       action='store_true',
                                       default=False,
                                       help='Assume yes')

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
        print("Either --disk or --pool option must be specified", file=sys.stderr)
        return 1

    if args.disk and args.pool:
        print("--disk and --pool options are exclusive", file=sys.stderr)
        return 1
    if args.pool and not args.disk_size:
        print("You must specify a disk size", file=sys.stderr)
        return 1

    if args.net and args.virtual_network:
        print("--net and --virtual_network option are exclusive", file=sys.stderr)
        return 1

    # insure unicity in networking options in BM case

    _all_net_names = set()
    if args.net:
        for n_name in args.net:
            if n_name not in _all_net_names:
                _all_net_names.add(n_name)
            else:
                print('Duplicate virtual network name [%s], ignore it', n_name)

    if '--network' in args.virt:
        sys.stderr.write("--network is not a supported option. Please retry without --network option.\n")
        return 1

    # sanity on extra arguments passed to virt-install(1)
    # some options do not create the guest but display information
    # this is wrongly interpreted as a succcess by underlying layers and we
    # may setup things by mistake
    _virt_install_extra = []
    for _a in args.virt:
        if _a not in ('--print-xml', '--version', '-h', '--help'):
            _virt_install_extra.append(_a)

    return oci_utils.kvm.virt.create(name=args.domain,
                                     root_disk=args.disk,
                                     pool=args.pool,
                                     disk_size=args.disk_size,
                                     network=list(_all_net_names),
                                     virtual_network=args.virtual_network,
                                     extra_args=_virt_install_extra)


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
    libvirtConn = libvirt.open(None)
    if libvirtConn is None:
        print('Cannot contact hypervisor', file=sys.stderr)
        return 1
    dom = None
    try:
        dom = libvirtConn.lookupByName(args.domain)
        if dom is None:
            print("Domain %s does not exist." % args.domain, file=sys.stderr)
            return 1
    except Exception as e:
        print("Failed looking for Domain %s: %s" % (args.domain, str(e)))
        return 1
    # from here , domain exists
    if dom.isActive():
        if not args.stop:
            _logger.error("Domain %s is running.  Only domains that are not running can be destroyed.", args.domain)
            libvirtConn.close()
            return 1

        shut_res = 0
        _logger.debug('Domain is running, stop it first with force ? %s', args.force)
        if args.force:
            shut_res = dom.destroyFlags()
        else:
            shut_res = dom.destroyFlags(libvirt.VIR_DOMAIN_DESTROY_GRACEFUL)

        libvirtConn.close()

        if shut_res != 0:
            _logger.error("Failed to stop domain")
            return 1

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

    if not args.yes:
        if not input('Really destroy this network ?').strip().lower() in ('y', 'yes'):
            return 1
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
    #
    # maximum length of network name is 14 chars, longer names will result in
    # a failure 'numerical result out of range' when creating the bridge.
    if len(args.network_name) > 14:
        _logger.error('Network name %s to long, max is 14 characters.', args.network_name)
        return 1
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
    Create a filesystem pool

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
    _sps = list()
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
        print("Must specify the remote resource path with the --path option", file=sys.stderr)
        return 1

    _pool_name = args.name
    if args.disk:
        return oci_utils.kvm.virt.create_fs_pool(args.disk, _pool_name)
    if args.netfshost:
        return oci_utils.kvm.virt.create_netfs_pool(args.netfshost, args.path, _pool_name)


def _format_size(size):
    """
    Format a size in bytes as a sting Tib, Gib, Mib.

    Parameters
    ----------
    size: int
        The size in bytes.

    Returns
    -------
        str: the size string.
    """
    size_mb = float(size)/1048576
    size_str = '%10.2f MiB' % size_mb
    if size_mb > 1024:
        size_gb = size_mb/1024
        size_str = '%10.2f GiB' % size_gb
    else:
        return size_str
    if size_gb > 1024:
        size_tb = size_gb/1024
        size_str = '%10.2f TiB' % size_tb
    return size_str.strip()


def _list_pool_vm(args):
    """
    List the filesystem pools.

    Parameters
    ----------
        args : namespace
            The parsed command line.
    Returns
    -------
        No return value.
    """
    _logger.debug('_list_pool_vm')

    pool_states = ['inactive',
                   'initializing',
                   'running',
                   'degraded',
                   'inaccessible']
    yes_no = ['no',
              'yes']

    conn = libvirt.open(None)
    try:
        _sps = list()
        if conn:
            _sps = conn.listAllStoragePools()
        else:
            _logger.error('Failed to contact hypervisor')
            raise ValueError('Failed to contact hypervisor.')
    except Exception as e:
        _logger.error('Failed to collect vm pool data: %s', str(e))
        raise ValueError('Failed to collect vm pool data.') from e
    finally:
        conn.close()

    if len(_sps) == 0:
        _logger.info('No filesystem pools found.')
        return

    _cols = ['Name', 'UUID', 'Autostart', 'Active', 'Persistent', 'Volumes', 'State', 'Capacity', 'Allocation', 'Available']
    _col_name = ['name', 'uuid', 'autostart', 'active', 'persistent', 'volumes', 'state', 'capacity', 'allocation', 'available']
    _cols_len = list()
    for col in _cols:
        _cols_len.append(len(col))
    _collen = { k:v for k, v in zip(_col_name, _cols_len)}
    #
    # format data and determine optimal lenght of fields.
    pool_data = list()
    for _sp in _sps:
        _sp_info = _sp.info()
        _sp_data = dict()
        # name
        _collen['name'] = max(len(_sp.name()), _collen['name'])
        _sp_data['name'] = _sp.name()
        # uuid
        _collen['uuid'] = max(len(_sp.UUIDString()), _collen['uuid'])
        _sp_data['uuid'] = _sp.UUIDString()
        # autostart
        _sp_data['autostart'] = yes_no[_sp.autostart()]
        # active
        _sp_data['active'] = yes_no[_sp.isActive()]
        # persistent
        _sp_data['persistent'] = yes_no[_sp.isPersistent()]
        try:
            # number of volumes
            _sp_data['volumes'] = _sp.numOfVolumes()
        except Exception as e:
            _logger.debug('Unable to collect number of volumes: %s', str(e))
            _sp_data['volumes'] = 0
        # total capacity
        _sp_data['capacity'] = _format_size(int(_sp_info[1]))
        _collen['capacity'] = max(len(_sp_data['capacity']), _collen['capacity'])
        # state
        _sp_data['state'] = pool_states[_sp_info[0]]
        _collen['state'] = max(len(_sp_data['state']), _collen['state'])
        # allocated space
        _sp_data['allocation'] = _format_size(int(_sp_info[2]))
        _collen['allocation'] = max(len(_sp_data['allocation']), _collen['allocation'])
        # available space
        _sp_data['available'] = _format_size(int(_sp_info[3]))
        _collen['available'] = max(len(_sp_data['available']), _collen['available'])
        #
        pool_data.append(_sp_data)

    _title = 'VM pool Information:'
    _columns = list()
    for i in range(len(_cols)):
        _columns.append([_cols[i], _collen[_col_name[i]] + 2, _col_name[i]])

    printerKlass = get_row_printer_impl(args.output_mode)
    printer = printerKlass(title=_title, columns=_columns)
    printer.printHeader()

    for _sp in pool_data:
        printer.rowBreak()
        printer.printRow(_sp)
    printer.printFooter()
    printer.finish()
    return


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
                   _list_pool: _list_pool_vm,
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
