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
import sys
import time

import oci_utils
import oci_utils.oci_api
from oci_utils import is_root_user
from oci_utils import where_am_i
from oci_utils.impl.network_helpers import add_mac_to_nm
from oci_utils.impl.network_helpers import ipv_version
from oci_utils.impl.network_helpers import is_valid_ip_address
from oci_utils.impl.oci_resources import OCIVNIC
from oci_utils.impl.row_printer import TablePrinter
from oci_utils.impl.row_printer import TextPrinter
from oci_utils.impl.row_printer_helpers import IndentPrinter
from oci_utils.impl.row_printer_helpers import get_value_data
from oci_utils.impl.row_printer_helpers import initialise_column_lengths
from oci_utils.impl.row_printer_helpers import list_to_str
from oci_utils.impl.row_printer_helpers import print_data
from oci_utils.impl.row_printer_helpers import print_vnic_data
from oci_utils.vnicutils import VNICUtils

_logger = logging.getLogger("oci-utils.oci-network-config")
VCN_PREFIX = ['ocid1.vcn.oc']
SUBNET_PREFIX = ['ocid1.subnet.oc']
VNIC_PREFIX = ['ocid1.vnic.oc']


class NetworkConfigException(Exception):
    """Class of exceptions during notification handling
    """
    def __init__(self, message=None):
        """
        Initialisation of the Oci NetworkConfig Exception.

        Parameters
        ----------
        message: str
            The exception message.
        """
        super().__init__()
        self._message = message
        assert (self._message is not None), 'No exception message given, no further information.'

    def __str__(self):
        """
        Get this OCISDKError representation.

        Returns
        -------
        str
            The error message.
        """
        return str(self._message)


class NameWithSpaces(argparse.Action):
    """    Handle argparse arguments containing spaces.
    """
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, " ".join(values))


def def_show_parser(s_parser):
    """
    Define the show subparser.

    Parameters
    ----------
    s_parser: subparsers.

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    show_parser = s_parser.add_parser('show',
                                      description='Shows the current Virtual Interface Cards provisioned in the '
                                                  'Oracle Cloud Infrastructure and configured on this instance. '
                                                  'This is the default action if no options are given.',
                                      help='Shows data of the VNICs configured on this instance.')
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
    show_parser.add_argument('--no-truncate',
                             action='store_true',
                             default=False,
                             help='Do not truncate value during output ')
    show_parser.add_argument('--compat-output',
                             action='store_true',
                             default=False,
                             help=argparse.SUPPRESS)
    return show_parser


def def_show_vnics_parser(s_parser):
    """
    Define the show_vnics subparser

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    show_vnics_parser = s_parser.add_parser('show-vnics',
                                            description='Shows VNICs information of this instance.',
                                            help='Shows VNICs information of this instance.')
    show_vnics_parser.add_argument('--output-mode',
                                   choices=('parsable', 'table', 'json', 'text'),
                                   help='Set output mode.',
                                   default='table')
    show_vnics_parser.add_argument('--details',
                                   action='store_true',
                                   default=False,
                                   help='Display detailed information')
    show_vnics_parser.add_argument('--ocid',
                                   type=vnic_ocid_validator,
                                   action='store',
                                   metavar='VNIC_OCID',
                                   help='Show information of VNIC matching ocid.')
    show_vnics_parser.add_argument('--name',
                                   type=str,
                                   action=NameWithSpaces,
                                   nargs='+',
                                   metavar='VNIC_NAME',
                                   help='Show information of VNIC matching name.')
    show_vnics_parser.add_argument('--ip-address',
                                   type=str,
                                   action='store',
                                   metavar='PRIMARY_IP',
                                   help='Show information of VNIC matching IP as primary IP')
    show_vnics_parser.add_argument('--no-truncate',
                                   action='store_true',
                                   default=False,
                                   help='Do not truncate value during output ')
    return show_vnics_parser


def def_show_vnics_all_parser(s_parser):
    """
    Define the show_vnics_all subparser

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    show_vnics_all_parser = s_parser.add_parser('show-vnics-all',
                                                description='Show all VNICs information with details of this instance.',
                                                help='Show all VNICs information with details of this instance.')
    show_vnics_all_parser.add_argument('-t', '--truncate',
                                       action='store_true',
                                       help=argparse.SUPPRESS)
    show_vnics_all_parser.add_argument('--output-mode',
                                       choices=('parsable', 'table', 'json', 'text'),
                                       help='Set output mode.',
                                       default='table')
    return show_vnics_all_parser


def def_show_vcn_parser(s_parser):
    """
    Define the show_vcn subparser

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    show_vcn_parser = s_parser.add_parser('show-vcns',
                                          description='Show VCN information in this compartment.',
                                          help='Show VCN information in this compartment.')
    show_vcn_parser.add_argument('--output-mode',
                                 choices=('parsable', 'table', 'json', 'text'),
                                 help='Set output mode.',
                                 default='table')
    show_vcn_parser.add_argument('--details',
                                 action='store_true',
                                 default=False,
                                 help='Display detailed information')
    show_vcn_parser.add_argument('--ocid',
                                 type=vcn_ocid_validator,
                                 action='store',
                                 metavar='VCN_OCID',
                                 help='Show information of VCN matching ocid.')
    show_vcn_parser.add_argument('--name',
                                 type=str,
                                 action=NameWithSpaces,
                                 nargs='+',
                                 metavar='VCN_NAME',
                                 help='Show information of VCN matching name.')
    show_vcn_parser.add_argument('--no-truncate',
                                 action='store_true',
                                 default=False,
                                 help='Do not truncate value during output ')
    return show_vcn_parser


def def_show_subnet_parser(s_parser):
    """
    Define the show_subnet subparser

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    show_subnet_parser = s_parser.add_parser('show-subnets',
                                             description='Show subnet information in this compartment.',
                                             help='Show subnet information in this compartment.')
    show_subnet_parser.add_argument('--output-mode',
                                    choices=('parsable', 'table', 'json', 'text'),
                                    help='Set output mode.',
                                    default='table')
    show_subnet_parser.add_argument('--details',
                                    action='store_true',
                                    default=False,
                                    help='Display detailed information')
    show_subnet_parser.add_argument('--ocid',
                                    type=subnet_ocid_validator,
                                    action='store',
                                    metavar='SUBNET_OCID',
                                    help='Show information of subnet matching ocid.')
    show_subnet_parser.add_argument('--name',
                                    type=str,
                                    action=NameWithSpaces,
                                    nargs='+',
                                    metavar='SUBNET_NAME',
                                    help='Show information of subnet matching name.')
    show_subnet_parser.add_argument('--no-truncate',
                                    action='store_true',
                                    default=False,
                                    help='Do not truncate value during output ')
    return show_subnet_parser


def def_configure_parser(s_parser):
    """
    Define the configure subparser

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    configure_parser = s_parser.add_parser('configure',
                                           description='Add IP configuration for VNICs that are not configured '
                                                       'and delete for VNICs that are no longer provisioned.',
                                           help='Add IP configuration for VNICs that are not configured '
                                                'and delete for VNICs that are no longer provisioned.')
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
    return configure_parser


