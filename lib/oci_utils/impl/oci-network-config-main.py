#
# Copyright (c) 2017, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
This utility assists with configuring network interfaces on Oracle Cloud
Infrastructure instances.  See the manual page for more information.
"""

import argparse
import logging
import os
import sys

import oci_utils
import oci_utils.oci_api
from oci_utils.vnicutils import VNICUtils
from oci_utils.impl.row_printer import (get_row_printer_impl, TablePrinter, TextPrinter)

_logger = logging.getLogger("oci-utils.oci-network-config")

def uniq_item_validator(value):
    """
    Validates unicity by checking that value not already in the list

    Parameter
    ---------
     value : str , option's value
    """
    already_seen = getattr(uniq_item_validator,"_item_seen",[])

    if value in already_seen:
        raise argparse.ArgumentTypeError("Invalid arguments: item both included and excluded: %s" % value)
    already_seen.append(value)
    setattr(uniq_item_validator,"_item_seen",already_seen)

    return value
def vnic_oci_validator(value):
    """
    validate than value passed is a VNIC ocid
    parameter:
    ----------
            value : option's value as str
    """
    if value.startswith('ocid1.vnic.oc'):
        return value
    raise argparse.ArgumentTypeError("Invalid arguments: invalid VNIC ocid : %s" % value)

def get_arg_parser():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args()).

    Returns
    -------
        The argparse namespace.
    """
    parser = argparse.ArgumentParser(description='Utility for configuring '
                                                 'network interfaces on an '
                                                 'instance running in the '
                                                 'Oracle Cloud '
                                                 'Infrastructure.')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Suppress information messages')


    subparser = parser.add_subparsers(dest='command')
    subparser.add_parser('usage',
                         description='Displays usage')
    show_parser = subparser.add_parser('show',
               description="shows the current Virtual interface Cards provisioned in the Oracle Cloud Infrastructure and configured on this instance. This is the default action if no options are given")

    show_parser.add_argument('-I', '--include', metavar='ITEM', action='append',
                                type=uniq_item_validator, dest='include',
                                help='Include an ITEM that was previously excluded '
                                     'using the --exclude option in automatic '
                                     'configuration/deconfiguration.')
    show_parser.add_argument('-X', '--exclude', metavar='ITEM', action='append',
                        type=uniq_item_validator, dest='exclude',
                        help='Persistently exclude ITEM from automatic '
                             'configuration/deconfiguration.  Use the '
                             '--include option to include the ITEM again.')
    show_parser.add_argument('--details', action='store_true', default=False,
                                help='Display detailed information')
    show_parser.add_argument('--output-mode', choices=('parsable','table','json','text'),
                        help='Set output mode',default='table')
    # Display information the way previous version used to do (backward compatibility mode)
    show_parser.add_argument('--compat-output', action='store_true', default=False, help=argparse.SUPPRESS)

    show_vnics_parser = subparser.add_parser('show-vnics', description="shows VNICs information of this instance")
    show_vnics_parser.add_argument('--output-mode', choices=('parsable','table','json','text'),
                        help='Set output mode',default='table')
    show_vnics_parser.add_argument('--details', action='store_true', default=False,
                                help='Display detailed information')
    show_vnics_parser.add_argument('--ocid', type=vnic_oci_validator, action='store', metavar='VNIC_OCID', help='Show information of vNIC matching ocid')
    show_vnics_parser.add_argument('--name', type=str, action='store', metavar='VNIC_NAME', help='Show information of vNIC matching name')
    show_vnics_parser.add_argument('--ip-address', type=str, action='store', metavar='PRIMARY_IP', help='Show information of vNIC matching IP as primary IP')

    configure_parser = subparser.add_parser('configure',
                            description='Add IP configuration for VNICs that are not '
                            'configured and delete for VNICs that are no '
                            'longer provisioned.')
    configure_parser.add_argument('-n', '--namespace', action='store', metavar='FORMAT',
                        help='When configuring, place interfaces in namespace '
                             'identified by the given format. Format can '
                             'include $nic and $vltag variables.')
    configure_parser.add_argument('-r', '--start-sshd', action='store_true',
                        help='Start sshd in namespace (if -n is present)')
    # Secondary private IP address to use in conjunction configure or deconfigure.'
    # deprecated as redundant with add-secondary-addr and remove-secondary-addr
    configure_parser.add_argument('-S','--secondary-ip', nargs=2, metavar=('IP_ADDR', 'VNIC_OCID'),
                        dest='sec_ip', action='append',
                        help=argparse.SUPPRESS)
    configure_parser.add_argument('-I', '--include', metavar='ITEM', action='append',
                                type=str, dest='include',
                                help='Include an ITEM that was previously excluded '
                                     'using the --exclude option in automatic '
                                     'configuration/deconfiguration.')
    configure_parser.add_argument('-X', '--exclude', metavar='ITEM', action='append',
                        type=str, dest='exclude',
                        help='Persistently exclude ITEM from automatic '
                             'configuration/deconfiguration.  Use the '
                             '--include option to include the ITEM again.')

    deconfigure_parser = subparser.add_parser('deconfigure',
                            description='Deconfigure all VNICs (except the primary).')
    # Secondary private IP address to use in conjunction configure or deconfigure.'
    # deprecated as redundant with add-secondary-addr and remove-secondary-addr
    deconfigure_parser.add_argument('-S','--secondary-ip', nargs=2, metavar=('IP_ADDR', 'VNIC_OCID'),
                        dest='sec_ip', action='append',
                        help=argparse.SUPPRESS)
    deconfigure_parser.add_argument('-I', '--include', metavar='ITEM', action='append',
                                type=str, dest='include',
                                help='Include an ITEM that was previously excluded '
                                     'using the --exclude option in automatic '
                                     'configuration/deconfiguration.')
    deconfigure_parser.add_argument('-X', '--exclude', metavar='ITEM', action='append',
                        type=str, dest='exclude',
                        help='Persistently exclude ITEM from automatic '
                             'configuration/deconfiguration.  Use the '
                             '--include option to include the ITEM again.')

    attach_vnic = subparser.add_parser('attach-vnic',
                            description='Create a new VNIC and attach it to this instance.')
    attach_vnic.add_argument('-I','--ip-address', action='store', metavar='IP_ADDR',
                                        help="Private Ip to be assigned to the new vNIC")
    attach_vnic.add_argument('-i', '--nic-index', action='store', metavar='INDEX',
                                type=int, default=0,
                                 help='Physical NIC card index. When used with '
                                      'the --create-vnic option, assign the new VNIC '
                                      'to the specified physical NIC card.')
    attach_vnic.add_argument('--subnet', action='store',
                        help='When used with the --create-vnic option, '
                             'connect the new VNIC to the given subnet.')
    attach_vnic.add_argument('-n','--name', action='store', metavar='NAME',
                        help='use NAME as the display name of the new VNIC')
    attach_vnic.add_argument('--assign-public-ip', action='store_true',
                            help='assign a public IP address to the new VNIC.')
    attach_vnic.add_argument('--configure', action='store_true',
                            help='Adds IP configuration for that vNIC')

    detach_vnic = subparser.add_parser('detach-vnic',description='Detach and delete the VNIC with the given OCID'
                             ' or primary IP address')
    dg = detach_vnic.add_mutually_exclusive_group(required=True)
    dg.add_argument('--ocid', action='store', metavar='OCID',
                        help='detach the vNIC with the given VNIC')
    dg.add_argument('-I','--ip-address', action='store', metavar='IP_ADDR',
                        help='detach the vNIC with the given ip address configured on it')

    add_sec_addr = subparser.add_parser('add-secondary-addr',description="Adds the given secondary private IP.")
    add_sec_addr.add_argument('-I','--ip-address', action='store', metavar='IP_ADDR',
                        help='Secondary private IP to to be added',required=True)
    add_sec_addr.add_argument('--ocid', action='store', metavar='OCID',
                        help='Uses vNIC with the given VNIC',required=True)

    rem_sec_addr = subparser.add_parser('remove-secondary-addr',description="Removes the given secondary private IP.")
    rem_sec_addr.add_argument('-I','--ip-address', action='store', metavar='IP_ADDR',
                        help='Secondary private IP to to be removed',required=True)

    return parser


