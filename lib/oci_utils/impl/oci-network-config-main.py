#
# Copyright (c) 2017, 2022 Oracle and/or its affiliates. All rights reserved.
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
import time

import oci_utils
import oci_utils.oci_api
from oci_utils.impl.oci_resources import OCIVNIC
from oci_utils.impl.row_printer import (get_row_printer_impl, TablePrinter, TextPrinter)
from oci_utils.vnicutils import VNICUtils

_logger = logging.getLogger("oci-utils.oci-network-config")


def uniq_item_validator(value):
    """
    Validates unicity by checking that value not already in the list

    Parameter
    ---------
     value : str , option's value
    """
    already_seen = getattr(uniq_item_validator, "_item_seen", [])

    if value in already_seen:
        raise argparse.ArgumentTypeError("Invalid arguments: item both included and excluded: %s" % value)
    already_seen.append(value)
    setattr(uniq_item_validator, "_item_seen", already_seen)

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
    parser = argparse.ArgumentParser(prog='oci-network-config',
                                     description='Utility for configuring network interfaces on an instance running '
                                                 'in the Oracle Cloud Infrastructure.')
    parser.add_argument('--quiet', '-q',
                        action='store_true',
                        help='Suppress information messages.')

    subparser = parser.add_subparsers(dest='command')
    #
    # usage
    subparser.add_parser('usage',
                         description='Displays usage')
    #
    # show
    show_parser = subparser.add_parser('show',
                                       description='Shows the current Virtual Interface Cards provisioned in the '
                                                   'Oracle Cloud Infrastructure and configured on this instance. '
                                                   'This is the default action if no options are given.');
    show_parser.add_argument('-I', '--include',
                             metavar='ITEM',
                             action='append',
                             type=uniq_item_validator,
                             dest='include',
                             help='Include an ITEM that was previously excluded using the --exclude option in '
                                  'automatic configuration/deconfiguration.')
    show_parser.add_argument('-X', '--exclude',
                             metavar='ITEM',
                             action='append',
                             type=uniq_item_validator,
                             dest='exclude',
                             help='Persistently exclude ITEM from automatic configuration/deconfiguration. Use '
                                  'the --include option to include the ITEM again.')
    show_parser.add_argument('--details',
                             action='store_true',
                             default=False,
                             help='Display detailed information.')
    show_parser.add_argument('--output-mode',
                             choices=('parsable', 'table', 'json', 'text'),
                             help='Set output mode.',
                             default='table')
    # Display information the way previous version used to do (backward compatibility mode)
    show_parser.add_argument('--compat-output',
                             action='store_true',
                             default=False,
                             help=argparse.SUPPRESS)
    #
    # show-vnics
    show_vnics_parser = subparser.add_parser('show-vnics',
                                             description="Shows VNICs information of this instance.")
    show_vnics_parser.add_argument('--output-mode',
                                   choices=('parsable', 'table', 'json', 'text'),
                                   help='Set output mode.',
                                   default='table')
    show_vnics_parser.add_argument('--details',
                                   action='store_true',
                                   default=False,
                                   help='Display detailed information')
    show_vnics_parser.add_argument('--ocid',
                                   type=vnic_oci_validator,
                                   action='store',
                                   metavar='VNIC_OCID',
                                   help='Show information of VNIC matching ocid.')
    show_vnics_parser.add_argument('--name',
                                   type=str,
                                   action='store',
                                   metavar='VNIC_NAME',
                                   help='Show information of VNIC matching name.')
    show_vnics_parser.add_argument('--ip-address',
                                   type=str,
                                   action='store',
                                   metavar='PRIMARY_IP',
                                   help='Show information of VNIC matching IP as primary IP')
    #
    # configure
    configure_parser = subparser.add_parser('configure',
                                            description='Add IP configuration for VNICs that are not configured and '
                                                        'delete for VNICs that are no longer provisioned.')
    configure_parser.add_argument('-n', '--namespace',
                                  action='store',
                                  metavar='FORMAT',
                                  help='When configuring, place interfaces in namespace identified by the given '
                                       'format. Format can include $nic and $vltag variables.')
    configure_parser.add_argument('-r', '--start-sshd',
                                  action='store_true',
                                  help='Start sshd in namespace (if -n is present).')
    # Secondary private IP address to use in conjunction configure or deconfigure.'
    # deprecated as redundant with add-secondary-addr and remove-secondary-addr
    configure_parser.add_argument('-S', '--secondary-ip',
                                  nargs=2,
                                  metavar=('IP_ADDR', 'VNIC_OCID'),
                                  dest='sec_ip',
                                  action='append',
                                  help=argparse.SUPPRESS)
    configure_parser.add_argument('-I', '--include',
                                  metavar='ITEM',
                                  action='append',
                                  type=str,
                                  dest='include',
                                  help='Include an ITEM that was previously excluded using the --exclude option in '
                                       'automatic configuration/deconfiguration.')
    configure_parser.add_argument('-X', '--exclude',
                                  metavar='ITEM',
                                  action='append',
                                  type=str,
                                  dest='exclude',
                                  help='Persistently exclude ITEM from automatic configuration/deconfiguration. Use '
                                       'the --include option to include the ITEM again.')
    #
    # unconfigure
    unconfigure_parser = subparser.add_parser('unconfigure',
                                              description='Unconfigure all VNICs (except the primary).')
    # Secondary private IP address to use in conjunction configure or unconfigure.'
    # deprecated as redundant with add-secondary-addr and remove-secondary-addr
    unconfigure_parser.add_argument('-S', '--secondary-ip',
                                    nargs=2,
                                    metavar=('IP_ADDR', 'VNIC_OCID'),
                                    dest='sec_ip',
                                    action='append',
                                    help=argparse.SUPPRESS)
    unconfigure_parser.add_argument('-I', '--include',
                                    metavar='ITEM',
                                    action='append',
                                    type=str, dest='include',
                                    help='Include an ITEM that was previously excluded using the --exclude option '
                                         'in automatic configuration/deconfiguration.')
    unconfigure_parser.add_argument('-X', '--exclude',
                                    metavar='ITEM',
                                    action='append',
                                    type=str,
                                    dest='exclude',
                                    help='Persistently exclude ITEM from automatic configuration/deconfiguration.  '
                                         'Use the --include option to include the ITEM again.')
    #
    # attach vnic
    attach_vnic = subparser.add_parser('attach-vnic',
                                       description='Create a new VNIC and attach it to this instance.')
    attach_vnic.add_argument('-I', '--ip-address',
                             action='store',
                             metavar='IP_ADDR',
                             help="Private IP to be assigned to the new VNIC.")
    attach_vnic.add_argument('-i', '--nic-index',
                             action='store',
                             metavar='INDEX',
                             type=int,
                             default=0,
                             help='Physical NIC card index.')
    attach_vnic.add_argument('--subnet',
                             action='store',
                             help='Connect the new VNIC to the given subnet.')
    attach_vnic.add_argument('-n', '--name',
                             action='store',
                             metavar='NAME',
                             help='Use NAME as the display name of the new VNIC.')
    attach_vnic.add_argument('--assign-public-ip',
                             action='store_true',
                             help='assign a public IP address to the new VNIC.')
    #
    # detach vnic
    detach_vnic = subparser.add_parser('detach-vnic',
                                       description='Detach and delete the VNIC with the given '
                                                   'OCID or  primary IP address.')
    dg = detach_vnic.add_mutually_exclusive_group(required=True)
    dg.add_argument('-O', '--ocid',
                    action='store',
                    metavar='OCID',
                    help='Detach the VNIC with the given OCID.')
    dg.add_argument('-I', '--ip-address',
                    action='store',
                    metavar='IP_ADDR',
                    help='Detach the VNIC with the given ip address configured on it.')
    #
    #  add secondary address
    add_sec_addr = subparser.add_parser('add-secondary-addr',
                                        description="Adds the given secondary private IP.")
    add_sec_addr.add_argument('-I', '--ip-address',
                              action='store',
                              metavar='IP_ADDR',
                              help='Secondary private IP to to be added.')
    add_sec_addr.add_argument('-O', '--ocid',
                              action='store',
                              metavar='OCID',
                              help='Uses VNIC with the given VNIC.')
    #
    # remove secondary address
    rem_sec_addr = subparser.add_parser('remove-secondary-addr',
                                        description="Removes the given secondary private IP.")
    rem_sec_addr.add_argument('-I', '--ip-address',
                              action='store',
                              metavar='IP_ADDR',
                              help='Secondary private IP to to be removed.',
                              required=True)

    return parser