def def_unconfigure_parser(s_parser):
    """
    Define the unconfigure subparser

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    unconfigure_parser = s_parser.add_parser('unconfigure',
                                             description='Unconfigure all VNICs (except the primary).',
                                             help='Unconfigure all VNICs (except the primary).')
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
    return unconfigure_parser


def def_attach_vnic_parser(s_parser):
    """
    Define the attach_vnic subparser

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    attach_vnic_parser = s_parser.add_parser('attach-vnic',
                                             description='Create a new VNIC and attach it to this instance.',
                                             help='Create a new VNIC and attach it to this instance.')
    attach_vnic_parser.add_argument('-I', '--ip-address',
                                    action='store',
                                    metavar='IP_ADDR',
                                    type=ip_address_validator,
                                    help="Private IP to be assigned to the new VNIC.")
    ipv = attach_vnic_parser.add_mutually_exclusive_group()
    ipv.add_argument('-ipv4', '--ipv4',
                     action='store_true',
                     default=False,
                     help='Add an ipv4 address, by default.')
    ipv.add_argument('-ipv6', '--ipv6',
                     action='store_true',
                     default=False,
                     help='Add an ipv6 address.')
    attach_vnic_parser.add_argument('-i', '--nic-index',
                                    action='store',
                                    metavar='INDEX',
                                    type=int,
                                    default=0,
                                    help='Physical NIC card index.')
    attach_vnic_parser.add_argument('--subnet',
                                    action='store',
                                    metavar='SUBNET',
                                    type=str,
                                    # type=subnet_ocid_validator,
                                    help='Connect the new VNIC to the subnet with the given OCID.')
    attach_vnic_parser.add_argument('-n', '--name',
                                    action=NameWithSpaces,
                                    nargs='+',
                                    metavar='NAME',
                                    help='Use NAME as the display name of the new VNIC.')
    attach_vnic_parser.add_argument('--assign-public-ip',
                                    action='store_true',
                                    help='assign a public IP address to the new VNIC.')
    return attach_vnic_parser


def def_detach_vnic_parser(s_parser):
    """
    Define the detach_vnic subparser

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    detach_vnic_parser = s_parser.add_parser('detach-vnic',
                                             description='Detach and delete the VNIC with the given OCID or '
                                                         'primary IP address.',
                                             help='Detach and delete the VNIC with the given OCID or '
                                                  'primary IP address.')
    dg = detach_vnic_parser.add_mutually_exclusive_group(required=True)
    dg.add_argument('-O', '--ocid',
                    action='store',
                    type=vnic_ocid_validator,
                    metavar='OCID',
                    help='Detach the VNIC with the given OCID.')
    dg.add_argument('-I', '--ip-address',
                    action='store',
                    metavar='IP_ADDR',
                    help='Detach the VNIC with the given ip address configured on it.')
    return detach_vnic_parser


def def_add_secondary_addr_parser(s_parser):
    """
    Define the add_secondary_ip subparser

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    add_secondary_addr = s_parser.add_parser('add-secondary-addr',
                                             description="Adds the given secondary private IP.",
                                             help="Adds the given secondary private IP.")

    ipv = add_secondary_addr.add_mutually_exclusive_group()
    ipv.add_argument('-ipv4', '--ipv4',
                     action='store_true',
                     default=False,
                     help='Add an ipv4 address, by default.')
    ipv.add_argument('-ipv6', '--ipv6',
                     action='store_true',
                     default=False,
                     help='Add an ipv6 address.')
    add_secondary_addr.add_argument('-I', '--ip-address',
                                    action='store',
                                    metavar='IP_ADDR',
                                    help='Secondary private IP address to to be added.')
    add_secondary_addr.add_argument('-O', '--ocid',
                                    action='store',
                                    type=vnic_ocid_validator,
                                    metavar='OCID',
                                    help='Uses VNIC with the given VNIC id.')
    return add_secondary_addr


def def_remove_secondary_addr_parser(s_parser):
    """
    Define the remove_secondary_ipv4 subparser

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    remove_secondary_addr = s_parser.add_parser('remove-secondary-addr',
                                                description='Removes the given secondary private IP.',
                                                help='Removes the given secondary private IP.')
    remove_secondary_addr.add_argument('-I', '--ip-address',
                                       action='store',
                                       type=ip_address_validator,
                                       metavar='IP_ADDR',
                                       help='Secondary private addr to to be removed.',
                                       required=True)
    return remove_secondary_addr


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
    subparser.add_parser('usage', description='Displays usage')
    #
    # show
    _ = def_show_parser(subparser)
    #
    # show-vnics
    _ = def_show_vnics_parser(subparser)
    #
    # show-vnics-all
    _ = def_show_vnics_all_parser(subparser)
    #
    # show vncs
    _ = def_show_vcn_parser(subparser)
    #
    # show subnets
    _ = def_show_subnet_parser(subparser)
    #
    # configure
    _ = def_configure_parser(subparser)
    #
    # unconfigure
    _ = def_unconfigure_parser(subparser)
    #
    # attach vnic
    _ = def_attach_vnic_parser(subparser)
    #
    # detach vnic
    _ = def_detach_vnic_parser(subparser)
    #
    #  add secondary ipv4 address
    _ = def_add_secondary_addr_parser(subparser)
    #
    # remove secondary ip address
    _ = def_remove_secondary_addr_parser(subparser)

    return parser


def show_usage(usage_args):
    """
    Wrapper for showing usage info.

    Parameters
    ----------
    usage_args:
        The command line arguments.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    return True


def uniq_item_validator(value):
    """
    Validates unicity by checking that value not already in the list

    Parameter
    ---------
        value : str , option's value
    """
    _logger.debug('%s', where_am_i())
    already_seen = getattr(uniq_item_validator, "_item_seen", [])
    if value in already_seen:
        raise argparse.ArgumentTypeError("Invalid arguments: item both included and excluded: %s" % value)
    already_seen.append(value)
    setattr(uniq_item_validator, "_item_seen", already_seen)

    return value