def get_oci_api_session():
    """
    Ensure the OCI SDK is available if the option is not None.

    Parameters
    ----------
    opt_name : str
        Operation name currently been exceuted (used for logging).

    Returns
    -------
        OCISession
            The session or None if cannot get one
    """
    session_cache = getattr(get_oci_api_session, "_session", None)
    if  session_cache:
        return session_cache

    sess = None

    try:
        _logger.debug('Creating session')
        sess = oci_utils.oci_api.OCISession()
        # it seems that having a client is not enough, we may not be able to query anything on it
        # workaround :
        # try a dummy call to be sure that we can use this session
        sess.this_instance()
        setattr(uniq_item_validator, "_session", sess)
    except Exception as e:
        _logger.error("Failed to access OCI services: %s" % str(e))
    _logger.debug('Returning session')
    return sess


class IndentPrinter(object):
    """
    Printer used in ColumnsPrinter.
    Print rows with indentation to stdout
    """
    def __init__(self, howmany):
        '''how many space indentation'''
        self.hm = howmany
    def write(self, s):
        """
            write string to stdout
        """
        sys.stdout.write('  '*self.hm + s)

def do_show_vnics_information(vnics, mode, details=False):
    """
    Show given vNIC information
    parameter
    ---------
        vnics : OCIVNIC instances
        mode : the output mode as str (text,json,parsable)
        details : display detailed information ?
    """

    def _display_secondary_ip_subnet(_, privip):
        _sn = privip.get_subnet()
        return '%s (%s)' % (_sn.get_display_name() ,_sn.get_cidr_block())

    _title = 'VNIs Information'
    _columns = [['Name',32,'get_display_name']]
    _columns.append(['Private IP',15,'get_private_ip'])
    _columns.append(['OCID',90,'get_ocid'])
    _columns.append(['MAC',17,'get_mac_address'])
    printerKlass = get_row_printer_impl(mode)
    if details:
        printerKlass = get_row_printer_impl('text')
        _columns.append(['Primary',7,'is_primary'])
        _columns.append(['Subnet',25,'get_subnet'])
        _columns.append(['NIC',3,'get_nic_index'])
        _columns.append(['Public IP',15,'get_public_ip'])
        _columns.append(['Availability domain',20,'get_availability_domain_name'])

        ips_printer = TextPrinter(title='Private IP addresses:',
            columns=(['IP address',15,'get_address'],['OCID','90','get_ocid'],['Hostname',25,'get_hostname'],
            ['Subnet',24,_display_secondary_ip_subnet]),printer=IndentPrinter(3))

    printer = printerKlass(title=_title, columns=_columns)
    printer.printHeader()
    for vnic in vnics:
        printer.printRow(vnic)
        if details:
            private_ips = vnic.all_private_ips()
            if len(private_ips) > 1:
                # private_ips include the primary we won't print (>1)
                ips_printer.printHeader()
                for p_ip in private_ips:
                    if not p_ip.is_primary():
                        # primary already displayed
                        ips_printer.printRow(p_ip)
                        print()
            ips_printer.printFooter()
            ips_printer.finish()
    printer.printFooter()
    printer.finish()

