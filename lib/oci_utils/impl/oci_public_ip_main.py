#
# Copyright (c) 2017, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Script for printing the public IP address of a system.
Uses STUN (https://www.voip-info.org/wiki-STUN), implemented in
pystun.
"""

import argparse
import logging
import sys

from oci_utils.packages.stun import get_ip_info, STUN_SERVERS
from oci_utils import oci_api

from oci_utils.impl.row_printer import get_row_printer_impl

stun_log = logging.getLogger("oci-utils.oci-public-ip")


def parse_args():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args())

    Returns
    -------
        The command line namespace
    """
    parser = argparse.ArgumentParser(prog='oci-public-ip',
                                     description='Utility for displaying the public IP address of the '
                                                 'current OCI instance.',
                                     add_help=False)
    group = parser.add_mutually_exclusive_group()

    # deprecated option
    parser.add_argument('-h', '--human-readable',
                        action='store_true',
                        help=argparse.SUPPRESS)
    # deprecated option
    parser.add_argument('-j', '--json',
                        action='store_true',
                        help=argparse.SUPPRESS)
    # deprecated option
    parser.add_argument('-g', '--get',
                        action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('--output-mode',
                        choices=('parsable', 'table', 'json', 'text'),
                        help='Set output mode',
                        default='table')
    parser.add_argument('-d', '--details',
                        action='store_true',
                        help="display details information")
    parser.add_argument('-a', '--all',
                        action='store_true',
                        # help='list all the public IP addresses for the instance.')
                        help=argparse.SUPPRESS)
    parser.add_argument('-s', '--sourceip',
                        action='store',
                        default="0.0.0.0",
                        help='Specify the source IP address to use')
    group.add_argument('-S', '--stun-server',
                       action='store',
                       help='Specify the STUN server to use')
    parser.add_argument('-L', '--list-servers',
                        action='store_true',
                        help='Print a list of known STUN servers and exit')
    group.add_argument('--instance-id',
                       metavar='OCID',
                       action='store',
                       help='Display the public IP address of the given '
                       'instance instead of the current one.  Requires '
                       'the OCI Python SDK to be installed and '
                       'configured')
    parser.add_argument('--help',
                        action='help',
                        help='Display this help')
    args = parser.parse_args()
    return args


def _display_ip_list(ip_list, displayALL, outputMode, displayDetails):
    """
    Receive a list of IPs and display them
    arguments:
      ip_list : list of IPs as string
      displayALL : display all or only the one on the primary vNIC
      outputMode : output mode (table, text, etc..)
      displayDetails : display detailed information ?
    """

    _sorted_list_of_pubips = sorted(ip_list, key=lambda ip: ip['primary'], reverse=True)
    if displayALL:
        _ip_list_to_display = ip_list
    else:
        _ip_list_to_display = ip_list[:1]

    _collen = {'ipaddress': len('IP Address'),
               'vnicname': len('vNIC name'),
               'vnicprivate': len('vNIC private IP'),
               'vnicmac': len('vNIC mac address'),
               'vnicprimary': 7,
               'vnicocid': len('vNIC OCID')}

    for _ip in _ip_list_to_display:
        # ip
        _ip_len = len(_ip['ip'])
        _collen['ipaddress'] = max(_ip_len, _collen['ipaddress'])
        # vnic name
        _vnicname_len = len(_ip['vnic_name'])
        _collen['vnicname'] = max(_vnicname_len, _collen['vnicname'])
        # private ip 
        _vnicprivate_len = len(_ip['vnic_private_ip'])
        _collen['vnicprivate'] = max(_vnicprivate_len, _collen['vnicprivate'])
        # vnic mac address
        _vnicmac_len = len(_ip['vnic_mac_address'])
        _collen['vnicmac'] = max(_vnicmac_len, _collen['vnicmac'])
        # vnic ocid
        _vnicocid_len = len(_ip['vnic_ocid'])
        _collen['vnicocid'] = max(_vnicocid_len, _collen['vnicocid'])

    _title = 'Public IPs information (primary on top):'

    _columns = [['IP Address', _collen['ipaddress']+2, 'ip']]
    if displayDetails:
        _columns.append(['vNIC name', _collen['vnicname']+2, 'vnic_name'])
        _columns.append(['vNIC private ip', _collen['vnicprivate']+2, 'vnic_private_ip'])
        _columns.append(['vNIC mac address', _collen['vnicmac']+2, 'vnicmac'])
        _columns.append(['primary', _collen['vnicprimary']+2, 'primary'])
        _columns.append(['vNIC OCID', _collen['vnicocid']+2, 'vnic_ocid'])

    printerKlass = get_row_printer_impl(outputMode)

    _printer = printerKlass(title=_title, columns=_columns)
    _printer.printHeader()
    # _sorted_list_of_pubips = sorted(_ip_list_to_display, key=lambda ip: ip['primary'], reverse=True)
    for _ip in _sorted_list_of_pubips:
        _printer.printRow(_ip)
    _printer.printFooter()
    _printer.finish()
    return 0


def main():
    """
    Main

    Returns
    -------
        int
            0 on success, 1 otherwise.
    """
    args = parse_args()

    # deal with deprecated options
    if args.human_readable:
        args.output_mode = 'table'
    if args.get:
        args.output_mode = 'parsable'
    if args.json:
        args.output_mode = 'json'

    if args.list_servers:
        #
        # print the list of known STUN servers and exit
        for server in STUN_SERVERS:
            print(server)
        return 0
    #
    # Try to create a functional oci session
    _instance = None
    try:
        sess = oci_api.OCISession()
        if args.instance_id is not None:
            _instance = sess.get_instance(args.instance_id)
        else:
            _instance = sess.this_instance()
    except Exception as e:
        if args.instance_id is not None:
            # user specified a remote instance, there is no fallback to stun
            # we treat this as an error now
            stun_log.error("Error getting information of instance [%s]: %s", args.instance_id, str(e))
            return 1
        # in that case, just issue a debug info
        stun_log.debug("Error getting information of current instance: %s", str(e))

    _all_p_ips = []
    #
    # successfully creating a session and getting the instance data is not enough to collect vnic data.
    if _instance is not None:
        z = _instance.all_vnics()
        try:
            _all_p_ips = [{'ip': v.get_public_ip(),
                           'vnic_name': v.get_display_name(),
                           'vnic_private_ip': v.get_private_ip(),
                           'vnic_mac_address': v.get_mac_address(),
                           'primary': v.is_primary(),
                           'vnic_ocid': v.get_ocid()} for v in _instance.all_vnics() if v.get_public_ip()]
            stun_log.debug('%s ips retrieved from sdk information', len(_all_p_ips))
            if len(_all_p_ips) == 0:
                # stun_log.info('No public ip addresses found from OCI, falling back to the stun servers.')
                _instance = None
        except Exception as e:
            stun_log.info('Instance is missing privileges to collect ip data from OCI, '
                          'falling back to the stun servers.')
            _instance = None

    if _instance is None:
        stun_log.info('No public ip addresses found from OCI, falling back to the stun servers.')
        stun_log.info('The stun servers do not provide details on the vNIC and '
                      'might find only the primary IP address.\n')
        #
        # stun servers just give the ip address
        args.details = False
        if args.instance_id is not None:
            # user specified a remote instance, there is no fallback to stun
            stun_log.error("Instance not found: %s", args.instance_id)
            return 1
        # can we really end up here ?
        stun_log.debug("Current Instance not found")
        # fall back to pystun
        stun_log.debug('No ip found , fallback to STUN')
        _ip = get_ip_info(source_ip=args.sourceip, stun_host=args.stun_server)[1]
        stun_log.debug('STUN gave us : %s', _ip)
        if _ip:
            _all_p_ips.append({'ip': _ip,
                               'vnic_name': '',
                               'primary': True,
                               'vnic_private_ip': '',
                               'vnic_mac_address': '',
                               'vnic_ocid': ''})
        else:
            stun_log.info('No public IP addresses found via the stun servers.')

    if len(_all_p_ips) == 0:
        # none of the methods give us information
        stun_log.info("No public IP address found.\n")
        return 1

    if args.get:
        #
        # for compatibility mode, the parsable output mode is not really appropriate
        # LINUX-11255
        for ip in _all_p_ips:
            print('%16s' % ip['ip'])
    else:
        # _display_ip_list(_all_p_ips, args.all, args.output_mode, args.details)
        _display_ip_list(_all_p_ips, True, args.output_mode, args.details)

    return 0


if __name__ == "__main__":
    sys.exit(main())