def validate_vnic_ocid(value):
    """
    Verify the value is a vnic ocid.

    Parameters
    ----------
    value: str
        The ocid

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    for prefix in VNIC_PREFIX:
        if value.startswith(prefix):
            return value
    return False


def vnic_ocid_validator(value):
    """
    Validates the value passed is a VNIC ocid

    Parameter:
    ----------
        value : option's value as str
    """
    _logger.debug('%s', where_am_i())
    if validate_vnic_ocid(value):
        return value
    raise argparse.ArgumentTypeError("Invalid arguments: invalid VNIC ocid : %s" % value)


def validate_vcn_ocid(value):
    """
    Verify the value is a vcn ocid.

    Parameters
    ----------
    value: str
        The ocid

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    for prefix in VCN_PREFIX:
        if value.startswith(prefix):
            return value
    return False


def vcn_ocid_validator(value):
    """
    Validate the value passed is a Vcn ocid

    Parameter:
    ----------
        value : option's value as str
    """
    _logger.debug('%s', where_am_i())
    if validate_vcn_ocid(value):
        return value
    raise argparse.ArgumentTypeError("Invalid arguments: invalid VCN ocid : %s" % value)


def validate_subnet_ocid(value):
    """
    Verify the value is a subnet ocid.

    Parameters
    ----------
    value: str
        The ocid

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    for prefix in SUBNET_PREFIX:
        if value.startswith(prefix):
            return True
    return False


def subnet_ocid_validator(value):
    """
    Validate the value passed is a VNIC ocid

    Parameters:
    -----------
    value : str
        The ocid
    """
    _logger.debug('%s', where_am_i())
    if validate_subnet_ocid(value):
        return value
    raise argparse.ArgumentTypeError("Invalid arguments: invalid subnet ocid : %s" % value)


def ip_address_validator(value):
    """
    Verify if the provided address is a valid IPv[4|6] address.

    Parameters
    ----------
    value: str
        The ip address.

    Returns
    -------
        value: the ip address
    """
    _logger.debug('%s', where_am_i())
    if is_valid_ip_address(value):
        return value
    _logger.debug('Invalid ip address.')
    raise argparse.ArgumentTypeError('Invalid arguments: %s is not a valid IP address.' % value)


def get_conf_states(vnics):
    """
    Get configuration state of the vnic,

    Parameters
    ----------
    vnics: OCIVNIC
        The OCIVNIC object.

    Returns
    -------
        dict: The configuration states.
    """
    _logger.debug('%s', where_am_i())
    _network_config = VNICUtils().get_network_config()
    conf_states = dict()
    for vnic in vnics:
        priv_ip = vnic.get_private_ip()
        for network in _network_config:
            if priv_ip == network['ADDR']:
                conf_states[priv_ip] = network['CONFSTATE']
                break
    return conf_states


def get_oci_api_session():
    """
    Ensure the OCI SDK is available if the option is not None.

    Returns
    -------
        OCISession
            The session or None, if we cannot get one
    """
    _logger.debug('%s', where_am_i())
    session_cache = getattr(get_oci_api_session, "_session", None)
    if session_cache:
        return session_cache

    sess = None
    try:
        _logger.debug('Creating session')
        sess = oci_utils.oci_api.OCISession()
        # it seems that having a client is not enough, we may not be able to query anything on it
        # work around but not full-proof:
        # try a dummy call to be sure that we can use this session
        if not bool(sess.this_instance()):
            _logger.debug('Returning None session')
            return None
        setattr(get_oci_api_session, "_session", sess)
    except Exception as e:
        _logger.error("Failed to access OCI services: %s", str(e))
    _logger.debug('Returning session')
    return sess


def compat_show_vnics_information():
    """
    Show the current VNIC configuration of the instance based on

    Returns
    -------
       No return value.
    """
    def _display_subnet(_, vn):
        """Return subnet display name of this vnic
        """
        return vn.get_subnet().get_display_name()

    def _display_secondary_ip_subnet(_, privip):
        _sn = privip.get_subnet()
        return '%s (%s)' % (_sn.get_display_name(), _sn.get_ipv4_cidr_block())

    def _display_vnic_name(_, vn):
        return '%s (primary)' % vn.get_display_name() if vn.is_primary() else vn.get_display_name()

    _logger.debug('%s', where_am_i())
    oci_session = get_oci_api_session()
    if oci_session is None:
        _logger.error("Failed to get API session.")
        return
    instance = oci_session.this_instance()
    if instance is None:
        _logger.error("Failed to get information from OCI.")
        return
    _logger.debug('Getting all vnics ')
    vnics = instance.all_vnics()
    _logger.debug('Got all vnics for printing')

    _title = 'VNIC configuration for instance %s:' % instance.get_display_name()

    _columns = (['Name', 32, _display_vnic_name],
                ['Hostname', 25, 'get_hostname'],
                ['MAC', 17, 'get_mac_address'],
                ['Public IP', 15, 'get_public_ip'],
                ['Private IP(s)', 15, 'get_private_ip'],
                ['Subnet', 18, _display_subnet],
                ['OCID', 90, 'get_ocid'])

    printer = TextPrinter(title=_title, columns=_columns, column_separator=' ')
    ips_printer = TextPrinter(title='Private IP addresses:',
                              columns=(['IP address', 15, 'get_address'],
                                       ['OCID', '90', 'get_ocid'],
                                       ['Hostname', 25, 'get_hostname'],
                                       ['Subnet', 24, _display_secondary_ip_subnet]),
                              printer=IndentPrinter(3))

    printer.printHeader()
    for vnic in vnics:
        printer.printRow(vnic)
        #
        # to check if compatible mode works with ipv6 as soon as primary ipv6 address for a vnic and/or single stack
        # ipv6 is implemented on OCI and oci sdk:
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


def do_show_information(nic_list, args):
    """
    Show network information.

    Parameters
    ----------
    nic_list:
        list: list of network data.
    args: namespace
        The command line.

    Returns
    -------
        No return value.
    """
    _logger.debug('%s', where_am_i())
    _data_struct = {
        'state':     {'head': 'State',      'item': 'CONFSTATE', 'type': 'str', 'collen': 6},
        'link':      {'head': 'Link',       'item': 'IFACE',     'type': 'str', 'collen': 5},
        'status':    {'head': 'Status',     'item': 'STATE',     'type': 'str', 'collen': 6},
        'ipaddress': {'head': 'IP address', 'item': 'ADDR',      'type': 'str', 'collen': 9},
        'vnic':      {'head': 'VNIC',       'item': 'VNICNAME',  'type': 'str', 'collen': 6},
        'mac':       {'head': 'MAC',        'item': 'MAC',       'type': 'str', 'collen': 17}
    }
    _data_struct_detail = {
        'hostname':  {'head': 'Hostname',    'item': 'HOSTNAME', 'type': 'str', 'collen': 8},
        'subnet':    {'head': 'Subnet',      'item': 'SUBNET',   'type': 'str', 'collen': 10},
        'routerip':  {'head': 'Router IPv4', 'item': 'VIRTRT4',  'type': 'str', 'collen': 9},
        'routerip6': {'head': 'Router IPv6', 'item': 'VIRTRT6',  'type': 'str', 'collen': 9},
        'namespace': {'head': 'Namespace',   'item': 'NS',       'type': 'str', 'collen': 9},
        'index':     {'head': 'Index',       'item': 'IND',      'type': 'str', 'collen': 5},
        'vlantag':   {'head': 'VLAN tag',    'item': 'VLTAG',    'type': 'str', 'collen': 8},
        'vlan':      {'head': 'VLAN',        'item': 'VLAN',     'type': 'str', 'collen': 4}
    }
    #
    # add details information
    if args.details:
        _data_struct.update(_data_struct_detail)
    #
    # initialise the column widths if no-truncate is set
    if args.no_truncate:
        _data_struct = initialise_column_lengths(_data_struct)
    #
    nic_data = list()
    for _nic in nic_list:
        _nic_dict = dict()
        for key, _ in _data_struct.items():
            value_data = get_value_data(_nic, _data_struct[key])
            _nic_dict[key] = value_data[0]
            val_length = value_data[1]
            if args.no_truncate:
                _data_struct[key]['collen'] = max(val_length, _data_struct[key]['collen'])
        nic_data.append(_nic_dict)
    #
    print_data('Network Configuration',
               _data_struct,
               nic_data,
               mode=args.output_mode,
               truncate=not args.no_truncate)
    return True


def update_network_config(nw_conf):
    """
    Add data from vnic to the network data.

    Parameters
    ----------
    nw_conf: list
        List of network configuration data.

    Returns
    -------
        list: list of updated network configuration data.
    """
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
        _logger.debug('%s', where_am_i())
        if interface['VNIC']:
            for v in vnics:
                if v.get_ocid() == interface['VNIC']:
                    return v.get_display_name()
        return '-'

    def _get_hostname(interface):
        """
        Return the interfaces' hostname.

        Parameters
        ----------
        interface: dict
            The interface.

        Returns
        -------
            str: the vnic hostname if the interface matches a vnic, else '-'
        """
        _logger.debug('%s', where_am_i())
        if interface['VNIC']:
            for v in vnics:
                if v.get_ocid() == interface['VNIC']:
                    v_hostname = v.get_hostname()
                    return 'None' if v_hostname is None else v_hostname
        return '-'

    def _display_subnet(interface):
        """
        Return the network subnet.

        Parameters
        ----------
        interface: dict
            The interface.

        Returns
        -------
            str: the network subnet or if the interface matches a vnic, the OCI vnic subnet.
        """
        _logger.debug('%s', where_am_i())
        if interface['VNIC']:
            for v in vnics:
                if v.get_ocid() == interface['VNIC']:
                    v_subnet = [interface['SPREFIX4'], interface['SBITS4']]
                    return '%s/%s (%s)' % (v_subnet[0], v_subnet[1], v.get_subnet().get_display_name())
        return '%s/%s' % (interface['SPREFIX4'], interface['SBITS4'])

    _logger.debug('%s', where_am_i())
    sess = get_oci_api_session()
    if sess is None:
        raise Exception("Failed to get API session.")
    vnics = sess.this_instance().all_vnics()

    for _nic in nw_conf:
        _nic['VNICNAME'] = _get_vnic_name(_nic)
        _nic['HOSTNAME'] = _get_hostname(_nic)
        _nic['SUBNET'] = _display_subnet(_nic)
    return nw_conf


def show_os_network_config(vnic_utils):
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
        return '%s/%s' % (interface['SPREFIX4'], interface['SBITS4'])

    _logger.debug('%s', where_am_i())
    ret = vnic_utils.get_network_config()

    _title = "Operating System level network configuration:"
    _columns = (['CONFIG', 6, 'CONFSTATE'],
                ['ADDR', 15, 'ADDR'],
                ['SUBNET', 15, 'SPREFIX4'],
                ['BITS', 5, 'SBITS4'],
                ['VIRTROUTER', 15, 'VIRTRT4'],
                ['NS', 10, 'NS'],
                ['IND', 4, 'IND'],
                ['IFACE', 15, 'IFACE'],
                ['VLTAG', 5, 'VLTAG'],
                ['VLAN', 13, 'VLAN'],
                ['STATE', 6, 'STATE'],
                ['MAC', 18, 'MAC'],
                ['VNIC ID', 95, 'VNIC'])
    printer = TablePrinter(title=_title, columns=_columns, column_separator=' ', text_truncate=False)

    printer.printHeader()
    for item in ret:
        printer.printRow(item)
    printer.printFooter()
    printer.finish()


def show_network(show_args):
    """
    Display the network information.

    Parameters
    ----------
    show_args: namespace
        The command line arguments.

    Returns
    -------
        int: 0 on success, 1 otherwise.
    """
    _logger.debug('%s', where_am_i())
    vnic_utils = get_vnic_utils(show_args)

    network_config = vnic_utils.get_network_config()
    network_config = update_network_config(network_config)
    #
    # for compatibility mode, oci-network-config show should provide the same output as oci-network-config --show;
    # if output-mode is specified, compatiblity requirement is dropped.
    showerror = False
    if show_args.compat_output:
        compat_show_vnics_information()
    else:
        try:
            do_show_information(network_config, show_args)
        except Exception as e:
            _logger.debug('Cannot show information', exc_info=True)
            _logger.error('Cannot show information: %s', str(e))
            showerror = True
    if show_args.output_mode == 'table':
        show_os_network_config(vnic_utils)
    return False if showerror else True


def do_show_vnics_information(vnics, args):
    """
    Show given VNIC information.

    Parameters:
    ----------
        vnics: OCIVNIC instances
        mode: the output mode as str (text,json,parsable)
        details: display detailed information ?
    """
    _logger.debug('%s', where_am_i())
    _data_struct = {
        'name':       {'head': 'Name',       'func':  'get_display_name', 'type': 'str', 'collen': 20},
        'privateip':  {'head': 'Private IP', 'func':  'get_private_ip',   'type': 'str', 'collen': 10},
        'mac':        {'head': 'MAC',        'func':  'get_mac_address',  'type': 'str', 'collen': 17},
        'config':     {'head': 'Config',     'item':  'get_conf_state',   'type': 'str', 'collen': 6}
        # this function fails intentionally, data is completed below
        # todo: implement decent way to get this data.
    }
    _data_struct_detail = {
        'ocid':               {'head': 'OCID',                'func': 'get_ocid',                            'type': 'str',  'collen': 32},
        'primary':            {'head': 'Primary',             'func': 'is_primary',                          'type': 'bool', 'collen': 7},
        'subnetname':         {'head': 'Subnet',              'func': ['get_subnet', 'get_display_name'],    'type': 'str',  'collen': 15},
        'subnetid':           {'head': 'Subnet OCID',         'func': ['get_subnet', 'get_ocid'],            'type': 'str',  'collen': 32},
        'subnetcidr':         {'head': 'Subnet cidr',         'func': ['get_subnet', 'get_ipv4_cidr_block'], 'type': 'str',  'collen': 15},
        'state':              {'head': 'State',               'func': 'get_state',                           'type': 'str',  'collen': 6},
        'mic':                {'head': 'NIC',                 'func': 'get_nic_index',                       'type': 'str',  'collen': 3},
        'public':             {'head': 'Public IP',           'func': 'get_public_ip',                       'type': 'str',  'collen': 15},
    }

    _data_struct_secondary = {
        'privateip':     {'head': 'Private IP', 'func': 'get_address', 'type': 'str', 'collen': 15},
        'ocid':          {'head': 'OCID',       'func': 'get_ocid',    'type': 'str', 'collen': 32},
    }
    #
    # remove vcn uuid if output mode is table
    if args.output_mode in ['table']:
        _data_struct_detail.pop('subnetid', None)
    #
    # add details information
    if args.details:
        _data_struct.update(_data_struct_detail)
    #
    # initialise the column widths
    if args.no_truncate:
        _data_struct = initialise_column_lengths(_data_struct)
        _data_struct_secondary = initialise_column_lengths(_data_struct_secondary)
    #
    conf_states = get_conf_states(vnics)
    #
    vnic_data = list()
    for _vnic in vnics:
        _vnic_dict = dict()

        for key, _ in _data_struct.items():
            value_data = get_value_data(_vnic, _data_struct[key])
            _vnic_dict[key] = value_data[0]
            val_length = value_data[1]
            if args.no_truncate:
                _data_struct[key]['collen'] = max(val_length, _data_struct[key]['collen'])
        #
        # conf state
        _vnic_dict['config'] = conf_states[_vnic_dict['privateip']]
        val_length = len(_vnic_dict['config'])
        if args.no_truncate:
            _data_struct['config']['collen'] = max(val_length, _data_struct['config']['collen'])
        #
        if args.details:
            _priv_ipv4s = _vnic.all_private_ipv4_ips()
            if len(_priv_ipv4s) > 0:
                ipv4_data = list()
                for _priv_ipv4 in _priv_ipv4s:
                    _priv_ipv4_dict = dict()
                    for key, _ in _data_struct_secondary.items():
                        value_data = get_value_data(_priv_ipv4, _data_struct_secondary[key])
                        _priv_ipv4_dict[key] = value_data[0]
                        val_length = value_data[1]
                        if args.no_truncate:
                            _data_struct_secondary[key]['collen'] \
                                = max(val_length, _data_struct_secondary[key]['collen'])
                    ipv4_data.append(_priv_ipv4_dict)
                _vnic_dict['ipv4'] = ipv4_data

            _priv_ipv6s = _vnic.all_private_ipv6_ips()
            if len(_priv_ipv6s) > 0:
                ipv6_data = list()
                for _priv_ipv6 in _priv_ipv6s:
                    _priv_ipv6_dict = dict()
                    for key, _ in _data_struct_secondary.items():
                        value_data = get_value_data(_priv_ipv6, _data_struct_secondary[key])
                        _priv_ipv6_dict[key] = value_data[0]
                        val_length = value_data[1]
                        if args.no_truncate:
                            _data_struct_secondary[key]['collen'] \
                                = max(val_length, _data_struct_secondary[key]['collen'])
                    ipv6_data.append(_priv_ipv6_dict)
                _vnic_dict['ipv6'] = ipv6_data

        vnic_data.append(_vnic_dict)
    #
    print_vnic_data('Virtual Network Interface Information:', _data_struct, _data_struct_secondary, vnic_data,
                    mode=args.output_mode,
                    truncate=not args.no_truncate)


def show_vnics(args):
    """
    Show Virtual Network Interface data.

    Parameters
    ----------
    args: namespace
        The command line.

    Returns
    -------
        No return value.
    """
    _logger.debug('%s', where_am_i())
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
    do_show_vnics_information(vnics, args)
    return True


def show_vnics_all(args):
    """
    Show all Virtual Network Interface data.

    Parameters
    ----------
    args: namespace
        The command line.

    Returns
    -------
        No return value.
    """
    _logger.debug('%s', where_am_i())
    args.no_truncate = True
    args.details = True
    args.ocid = None
    args.ip_address = None
    args.name = None
    return show_vnics(args)


def do_show_vcn_information(vcn_list, args):
    """
    Display virtual cloud network data.

    Parameters
    ----------
    vcn_list: list of OCIVCN
        The list of vnics.
    args: namespace
        The command line arguments.

    Returns
    -------
        No return value.
    """
    _logger.debug('%s', where_am_i())
    #
    #
    _data_struct = {
        'name':  {'head': 'Name',             'func': 'get_display_name',     'type': 'str', 'collen': 20},
        'ipv4':  {'head': 'IPv4 cidr block',  'func': 'get_ipv4_cidr_block',  'type': 'str', 'collen': 15},
        'ipv6':  {'head': 'IPv6 cidr block',  'func': 'get_ipv6_cidr_blocks', 'type': 'str', 'collen': 20, 'convert': list_to_str}
    }
    _data_struct_detail = {
        'uuid':  {'head': 'OCID',             'func': 'get_ocid',             'type': 'str', 'collen': 32},
        'ipv4s': {'head': 'IPv4 cidr blocks', 'func': 'get_ipv4_cidr_blocks', 'type': 'str', 'collen': 16, 'convert': list_to_str},
        'dns':   {'head': 'DNS label',        'func': 'get_dns_label',        'type': 'str', 'collen': 10},
        'state': {'head': 'State',            'func': 'get_state',            'type': 'str', 'collen': 10},
        'life ': {'head': 'Lifecycle state',  'func': 'get_lifecycle_state',  'type': 'str', 'collen': 17}
    }
    #
    # add details if requested.
    if args.details:
        _data_struct.update(_data_struct_detail)
    #
    # initialise the column widths if no-truncate is set
    if args.no_truncate:
        _data_struct = initialise_column_lengths(_data_struct)
    #
    vcn_data = list()
    for _vcn in vcn_list:
        _vcn_dict = dict()
        for key, _ in _data_struct.items():
            value_data = get_value_data(_vcn, _data_struct[key])
            _vcn_dict[key] = value_data[0]
            val_length = value_data[1]
            if args.no_truncate:
                _data_struct[key]['collen'] = max(val_length, _data_struct[key]['collen'])
        vcn_data.append(_vcn_dict)
    #
    print_data('Virtual Cloud Network Information:',
               _data_struct,
               vcn_data,
               mode=args.output_mode,
               truncate=not args.no_truncate)


def show_vcns(args):
    """
    Show virtual cloud network data.

    Parameters
    ----------
    args: namespace
        The command line.

    Returns
    -------
        No return value.
    """
    _logger.debug('%s', where_am_i())
    sess = get_oci_api_session()
    if sess is None:
        _logger.error("Failed to get API session.")
        return 1
    vcns = set()
    _vcns = sess.all_vcns()
    if not args.ocid and not args.name:
        vcns.update(_vcns)
    else:
        if args.ocid:
            for v in _vcns:
                if v.get_ocid() == args.ocid:
                    vcns.add(v)
        if args.name:
            for v in _vcns:
                if v.get_display_name() == args.name:
                    vcns.add(v)
    do_show_vcn_information(vcns, args)
    return True


def do_show_subnet_information(subnet_list, args):
    """
    Display subnetdata.

    Parameters
    ----------
    subnet_list: list of OCISubnet
        The list of subnets.
    args: namespace
        The command line.

    Returns
    -------
        No return value.
    """
    _logger.debug('%s', where_am_i())
    #
    #
    _data_struct = {
        'name':  {'head': 'Name',               'func': 'get_display_name',                    'type': 'str', 'collen': 20},
        'ipv4':  {'head': 'ipv4 cidr block',    'func': 'get_ipv4_cidr_block',                 'type': 'str', 'collen': 15},
        'ipv6':  {'head': 'ipv6 cidr block',    'func': 'get_ipv6_cidr_block',                 'type': 'str', 'collen': 20}
    }
    _data_struct_detail = {
        'uuid':     {'head': 'OCID',            'func': 'get_ocid',                            'type': 'str',  'collen': 32},
        'vcn':      {'head': 'VCN name',        'func': 'get_vcn_name',                        'type': 'str',  'collen': 20},
        'vcnid':    {'head': 'VCN ocid',        'func': 'get_vcn_id',                          'type': 'str',  'collen': 32},
        'public':   {'head': 'Public',          'func': 'is_public_ip_on_vnic_allowed',        'type': 'bool', 'collen': 6},
        'publicin': {'head': 'Public ingress',  'func': 'is_internet_ingress_on_vnic_allowed', 'type': 'bool', 'collen': 14},
        'dns':      {'head': 'DNS label',       'func': 'get_dns_label',                       'type': 'str',  'collen': 11},
        'domain':   {'head': 'Domain name',     'func': 'get_domain_name',                     'type': 'str',  'collen': 20},
        'life ':    {'head': 'Lifecycle state', 'func': 'get_lifecycle_state',                 'type': 'str',  'collen': 17}
    }
    #
    # remove vcn uuid if output mode is table
    if args.output_mode in ['table']:
        _data_struct_detail.pop('vcnid', None)
    #
    # add details if necessary
    if args.details:
        _data_struct.update(_data_struct_detail)
    #
    # initialise the column widths
    if args.no_truncate:
        _data_struct = initialise_column_lengths(_data_struct)
    #
    subnet_data = list()
    for _subn in subnet_list:
        _subn_dict = dict()
        for key, _ in _data_struct.items():
            value_data = get_value_data(_subn, _data_struct[key])
            _subn_dict[key] = value_data[0]
            val_length = value_data[1]
            if args.no_truncate:
                _data_struct[key]['collen'] = max(val_length, _data_struct[key]['collen'])
        subnet_data.append(_subn_dict)
    #
    print_data('Subnet Information:', _data_struct, subnet_data, mode=args.output_mode, truncate=not args.no_truncate)


def show_subnets(args):
    """
    Show virtual cloud subnet data.

    Parameters
    ----------
    args: namespace
        The command line.

    Returns
    -------
        No return value.
    """
    _logger.debug('%s', where_am_i())
    sess = get_oci_api_session()
    if sess is None:
        _logger.error("Failed to get API session.")
        return 1
    subnets = set()
    _subnets = sess.all_subnets()
    if not args.ocid and not args.name:
        subnets.update(_subnets)
    else:
        if args.ocid:
            for s in _subnets:
                if s.get_ocid() == args.ocid:
                    subnets.add(s)
        if args.name:
            for s in _subnets:
                if s.get_display_name() == args.name:
                    subnets.add(s)
    do_show_subnet_information(subnets, args)
    return True


def get_ipv_version(args):
    """
    Get the ip version from the commandline, default is 4.

    Parameters
    ----------
    args: namespace
        command line.
    Returns
    -------
        int: the IP version.
    """
    if args.ipv4:
        return 4
    if args.ipv6:
        return 6
    return 4


def get_vnic_utils(args):
    """
    Collect the VNIC data.

    Parameters
    ----------
    args: namespace
        The command lind arguments.

    Returns
    -------
        VNICUtils: the data.
    """
    _logger.debug('%s', where_am_i())
    vnic_utls = VNICUtils()

    if 'exclude' in args and args.exclude:
        for exc in args.exclude:
            vnic_utls.exclude(exc)

    if 'include' in args and args.include:
        for inc in args.include:
            vnic_utls.include(inc)
    return vnic_utls


def get_subnet_ocid_from_arg(this_session, subnet_arg):
    """
    Get the ocid for the subnet data provided on the command line.

    Parameters
    ----------
    this_session: OCISession
        The oci-sdk session.
    subnet_arg: str
        The subnet data from the command line.

    Returns
    -------
        str: the ocid of the subnet, if found.
    """
    _logger.debug('%s: %s', where_am_i(), subnet_arg)
    #
    # subnet specified in command line
    if not validate_subnet_ocid(subnet_arg):
        #
        # subnet name
        subnets = this_session.find_subnets(subnet_arg)
        if len(subnets) == 0:
            raise Exception("No subnet matching %s found" % subnet_arg)
        if len(subnets) > 1:
            _logger.error("More than one subnet matching %s found:\n", subnet_arg)
            for sn in subnets:
                _logger.error("   %s\n", sn.get_display_name())
            raise Exception("More than one subnet matching")
        return subnets[0].get_ocid()
    #
    # subnet ocid
    return subnet_arg


def get_subnet_ocid_from_ip(this_instance, ip_arg):
    """
    Get the ocid for the subnet the provided ip address belongs to.

    Parameters
    ----------
    this_instance: OCIInstance
        The instance object.

    ip_arg: str
        The ip address.

    Returns
    -------
        str: the ocid of the subnet, if found.
    """
    _logger.debug('%s: %s', where_am_i(), ip_arg)
    subnet_id = None
    _all_subnets = [v.get_subnet() for v in this_instance.all_vnics()]
    for subn in _all_subnets:
        if subn.is_suitable_for_ip(ip_arg):
            subnet_id = subn.get_ocid()
    if subnet_id is None:
        raise Exception('Cannot find suitable subnet for ip %s' % ip_arg)
    return subnet_id


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
    _logger.debug('%s: %s', where_am_i(), create_options)
    # needs the OCI SDK installed and configured
    session = get_oci_api_session()
    if session is None:
        raise Exception("Failed to get API session.")

    the_instance = session.this_instance()

    subnet_id = None
    if create_options.subnet:
        #
        # subnet data provided on command line.
        subnet_id = get_subnet_ocid_from_arg(session, create_options.subnet)
    else:
        #
        # no subnet data on the command line.
        #
        # if private ip provided, pick up subnet with matching IP
        # else pick the subnet of the primary vnic
        if create_options.ip_address:
            #
            # private ip provided, look for subnet the ip belongs to.
            if is_valid_ip_address(create_options.ip_address):
                subnet_id = get_subnet_ocid_from_ip(the_instance, create_options.ip_address)
            else:
                raise Exception('Invalid ip address format.')
        else:
            #
            # No subnet nor ip provided, use the primary vnic.
            _primary_v = [v for v in the_instance.all_vnics() if v.is_primary()][0]
            subnet_id = _primary_v.get_subnet_id()
    _logger.debug('Subnet ocid used: %s', subnet_id)

    try:
        vnic = the_instance.attach_vnic(private_ip=create_options.ip_address,
                                        assign_public_ip=create_options.assign_public_ip,
                                        subnet_id=subnet_id,
                                        nic_index=create_options.nic_index,
                                        display_name=create_options.name,
                                        ipv=create_options.ipv)
    except Exception as e:
        # raise Exception('Failed to create VNIC: %s' % str(e)) from e
        raise ValueError('%s' % str(e)) from e

    if not isinstance(vnic, OCIVNIC):
        raise ValueError('Failed to attach VNIC %s' % create_options.name)

    #
    #
    public_ip = vnic.get_public_ip()
    if public_ip is not None:
        _logger.info('Creating VNIC: %s (public IP %s)', vnic.get_private_ip(), public_ip)
    else:
        _logger.info('Creating VNIC: %s', vnic.get_private_ip())


def ipv_not_supported(ipv):
    """
    Write a messages attaching a vnic with primary ipv6 address is not (yet) supported.
    Parameters
    ----------
    ipv: int
        The ipv version.
    Returns
    -------
        No return value.
    """
    _logger.debug('%s', where_am_i())
    if ipv == 6:
        _logger.warning('Attaching a vnic with a primary ipv%d address is not yet supported by OCI.', ipv)
        sys.exit(1)


def attach_vnic(args):
    """
    Attach a new Virtula Network Interface Card to the instance.

    Parameters
    ----------
    args: namespace
        The command line.

    Returns
    -------
        bool: True
    """
    _logger.debug('%s', where_am_i())
    args.ipv = get_ipv_version(args)
    #
    # OCI does not support creating a vnic with an ipv6 address only.
    ipv_not_supported(args.ipv)
    if 'nic_index' in args and args.nic_index != 0:
        if not get_oci_api_session().this_shape().startswith("BM"):
            _logger.error('--nic-index option ignored when not runnig on Bare Metal type of shape')
            return 1
    try:
        do_create_vnic(args)
    except Exception as e:
        _logger.debug('Cannot create the VNIC', exc_info=True)
        _logger.error('%s', str(e))
        return 1
    #
    # apply config of newly created vnic
    time.sleep(25)
    vnic_utils = VNICUtils()
    vnic_utils.auto_config(None, deconfigured=False)
    return True


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
    _logger.debug('%s', where_am_i())
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
                macaddress = vnic.get_mac_address()
                vnic.detach()
                _logger.info('VNIC [%s] is detached.', v_ocid)
                add_mac_to_nm(macaddress)
                _logger.debug('Added mac address %s back to nm.', macaddress)
                break
            raise Exception("The primary VNIC cannot be detached.")
    else:
        _logger.error('VNIC %s [%s] is not attached to this instance.', detach_options.ip_address, detach_options.ocid)


def detach_vnic(args):
    """
    Detach a new Virtula Network Interface Card to the instance.

    Parameters
    ----------
    args: namespace
        The command line.

    Returns
    -------
        bool: True on success, false otherwise.
    """
    _logger.debug('%s', where_am_i())
    try:
        do_detach_vnic(args)
    except Exception as e:
        _logger.debug('Cannot detach VNIC', exc_info=True, stack_info=True)
        # _logger.error('Cannot detach VNIC: %s', str(e))
        _logger.error('%s', str(e))
        return False
    # if we are here session is alive: no check
    vnic_utils = get_vnic_utils(args)
    if get_oci_api_session().this_shape().startswith("BM"):
        # in runnning on BM some cleanup is needed on the host
        vnic_utils.auto_config(None, deconfigured=False)
    return True


def do_add_secondary_addr(vnic_utils, add_options):
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
    _logger.debug('%s', where_am_i())
    # needs the OCI SDK installed and configured
    sess = get_oci_api_session()
    if sess is None:
        raise Exception("Failed to get API session.")

    if add_options.ocid:
        vnic = sess.get_vnic(vnic_id=add_options.ocid)
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

    if add_options.ipv == 4:
        priv_ip, ip_ocid = do_add_private_ipv4(vnic_utils, vnic, add_options.ip_address)
    elif add_options.ipv == 6:
        priv_ip, ip_ocid = do_add_private_ipv6(vnic_utils, vnic, add_options.ip_address)
    else:
        raise Exception('Invalid ip version: %d' % add_options.ipv)

    return priv_ip, ip_ocid


def do_add_private_ipv4(vnic_utils, vnic, ip_address):
    """
    Add an ipv4 address to a vnic.

    Parameters
    ----------
    vnic_utils: VNICUtils
        The VNICUtils helper instance.
    vnic: OCIVNIC
        The vnic data.
    ip_address: str
        The ipaddress to add.

    Returns
    -------
        tuple: (ipv6, ocid)
    """
    _logger.debug('%s', where_am_i())
    try:
        priv_ipv4 = vnic.add_private_ipv4(private_ip=ip_address)
    except Exception as e:
        _logger.debug('Failed to provision private IPv4: %s ', str(e))
        raise Exception('%s ' % str(e)) from e

    _logger.info('Provisioning secondary private IPv4: %s', priv_ipv4.get_address())
    vnic_utils.add_private_ip(priv_ipv4.get_address(), vnic.get_ocid())
    return priv_ipv4.get_address(), vnic.get_ocid()


def do_add_private_ipv6(vnic_utils, vnic, ip_address):
    """
    Add an ipv6 address to a vnic.

    Parameters
    ----------
    vnic_utils: VNICUtils
        The VNICUtils helper instance.
    vnic: OCIVNIC
        The vnic data.
    ip_address: str
        The ipaddress to add.

    Returns
    -------
        tuple: (ipv6, ocid)
    """
    _logger.debug('%s', where_am_i())
    try:
        priv_ipv6 = vnic.add_private_ipv6(private_ipv6=ip_address)
    except Exception as e:
        _logger.debug('Failed to provision private IPv6: %s ', str(e))
        raise Exception('%s ' % str(e)) from e

    _logger.info('Provisioning secondary private IPv6: %s', priv_ipv6.get_address())
    vnic_utils.add_private_ip(priv_ipv6.get_address(), vnic.get_ocid())
    return priv_ipv6.get_address(), vnic.get_ocid()


def add_secondary_address(args):
    """
    Add a secondary address to a vnic.

    Parameters
    ----------
    args: namespace
        The command line.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    args.ipv = get_ipv_version(args)
    if args.ip_address:
        if is_valid_ip_address(args.ip_address):
            args.ipv = ipv_version(args.ip_address)
        else:
            _logger.error('Invalid IP address provided: %s', args.ip_address)
            return False
    vnic_utils = get_vnic_utils(args)
    try:
        ip, vnic_id = do_add_secondary_addr(vnic_utils, args)
        _logger.info("IP %s has been assigned to vnic %s.", ip, vnic_id)
    except Exception as e:
        _logger.debug('%s', str(e), stack_info=True)
        _logger.error('%s', str(e))
        return False
    return True