def get_oci_api_session():
    """
    Ensure the OCI SDK is available if the option is not None.

    Returns
    -------
        OCISession
            The session or None if cannot get one
    """
    session_cache = getattr(get_oci_api_session, "_session", None)
    if session_cache:
        return session_cache

    sess = None

    try:
        _logger.debug('Creating session')
        sess = oci_utils.oci_api.OCISession()
        # it seems that having a client is not enough, we may not be able to query anything on it
        # workaround :
        # try a dummy call to be sure that we can use this session
        if not bool(sess.this_instance()):
            _logger.debug('Returning None session')
            return None
        setattr(get_oci_api_session, "_session", sess)
    except Exception as e:
        _logger.error("Failed to access OCI services: %s", str(e))
    _logger.debug('Returning session')
    return sess


class IndentPrinter:
    """
    Printer used in ColumnsPrinter.
    Print rows with indentation to stdout
    """

    def __init__(self, howmany):
        """ How many spaces indentation
        """
        self.hm = howmany

    def write(self, s):
        """ Write string to stdout
        """
        sys.stdout.write('  '*self.hm + s)


def collect_vnic_data(vnics, details, col_lengths, p_col_lengths):
    """
    Collect the data from volumes with respect to disply.

    Parameters
    ----------
    vnics: VNICUtils
        The vnic data.
    details: bool
        Flag, if True, show details.
    col_lengths: list
        Lengths of the respective columns.
    p_col_lengths: list
        Lenghts of the columns for private ip data.

    Returns
    -------
        tuple: (vnic data, private vnic data, column lengths, column lengths for private ip)
    """

    def _display_secondary_ip_subnet(_, privip):
        _sn = privip.get_subnet()
        return '%s (%s)' % (_sn.get_display_name(), _sn.get_cidr_block())

    def _display_subnet(_, subnet):
        """ return network subnet information."""
        return '%s/%s' % (vnic.get_subnet().get_cidr_block(), vnic.get_subnet().get_display_name())

    vnic_data = list()
    p_vnic_data = dict()
    for vnic in vnics:
        _nic_data = dict()
        # name
        _nic_data['name'] = vnic.get_display_name()
        col_lengths['name'] = max(len(_nic_data['name']), col_lengths['name'])
        # private ip
        _nic_data['privateip'] = vnic.get_private_ip()
        col_lengths['privateip'] = max(len(_nic_data['privateip']), col_lengths['privateip'])
        # ocid
        _nic_data['ocid'] = vnic.get_ocid()
        col_lengths['ocid'] = max(len(_nic_data['ocid']), col_lengths['ocid'])
        # mac address
        _nic_data['mac'] = vnic.get_mac_address()
        col_lengths['mac'] = max(len(_nic_data['mac']), col_lengths['mac'])
        if details:
            # primary
            _nic_data['primary'] = vnic.is_primary()
            _nic_primary_len = 4 if _nic_data['primary'] else 5
            col_lengths['primary'] = max(_nic_primary_len, col_lengths['primary'])
            # subnet
            _nic_data['subnet'] = _display_subnet(None, 'dummy')
            col_lengths['subnet'] = max(len(_nic_data['subnet']), col_lengths['subnet'])
            # nic index
            _nic_data['nic'] = vnic.get_nic_index()
            col_lengths['nic'] = max(3, col_lengths['nic'])
            # public ip
            _nic_data['publicip'] = vnic.get_public_ip()
            _nic_publicip_len = 4 if _nic_data['publicip'] is None else len(_nic_data['publicip'])
            col_lengths['publicip'] = max(_nic_publicip_len, col_lengths['publicip'])
            # availability domain
            _nic_data['availabilitydomain'] = vnic.get_availability_domain_name()
            col_lengths['availabilitydomain'] = max(len(_nic_data['availabilitydomain']),
                                                    col_lengths['availabilitydomain'])
            # secondary addresses
            _private_ips = vnic.all_private_ips()
            # we do not print primary again
            if len(_private_ips) > 1:
                p_vnic_data[_nic_data['name']] = list()
                for priv_ip in _private_ips:
                    if not priv_ip.is_primary():
                        _p_nic_data = dict()
                        # ipaddress
                        _p_nic_data['ipaddress'] = priv_ip.get_address()
                        p_col_lengths['ipaddress'] = max(len(_p_nic_data['ipaddress']), p_col_lengths['ipaddress'])
                        # ocid
                        _p_nic_data['ocid'] = priv_ip.get_ocid()
                        p_col_lengths['ocid'] = max(len(_p_nic_data['ocid']), p_col_lengths['ocid'])
                        # hostname
                        _hostname = priv_ip.get_hostname()
                        _p_nic_data['hostname'] = '-' if _hostname is None else _hostname
                        p_col_lengths['hostname'] = max(len(_p_nic_data['hostname']), p_col_lengths['hostname'])
                        # subnet
                        _p_nic_data['subnet'] = _display_secondary_ip_subnet(None, priv_ip)
                        p_col_lengths['subnet'] = max(len(_p_nic_data['subnet']), p_col_lengths['subnet'])
                        #
                        p_vnic_data[_nic_data['name']].append(_p_nic_data)
        vnic_data.append(_nic_data)

    return vnic_data, p_vnic_data, col_lengths, p_col_lengths