def do_show_information (vnic_utils, mode, details=False):
    """
    Display network information
    parameter
    ---------
        vnic_utils : instance ov VNICUtil
        mode : output mode (text,parsable etc...)
        details : display detailed information ?
    """

    sess = get_oci_api_session()
    if sess is None:
        raise Exception("Failed to get API session.")



    vnics = sess.this_instance().all_vnics()
    network_config = vnic_utils.get_network_config()

    def _display_subnet(_, interface):
        """ return network subnet. if interface match a vnic return OCI vnic subnet """
        if interface['VNIC']:
            vnic = [v for v in vnics if v.get_ocid() == interface['VNIC']][0]
            return '%s/%s (%s)' % (interface['SPREFIX'],interface['SBITS'],vnic.get_subnet().get_display_name())
        return '%s/%s' % (interface['SPREFIX'],interface['SBITS'])

    def _get_vnic_name(_, interface):
        """ if interface match a vnic return its display name """
        if interface['VNIC']:
            vnic = [v for v in vnics if v.get_ocid() == interface['VNIC']][0]
            return vnic.get_display_name()

    def _get_hostname(_, interface):
        """ if interface match a vnic return its hostname """
        if interface['VNIC']:
            vnic = [v for v in vnics if v.get_ocid() == interface['VNIC']][0]
            return vnic.get_hostname()

    _columns = []
    _columns.append(['State',6,'CONFSTATE'])
    _columns.append(['Link',15,'IFACE'])
    _columns.append(['Status',6,'STATE'])
    _columns.append(['Ip address',15,'ADDR'])
    _columns.append(['VNIC',30,_get_vnic_name])
    _columns.append(['MAC',17,'MAC'])
    if details:
        _columns.append(['Hostname',25,_get_hostname])
        _columns.append(['Subnet',32,_display_subnet])
        _columns.append(['Router IP',15,'VIRTRT'])
        _columns.append(['Namespace',10,'NS'])
        _columns.append(['Index',5,'IND'])
        _columns.append(['VLAN tag',8,'VLTAG'])
        _columns.append(['VLAN',11,'VLAN'])

    printerKlass = get_row_printer_impl(mode)
    printer = printerKlass(title='Network configuration', columns=_columns)

    printer.printHeader()
    for item in network_config:
        printer.printRow(item)
    printer.printFooter()
    printer.finish()