def do_remove_secondary_addr(vnic_utils, delete_options):
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
    _logger.debug('%s', where_am_i())
    ip_addr = delete_options.ip_address
    #
    # ipv4 or ipv6; valid ip address is verified by the ip_address_validator.
    # ip_version = ipv_version(ip_addr)
    #
    # needs the OCI SDK installed and configured
    sess = get_oci_api_session()
    if sess is None:
        raise Exception("Failed to get API session.")
    #
    # find the private IP
    priv_ip = sess.this_instance().find_private_ip(ip_addr)
    if priv_ip is None:
        raise Exception("Secondary private IP not found: %s" % ip_addr)
    #
    # cannot delete primary ip from a vnic
    if priv_ip.is_primary():
        raise Exception("Cannot delete IP %s, it is the primary private address of the VNIC." % ip_addr)
    #
    # get the vnic ocid
    vnic_id = priv_ip.get_vnic_ocid()
    #
    # delete the private ip from the vnic in OCI
    if not priv_ip.delete():
        raise Exception('Failed to delete secondary private IP %s' % ip_addr)
    #
    # cleanup on instance
    _logger.info('Deconfigure secondary private IP %s', ip_addr)
    # delete from vnic_info and de-configure the interface
    return vnic_utils.del_private_ip(ip_addr, vnic_id)