def do_show_vnics_information(vnics, mode, details=False):
    """
    Show given VNIC information
    parameter
    ---------
        vnics : OCIVNIC instances
        mode : the output mode as str (text,json,parsable)
        details : display detailed information ?
    """
    _cols = ['Name', 'Private IP', 'OCID', 'MAC']
    _col_name = ['name', 'privateip', 'ocid', 'mac']
    _cols_details = ['Primary', 'Subnet', 'NIC', 'Public IP', 'Availability Domain']
    _col_detail_name = ['primary', 'subnet', 'nic', 'publicip', 'availabilitydomain']
    if details:
        _cols = [*_cols, *_cols_details]
        _col_name = [*_col_name, *_col_detail_name]

    _cols_len = list()
    for col in _cols:
        _cols_len.append(len(col))

    _p_cols = ['IP address', 'OCID', 'Hostname', 'Subnet']
    _p_col_name = ['ipaddress', 'ocid', 'hostname', 'subnet']
    _p_cols_len = list()
    for col in _p_cols:
        _p_cols_len.append(len(col))

    vnic_data, p_vnic_data, _collen, _p_collen = collect_vnic_data(vnics,
                                                                   details,
                                                                   dict(zip(_col_name, _cols_len)),
                                                                   dict(zip(_p_col_name, _p_cols_len)))

    _title = 'VNICs Information:'
    _columns = list()
    for i in range(len(_cols)):
        _columns.append([_cols[i], _collen[_col_name[i]]+2, _col_name[i]])

    _p_columns = list()
    for i in range(len(_p_cols)):
        _p_columns.append([_p_cols[i], _p_collen[_p_col_name[i]]+2, _p_col_name[i]])

    printerKlass = get_row_printer_impl(mode)
    printer = printerKlass(title=_title, columns=_columns)
    printheader = False
    for vnic in vnic_data:
        if not printheader:
            printer.printHeader()
            printheader = True
        printer.rowBreak()
        printer.printRow(vnic)
        if details:
            if vnic['name'] in p_vnic_data:
                ips_printer = printerKlass(title='Private IP addresses:',
                                           columns=_p_columns,
                                           printer=IndentPrinter(3))
                ips_printer.printHeader()
                for p_ip in p_vnic_data[vnic['name']]:
                    ips_printer.printRow(p_ip)
                    ips_printer.rowBreak()
                ips_printer.printFooter()
                ips_printer.finish()
                printheader = False
    printer.printFooter()
    printer.finish()