def compat_show_vnics_information():
    """
    Show the current vNIC configuration of the instance based on


    parameters
    ----------
     mode : output mode as str 'json','test','table','parsable','json'
     details : display details information ?

    Returns
    -------
       No return value.
    """

    def _display_subnet(_, vnic):
        """return subnet display name of this vnic """
        return vnic.get_subnet().get_display_name()
    def _display_secondary_ip_subnet(_, privip):
        _sn = privip.get_subnet()
        return '%s (%s)' % (_sn.get_display_name() ,_sn.get_cidr_block())
    def _display_vnic_name(_, vn):
        if vn.is_primary():
            return '%s (primary)' % vn.get_display_name()
        return vn.get_display_name()

    sess = get_oci_api_session()
    if sess is None:
        _logger.error("Failed to get API session.")
        return
    _logger.debug('getting instance ')
    inst = sess.this_instance()
    if inst is None:
        _logger.error("Failed to get information from OCI.")
        return
    _logger.debug('getting all vnics ')
    vnics = inst.all_vnics()
    _logger.debug('got for printing')

    _title = 'VNIC configuration for instance %s' % inst.get_display_name()

    _columns=(['Name',32,_display_vnic_name],
        ['Hostname',25,'get_hostname'],
        ['MAC',17,'get_mac_address'],
        ['Public IP',15,'get_public_ip'],
        ['Private IP(s)',15,'get_private_ip'],
        ['Subnet',18,_display_subnet],
        ['OCID',90,'get_ocid'])


    printer = TextPrinter(title=_title, columns=_columns, column_separator='')
    ips_printer = TextPrinter(title='Private IP addresses:',
            columns=(['IP address',15,'get_address'],['OCID','90','get_ocid'],['Hostname',25,'get_hostname'],
            ['Subnet',24,_display_secondary_ip_subnet]),printer=IndentPrinter(3))

    printer.printHeader()
    for vnic in vnics:
        printer.printRow(vnic)
        _all_p_ips = vnic.all_private_ips()
        if len(_all_p_ips) > 1:
            # _all_p_ips include the primary we won't print (>1)
            ips_printer.printHeader()
            for p_ip in _all_p_ips:
                if not p_ip.is_primary():
                    # primary already displayed
                    ips_printer.printRow(p_ip)
            print()
            ips_printer.printFooter()
            ips_printer.finish()
    printer.printFooter()
    printer.finish()