def remove_secondary_address(args):
    """
    Remove a secondary address from a vnic.

    Parameters
    ----------
    args: namespace
        The command line.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    vnic_utils = get_vnic_utils(args)
    try:
        (ret, out) = do_remove_secondary_addr(vnic_utils, args)
        if ret != 0:
            raise Exception('Cannot delete ip: %s' % out)
    except Exception as e:
        _logger.debug('Failed to delete private IP: %s', str(e), stack_info=True)
        # _logger.error('Failed to delete private IP: %s', str(e))
        _logger.error('%s', str(e))
        return False
    return True


def configure(args):
    """
    Parameters
    ----------
    args: namespace
        The command line.

    Returns
    -------
    Configure vnics.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    vnic_utils = get_vnic_utils(args)

    if 'namespace' in args and args.namespace:
        try:
            vnic_utils.set_namespace(args.namespace)
        except Exception as e:
            _logger.debug('Failed to set namespace: %s', str(e), stack_info=True)
            _logger.error('Failed to set namespace: %s', str(e))
            return False

    if 'start_sshd' in args and args.start_sshd:
        try:
            vnic_utils.set_sshd(args.start_sshd)
        except Exception as e:
            _logger.debug('Failed to start sshd: %s', str(e), stack_info=True)
            _logger.error('Failed to start sshd: %s', str(e))
            return False

    try:
        vnic_utils.auto_config(args.sec_ip)
        _logger.info('Configured ')
    except Exception as e:
        _logger.debug('Failed to configure network: %s', str(e), stack_info=True)
        _logger.error('Failed to configure network: %s', str(e))
        return False
    return True