def do_show_information(vnic_utils, mode, details=False):
    """
    Display network information

    Parameters
    ----------
        vnic_utils : instance of VNICUtils

        mode : str
            output mode (text,parsable etc...)
        details : bool
            display detailed information ?
    """

    sess = get_oci_api_session()
    if sess is None:
        raise Exception("Failed to get API session.")

    vnics = sess.this_instance().all_vnics()
    network_config = vnic_utils.get_network_config()


    def _display_subnet(interface):
        """
        Return the network subnet.

        Parameters
        ----------
        interface: dict
            The interface.

        Returns
        -------
            str: the network subnet, it the interface matches a vnic, the OCI vnic subnet.
        """
        if interface['VNIC']:
            for v in vnics:
                if v.get_ocid() == interface['VNIC']:
                    v_subnet = [interface['SPREFIX'], interface['SBITS']]
                    return '%s/%s (%s)' % (v_subnet[0], v_subnet[1], v.get_subnet().get_display_name())
        return '%s/%s' % (interface['SPREFIX'], interface['SBITS'])

    def _get_vnic_name(interface):
        """
        Get the vnic name.

        Parameters
        ----------
        interface: dict
            The interface.

        Returns
        -------
            str: the vnic name if the interface matches a vnic, else '-'
        """
        if interface['VNIC']:
            for v in vnics:
                if v.get_ocid() == interface['VNIC']:
                    return v.get_display_name()
        return '-'

    def _get_hostname(interface):
        """
        Return the interfaces hostname.

        Parameters
        ----------
        interface: dict
            The interface.

        Returns
        -------
            str: the vnic hostname if the interface matches a vnic, else '-'
        """
        if interface['VNIC']:
            for v in vnics:
                if v.get_ocid() == interface['VNIC']:
                    v_hostname = v.get_hostname()
                    return 'None' if v_hostname is None else v_hostname
        return '-'

    _cols = ['State', 'Link', 'Status', 'IP address', 'VNIC', 'MAC']
    _col_name = ['state', 'link', 'status', 'ipaddress', 'vnic', 'mac']
    _cols_details = ['Hostname', 'Subnet', 'Router IP', 'Namespace', 'Index', 'VLAN tag', 'VLAN']
    _col_detail_name = ['hostname', 'subnet', 'routerip', 'namespace', 'index', 'vlantag', 'vlan']

    if details:
        _cols = [*_cols, *_cols_details]
        _col_name = [*_col_name, *_col_detail_name]

    _cols_len = list()
    for col in _cols:
        _cols_len.append(len(col))
    _collen = dict(zip(_col_name, _cols_len))

    vnic_data = list()
    for item in network_config:
        _nic_data = dict()
        # state
        _nic_data['state'] = item['CONFSTATE']
        _collen['state'] = max(len(_nic_data['state']), _collen['state'])
        # link
        _nic_data['link'] = item['IFACE']
        _collen['link'] = max(len(_nic_data['link']), _collen['link'])
        # status
        _nic_data['status'] = item['STATE']
        _collen['status'] = max(len(_nic_data['status']), _collen['status'])
        # ipaddress
        _nic_data['ipaddress'] = item['ADDR']
        _collen['ipaddress'] = max(len(_nic_data['ipaddress']), _collen['ipaddress'])
        # vnic
        _nic_data['vnic'] = _get_vnic_name(item)
        _collen['vnic'] = max(len(_nic_data['vnic']), _collen['vnic'])
        # mac
        _nic_data['mac'] = item['MAC']
        _collen['mac'] = max(len(_nic_data['mac']), _collen['mac'])
        if details:
            # hostname
            _nic_data['hostname'] = _get_hostname(item)
            _collen['hostname'] = max(len(_nic_data['hostname']), _collen['hostname'])
            # subnet
            _nic_data['subnet'] = _display_subnet(item)
            _collen['subnet'] = max(len(_nic_data['subnet']), _collen['subnet'])
            # routerip
            _nic_data['routerip'] = item['VIRTRT']
            _collen['routerip'] = max(len(_nic_data['routerip']), _collen['routerip'])
            # namespace
            _nic_data['namespace'] = item['NS']
            _collen['namespace'] = max(len(_nic_data['namespace']), _collen['namespace'])
            # index
            _nic_data['index'] = item['IND']
            _collen['index'] = max(len(_nic_data['index']), _collen['index'])
            # vlantag
            _nic_data['vlantag'] = item['VLTAG']
            _collen['vlantag'] = max(len(_nic_data['vlantag']), _collen['vlantag'])
            # vlan
            _nic_data['vlan'] = item['VLAN']
            _collen['vlan'] = max(len(_nic_data['vlan']), _collen['vlan'])
        vnic_data.append(_nic_data)

    _columns = list()
    for i in range(len(_cols)):
        _columns.append([_cols[i], _collen[_col_name[i]]+2, _col_name[i]])

    printerKlass = get_row_printer_impl(mode)
    printer = printerKlass(title='Network configuration', columns=_columns)

    printer.printHeader()
    for item in vnic_data:
        printer.printRow(item)
        printer.rowBreak()
    printer.printFooter()
    printer.finish()