def compat_show_network_config(vnic_utils):
    """
    Display the currect network interface configuration as well as the
    VNIC configuration from OCI.

    Parameters
    ----------
    vnic_utils :
        The VNIC configuration instance.

    Returns
    -------
        No return value.
    """
    def _get_subnet(_, interface):
        return '%s/%s' % (interface['SPREFIX'],interface['SBITS'])

    ret = vnic_utils.get_network_config()

    _title = "Operating System level network configuration"
    _columns=(['CONFIG',6,'CONFSTATE'],
        ['ADDR',15,'ADDR'],
        ['SPREFIX',15,'SPREFIX'],
        ['SBITS',5,'SBITS'],
        ['VIRTRT',15,'VIRTRT'],
        ['NS',10,'NS'],
        ['IND',4,'IND'],
        ['IFACE',15,'IFACE'],
        ['VLTAG',5,'VLTAG'],
        ['VLAN',11,'VLAN'],
        ['STATE',5,'STATE'],['MAC',17,'MAC'],['VNIC',90,'VNIC'])
    printer=TablePrinter(title=_title, columns=_columns, column_separator='', text_truncate=False)

    printer.printHeader()
    for item in ret:
        printer.printRow(item)
    printer.printFooter()
    printer.finish()


def do_detach_vnic(detach_options, vnic_utils):
    """
    Detach and delete the VNIC with the given ocid or primary ip address

    Parameters
    ----------
    detach_options : namespace
        The argparse namespace.
    vnic_utils :
        The VNIC configuration instance.

    Returns
    -------
        No return value on success;.

    Raises
    ------
        Exception
            if session cannot be acquired
            if the VNIC cannot be detached

    """

    sess = get_oci_api_session()
    if sess is None:
        raise Exception("Failed to get API session.")
    vnics = sess.this_instance().all_vnics()
    for vnic in vnics:
        if vnic.get_ocid() == detach_options.ocid or \
           vnic.get_private_ip() == detach_options.ip_address:
            if not vnic.is_primary():
                vnic_utils.delete_all_private_ips(vnic.get_ocid())
                vnic.detach()
                break
            raise Exception("The primary VNIC cannot be detached.")



def do_create_vnic(create_options):
    """
    Create and attach a VNIC to this instance.

    Parameters
    ----------
    create_options :
        The VNIC configuration instance.

    Returns
    -------
        No return value on success; errors out with return value 1 otherwise.

    Raises
    ------
        Exception
            if session cannot be acquired
    """
    # needs the OCI SDK installed and configured
    sess = get_oci_api_session()
    if sess is None:
        raise Exception("Failed to get API session.")
    subnet_id = None
    if create_options.subnet:
        if create_options.subnet.startswith('ocid1.subnet.'):
            subnet = sess.get_subnet(create_options.subnet)
            if subnet is None:
                raise Exception("Subnet not found: %s" % create_options.subnet)
            subnet_id = subnet.get_ocid()
        else:
            subnets = sess.find_subnets(create_options.subnet)
            if len(subnets) == 0:
                raise Exception("No subnet matching %s found" % create_options.subnet)
            if len(subnets) > 1:
                _logger.error("More than one subnet matching %s found:\n"
                               % create_options.subnet)
                for sn in subnets:
                    _logger.error("   %s\n" % sn.get_display_name())
                raise Exception("More than one subnet matching")
            subnet_id = subnets[0].get_ocid()
    try:
        vnic = sess.this_instance().attach_vnic(
            private_ip=create_options.ip_address,
            assign_public_ip=create_options.assign_public_ip,
            subnet_id=subnet_id,
            nic_index=create_options.nic_index,
            display_name=create_options.name)
    except Exception as e:
        raise Exception('Failed to create VNIC: %s'%str(e)) from e


    public_ip = vnic.get_public_ip()
    if public_ip is not None:
        _logger.info(
            'creating VNIC: %s (public IP %s)' , vnic.get_private_ip(), public_ip)
    else:
        _logger.info('creating VNIC: %s' , vnic.get_private_ip())