def unconfigure(args):
    """
    Unconfigure vnics..

    Parameters
    ----------
    args: namespace
        The command line.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    vnic_utils = get_vnic_utils(args)
    try:
        vnic_utils.auto_deconfig(args.sec_ip)
        _logger.info('Unconfigured ')
    except Exception as e:
        _logger.debug('Failed to unconfigure network: %s', str(e), stack_info=True)
        _logger.error('Failed to unconfigure network: %s', str(e))
    return True


def main():
    """
    Main

    Returns
    -------
        int
            0 on success;
            1 on failure.
    """
    sub_commands = {'usage': show_usage,
                    'show': show_network,
                    'show-vnics': show_vnics,
                    'show-vnics-all': show_vnics_all,
                    'show-vcns': show_vcns,
                    'show-subnets': show_subnets,
                    'attach-vnic': attach_vnic,
                    'detach-vnic': detach_vnic,
                    'add-secondary-addr': add_secondary_address,
                    'remove-secondary-addr': remove_secondary_address,
                    'configure': configure,
                    'unconfigure': unconfigure
                    }

    parser = get_arg_parser()
    args = parser.parse_args()

    if args.quiet:
        _logger.setLevel(logging.WARNING)

    if args.command is None or args.command == 'usage':
        parser.print_help()
        return 0
    #
    # operator needs to have root priviliges.
    if not is_root_user():
        _logger.error("This program needs to be run with root privileges.")
        return 1

    try:
        res = sub_commands[args.command](args)
        if not res:
            raise NetworkConfigException('Failed to complete %s.' % sub_commands[args.command].__name__)
        return 0
    except Exception as e:
        _logger.error('*** ERROR *** %s', str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