def compat_show_vnics_information():
    """
    Show the current VNIC configuration of the instance based on

    Returns
    -------
       No return value.
    """

    def _display_subnet(_, vnic):
        """return subnet display name of this vnic """
        return vnic.get_subnet().get_display_name()

    def _display_secondary_ip_subnet(_, privip):
        _sn = privip.get_subnet()
        return '%s (%s)' % (_sn.get_display_name(), _sn.get_cidr_block())

    def _display_vnic_name(_, vn):
        if vn.is_primary():
            return '%s (primary)' % vn.get_display_name()
        return vn.get_display_name()

    sess = get_oci_api_session()
    if sess is None:
        _logger.error("Failed to get API session.")
        return
    _logger.debug('Getting instance ')
    inst = sess.this_instance()
    if inst is None:
        _logger.error("Failed to get information from OCI.")
        return
    _logger.debug('Getting all vnics ')
    vnics = inst.all_vnics()
    _logger.debug('Got for printing')

    _title = 'VNIC configuration for instance %s:' % inst.get_display_name()

    _columns = (['Name', 32, _display_vnic_name],
                ['Hostname', 25, 'get_hostname'],
                ['MAC', 17, 'get_mac_address'],
                ['Public IP', 15, 'get_public_ip'],
                ['Private IP(s)', 15, 'get_private_ip'],
                ['Subnet', 18, _display_subnet],
                ['OCID', 90, 'get_ocid'])

    printer = TextPrinter(title=_title, columns=_columns, column_separator='')
    ips_printer = TextPrinter(title='Private IP addresses:',
                              columns=(['IP address', 15, 'get_address'],
                                       ['OCID', '90', 'get_ocid'],
                                       ['Hostname', 25, 'get_hostname'],
                                       ['Subnet', 24, _display_secondary_ip_subnet]),
                              printer=IndentPrinter(3))

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
            printer.rowBreak()
            ips_printer.printFooter()
            ips_printer.finish()
    printer.printFooter()
    printer.finish()