def do_add_private_ip(vnic_utils, add_options):
    """
    Add a secondary private IP for an existing VNIC.

    Parameters
    ----------
    vnic_utils : VNICUtils
        The VNICUtils helper instance.
    add_options : namespace
        The argparse namespace.

    Returns
    -------
        tuple
            (private_IP,vnic_ocid) for the new IP on success; errors out with
            return value 1 otherwise.

    Raises
    ------
        Exception
            On any error.
    """
    # needs the OCI SDK installed and configured
    sess = get_oci_api_session()
    if sess is None:
        raise Exception("Failed to get API session.")

    if add_options.ocid:
        vnic = sess.get_vnic(add_options.ocid)
        if vnic is None:
            raise Exception("VNIC not found: %s" % add_options.ocid)
    else:
        vnics = sess.this_instance().all_vnics()
        if len(vnics) > 1:
            _logger.error("More than one VNIC found."
                           "Use the --vnic option to select the one to add "
                           "a secondary IP for:")
            for vnic in vnics:
                _logger.error("   %s: %s" % (vnic.get_private_ip(),
                                              vnic.get_ocid()))
            raise Exception("Too many VNICs found")
        vnic = vnics[0]
    try:
        priv_ip = vnic.add_private_ip(private_ip=add_options.private_ip)
    except Exception as e:
        raise Exception('Failed to provision private IP') from e

    _logger.info(
        'provisioning secondary private IP: %s' % priv_ip.get_address())
    vnic_utils.add_private_ip(priv_ip.get_address(), vnic.get_ocid())
    return priv_ip.get_address(), vnic.get_ocid()


def do_del_private_ip(vnic_utils, delete_options):
    """
    Delete a secondary private IP

    Parameters
    ----------
    vnic_utils :
        The VNIC configuration instance.
    delete_options :
        The argparse namespace.

    Returns
    -------
        No return value on success; errors out with return value 1 otherwise.

    Raises
    ------
    Exception
        error getting session
    """
    # needs the OCI SDK installed and configured
    sess = get_oci_api_session()
    if sess is None:
        raise Exception("Failed to get API session.")
    # find the private IP
    priv_ip = sess.this_instance().find_private_ip(
        delete_options.ip_address)
    if priv_ip is None:
        raise Exception(
            "Secondary private IP not found: %s" %
            delete_options.ip_address)

    if priv_ip.is_primary():
        raise Exception("Cannot delete IP %s, it is the primary private "
                        "address of the VNIC." % delete_options.ip_address)

    vnic_id = priv_ip.get_vnic_ocid()

    if not priv_ip.delete():
        raise Exception('failed to delete secondary private IP %s' %
                        delete_options.ip_address)

    _logger.info('deconfigure secondary private IP %s' %
                  delete_options.ip_address)
    # delete from vnic_info and de-configure the interface
    return vnic_utils.del_private_ip(delete_options.ip_address, vnic_id)