def show_network_config(vnic_utils):
    """
    Display the current network interface configuration as well as the VNIC configuration from OCI.

    Parameters
    ----------
    vnic_utils :
        The VNIC configuration instance.

    Returns
    -------
        No return value.
    """
    def _get_subnet(_, interface):
        return '%s/%s' % (interface['SPREFIX'], interface['SBITS'])

    ret = vnic_utils.get_network_config()

    _title = "Operating System level network configuration:"
    _columns = (['CONFIG', 6, 'CONFSTATE'],
                ['ADDR', 15, 'ADDR'],
                ['SUBNET', 15, 'SPREFIX'],
                ['BITS', 5, 'SBITS'],
                ['VIRTROUTER', 15, 'VIRTRT'],
                ['NS', 10, 'NS'],
                ['IND', 4, 'IND'],
                ['IFACE', 15, 'IFACE'],
                ['VLTAG', 5, 'VLTAG'],
                ['VLAN', 13, 'VLAN'],
                ['STATE', 6, 'STATE'],
                ['MAC', 17, 'MAC'],
                ['VNIC ID', 90, 'VNIC'])
    printer = TablePrinter(title=_title, columns=_columns, column_separator='', text_truncate=False)

    printer.printHeader()
    for item in ret:
        printer.printRow(item)
    printer.printFooter()
    printer.finish()


def do_detach_vnic(detach_options):
    """
    Detach and delete the VNIC with the given ocid or primary ip address

    Parameters
    ----------
    detach_options : namespace
        The argparse namespace.

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
        v_ocid = vnic.get_ocid()
        v_ip = vnic.get_private_ip()
        if v_ocid == detach_options.ocid or v_ip == detach_options.ip_address:
            if not vnic.is_primary():
                _logger.info('Detaching VNIC %s [%s]', v_ip, v_ocid)
                vnic.detach()
                _logger.info('VNIC [%s] is detached.', v_ocid)
                break
            raise Exception("The primary VNIC cannot be detached.")
    else:
        _logger.error('VNIC %s [%s] is not attached to this instance.', detach_options.ip_address, detach_options.ocid)


def do_create_vnic(create_options):
    """
    Create and attach a VNIC to this instance.

    Parameters
    ----------
    create_options:
        The VNIC configuration instance.

    Returns
    -------
        No return value on success; errors out with return value 1 otherwise.

    Raises
    ------
        Exception
            if session cannot be acquired
    """
    _logger.debug('_do_create_vnic: create options: %s', create_options)
    # needs the OCI SDK installed and configured
    sess = get_oci_api_session()
    if sess is None:
        raise Exception("Failed to get API session.")

    _this_instance = sess.this_instance()

    subnet_id = None
    if create_options.subnet:
        if not create_options.subnet.startswith('ocid1.subnet.'):
            subnets = sess.find_subnets(create_options.subnet)
            if len(subnets) == 0:
                raise Exception("No subnet matching %s found" % create_options.subnet)
            if len(subnets) > 1:
                _logger.error("More than one subnet matching %s found:\n", create_options.subnet)
                for sn in subnets:
                    _logger.error("   %s\n", sn.get_display_name())
                raise Exception("More than one subnet matching")
            subnet_id = subnets[0].get_ocid()
        else:
            subnet_id = create_options.subnet
        #
    else:
        # if private ip provided, pick up subnet with matching IP
        # else pick the subnet of the primary vnic
        if create_options.ip_address:
            _all_subnets = [v.get_subnet() for v in _this_instance.all_vnics()]
            for subn in _all_subnets:
                if subn.is_suitable_for_ip(create_options.ip_address):
                    subnet_id = subn.get_ocid()
                if subnet_id is None:
                    raise Exception('Cannot find suitable subnet for ip %s' % create_options.ip_address)
        else:
            # We have a primary vnic for sure
            _primary_v = [v for v in _this_instance.all_vnics() if v.is_primary()][0]
            subnet_id = _primary_v.get_subnet_id()
    try:
        vnic = _this_instance.attach_vnic(private_ip=create_options.ip_address,
                                          assign_public_ip=create_options.assign_public_ip,
                                          subnet_id=subnet_id,
                                          nic_index=create_options.nic_index,
                                          display_name=create_options.name)
    except Exception as e:
        raise Exception('Failed to create VNIC: %s' % str(e)) from e

    if not isinstance(vnic, OCIVNIC):
        raise Exception('Failed to attach VNIC %s' % create_options.name)

    public_ip = vnic.get_public_ip()
    if public_ip is not None:
        _logger.info('Creating VNIC: %s (public IP %s)', vnic.get_private_ip(), public_ip)
    else:
        _logger.info('Creating VNIC: %s', vnic.get_private_ip())


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
            _logger.error("More than one VNIC found.Use the --ocid option to select the one to add a secondary IP for:")
            for vnic in vnics:
                _logger.error("   %s: %s", vnic.get_private_ip(), vnic.get_ocid())
            raise Exception("Too many VNICs found")
        vnic = vnics[0]
    try:
        priv_ip = vnic.add_private_ip(private_ip=add_options.ip_address)
    except Exception as e:
        raise Exception('Failed to provision private IP: %s ' % str(e)) from e

    _logger.info('Provisioning secondary private IP: %s', priv_ip.get_address())
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
    priv_ip = sess.this_instance().find_private_ip(delete_options.ip_address)
    if priv_ip is None:
        raise Exception("Secondary private IP not found: %s" % delete_options.ip_address)

    if priv_ip.is_primary():
        raise Exception("Cannot delete IP %s, it is the primary private address of the VNIC."
                        % delete_options.ip_address)

    vnic_id = priv_ip.get_vnic_ocid()

    if not priv_ip.delete():
        raise Exception('Failed to delete secondary private IP %s' % delete_options.ip_address)

    _logger.info('Deconfigure secondary private IP %s', delete_options.ip_address)
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
        _logger.error("This program needs to be run with root privileges.")
        return 1

    vnic_utils = VNICUtils()

    if 'exclude' in args and args.exclude:
        for exc in args.exclude:
            vnic_utils.exclude(exc)

    if 'include' in args and args.include:
        for inc in args.include:
            vnic_utils.include(inc)

    if args.command == 'show':
        #
        # for compatibility mode, oci-network-config show should provide the same output as oci-network-config --show;
        # if output-mode is specified, compatiblity requirement is dropped.
        showerror = False
        if args.compat_output:
            compat_show_vnics_information()
        else:
            try:
                do_show_information(vnic_utils, args.output_mode, args.details)
            except Exception as e:
                _logger.debug('Cannot show information', exc_info=True)
                _logger.error('Cannot show information: %s', str(e))
                showerror = True
        if args.output_mode == 'table':
            show_network_config(vnic_utils)
        return 1 if showerror else 0

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
        do_show_vnics_information(vnics, args.output_mode, args.details)

        return 0

    if args.command == 'attach-vnic':
        if 'nic_index' in args and args.nic_index != 0:
            if not get_oci_api_session().this_shape().startswith("BM"):
                _logger.error('--nic-index option ignored when not runnig on Bare Metal type of shape')
                return 1
        try:
            do_create_vnic(args)
        except Exception as e:
            _logger.debug('Cannot create the VNIC', exc_info=True)
            _logger.error('Cannot create the VNIC: %s', str(e))
            return 1
        # apply config of newly created vnic
        time.sleep(25)
        vnic_utils = VNICUtils()
        vnic_utils.auto_config(None, deconfigured=False)

    if args.command == 'detach-vnic':
        try:
            do_detach_vnic(args)
        except Exception as e:
            _logger.debug('Cannot detach VNIC', exc_info=True, stack_info=True)
            _logger.error('Cannot detach VNIC: %s', str(e))
            return 1
        # if we are here session is alive: no check
        if get_oci_api_session().this_shape().startswith("BM"):
            # in runnning on BM some cleanup is needed on the host
            vnic_utils.auto_config(None, deconfigured=False)

    if args.command == "add-secondary-addr":
        try:
            (ip, vnic_id) = do_add_private_ip(vnic_utils, args)
            _logger.info("IP %s has been assigned to vnic %s.", ip, vnic_id)
        except Exception as e:
            _logger.debug('Failed to add private IP: %s', str(e), stack_info=True)
            _logger.error('Failed to add private IP: %s', str(e))
            return 1

    if args.command == "remove-secondary-addr":
        try:
            (ret, out) = do_del_private_ip(vnic_utils, args)
            if ret != 0:
                raise Exception('Cannot delete ip: %s' % out)
        except Exception as e:
            _logger.debug('Failed to delete private IP: %s', str(e), stack_info=True)
            _logger.error('Failed to delete private IP: %s', str(e))
            return 1

    if 'namespace' in args and args.namespace:
        try:
            vnic_utils.set_namespace(args.namespace)
        except Exception as e:
            _logger.debug('Failed to set namespace: %s', str(e), stack_info=True)
            _logger.error('Failed to set namespace: %s', str(e))

    if 'start_sshd' in args and args.start_sshd:
        try:
            vnic_utils.set_sshd(args.start_sshd)
        except Exception as e:
            _logger.debug('Failed to start sshd: %s', str(e), stack_info=True)
            _logger.error('Failed to start sshd: %s', str(e))

    if args.command == 'configure':
        try:
            vnic_utils.auto_config(args.sec_ip)
            _logger.info('Configured ')
        except Exception as e:
            _logger.debug('Failed to configure network: %s', str(e), stack_info=True)
            _logger.error('Failed to configure network: %s', str(e))

    if args.command == 'unconfigure':
        try:
            vnic_utils.auto_deconfig(args.sec_ip)
            _logger.info('Unconfigured ')
        except Exception as e:
            _logger.debug('Failed to unconfigure network: %s', str(e), stack_info=True)
            _logger.error('Failed to unconfigure network: %s', str(e))

    return 0


if __name__ == "__main__":
    sys.exit(main())