def main():
    """
    Main

    Returns
    -------
        int
            0 on success;
            1 on failure.
    """
    parser = get_arg_parser()
    args = parser.parse_args()

    if args.quiet:
        _logger.setLevel(logging.WARNING)

    if not args.command:
        parser.print_help()
        return 1

    if args.command == 'usage':
        parser.print_help()
        return 0

    if os.geteuid() != 0:
        _logger.error("You must run this program with root privileges")
        return 1

    try:
        vnic_utils = VNICUtils()
    except IOError as e:
        _logger.warning("Cannot get vNIC information: %s" % str(e))
        _logger.debug('Cannot get vNIC information', exc_info=True)
        return 1

    if 'exclude' in args and args.exclude:
        for exc in args.exclude:
            vnic_utils.exclude(exc)

    if 'include' in args and args.include:
        for inc in args.include:
            vnic_utils.include(inc)


    if _logger.isEnabledFor(logging.INFO) and not args.quiet:
        excludes = vnic_utils.get_vnic_info()[1]['exclude']
        if excludes:
            _logger.info(
                "Info: Addresses excluded from automatic configuration: %s" %
                ", ".join(excludes))


    if args.command == 'show':
        if args.compat_output:
            compat_show_vnics_information()
            compat_show_network_config(vnic_utils)
        else:
            try:
                do_show_information(vnic_utils,args.output_mode, args.details)
            except Exception as e:
                _logger.debug('cannot show  information', exc_info=True)
                _logger.error('cannot show information: %s' % str(e))
                return 1
        return 0

    if args.command == 'show-vnics':
        sess = get_oci_api_session()
        if sess is None:
            _logger.error("Failed to get API session.")
            return 1
        vnics = set()
        _vnics = sess.this_instance().all_vnics()
        if not args.ocid and not args.name and not args.ip_address:
            vnics.update(_vnics)
        else:
            if args.ocid:
                for v in _vnics:
                    if v.get_ocid() == args.ocid:
                        vnics.add(v)
            if args.name:
                for v in _vnics:
                    if v.get_display_name() == args.name:
                        vnics.add(v)
            if args.ip_address:
                for v in _vnics:
                    if v.get_private_ip() == args.ip_address:
                        vnics.add(v)
        do_show_vnics_information(vnics,args.output_mode, args.details)

        return 0


    if args.command == 'attach-vnic':
        if 'nic_index' in args and args.nic_index != 0:
            if not get_oci_api_session().this_shape().startswith("BM"):
                _logger.error('--nic-index option ignored when not runnig on Bare Metal type of shape')
                return 1
        try:
            do_create_vnic(args)
        except Exception as e:
            _logger.debug('cannot create the VNIC', exc_info=True)
            _logger.error('cannot create the VNIC: %s' % str(e))
            return 1
        # apply config of newly created vnic
        vnic_utils.auto_config(None)


    if args.command == 'detach-vnic':
        try:
            do_detach_vnic(args, vnic_utils)
        except Exception as e:
            _logger.debug('cannot detach VNIC', exc_info=True)
            _logger.error('cannot detach vNIC: %s' % str(e))
            return 1
        # if we are here session is alive: no check
        if get_oci_api_session().this_shape().startswith("BM"):
            # in runnning on BM some cleanup is needed on the host
            vnic_utils.auto_config(None)


    if args.command == "add-secondary-addr":
        try:
            (ip, vnic_id) = do_add_private_ip(vnic_utils, args)
            _logger.info("IP %s has been assigned to vnic %s." % (ip, vnic_id))
        except Exception as e:
            _logger.error('failed to add private ip: %s' % str(e))
            return 1


    if args.command == "remove-secondary-addr":
        try:
            (ret, out) = do_del_private_ip(vnic_utils, args)
            if ret != 0:
                raise Exception('cannot deleet ip: %s' % out)
        except Exception as e:
            _logger.error('failed to delete private ip: %s' % str(e))
            return 1


    if 'namespace' in args and args.namespace:
        vnic_utils.set_namespace(args.namespace)

    if 'start_sshd' in args and args.start_sshd:
        vnic_utils.set_sshd(args.start_sshd)

    if args.command == 'configure':
        vnic_utils.auto_config(args.sec_ip)

    if args.command == 'deconfigure':
        vnic_utils.auto_deconfig(args.sec_ip)

    return 0


if __name__ == "__main__":
    sys.exit(main())
