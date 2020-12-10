#
# Copyright (c) 2017, 2020 Oracle and/or its affiliates. All rights reserved.
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

import json
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
    parser = argparse.ArgumentParser(
        description='Utility for displaying the public IP address of the '
                    'current OCI instance.', add_help=False)
    group = parser.add_mutually_exclusive_group()

    # deprecated option
    parser.add_argument('-h', '--human-readable', action='store_true',
                        help=argparse.SUPPRESS)
    # deprecated option
    parser.add_argument('-j', '--json', action='store_true',
                        help=argparse.SUPPRESS)
    # deprecated option
    parser.add_argument('-g', '--get', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('--output-mode', choices=('parsable','table','json','text'), help='Set output mode',default='table')
    parser.add_argument('-d', '--details', action='store_true',
                        help="display details information")
    parser.add_argument('-a', '--all', action='store_true',
                        help='list all of the public IP addresses for the '
                             'instance.')
    parser.add_argument('-s', '--sourceip', action='store', default="0.0.0.0",
                        help='Specify the source IP address to use')
    group.add_argument('-S', '--stun-server', action='store',
                       help='Specify the STUN server to use')
    parser.add_argument('-L', '--list-servers', action='store_true',
                        help='Print a list of known STUN servers and exit')
    group.add_argument('--instance-id', metavar='OCID', action='store',
                       help='Display the public IP address of the given '
                       'instance instead of the current one.  Requires '
                       'the OCI Python SDK to be installed and '
                       'configured')
    parser.add_argument('--help', action='help', help='Display this help')
    args = parser.parse_args()
    return args


def _display_ip_list(ip_list, displayALL, outputMode, displayDetails):
    """
    Receive a list of IPs and display them
    arguments:
      ip_list : list of IPs as string
      displayALL : display all or only the one on the primary vNIC
    """
    #we assume that primary is the first one

    if displayALL:
        _ip_list_to_display = ip_list
    else:
        _ip_list_to_display = ip_list[:1]

    _title = 'Public IPs information (primary on top)'
    _columns = [['IP Address',15,'ip']]
    if displayDetails:
        _columns.append(['vNIC name',15,'vnic_name'])
        _columns.append(['vNIC OCID',90,'vnic_ocid'])

    printerKlass = get_row_printer_impl(outputMode)

    _printer = printerKlass(title=_title, columns=_columns)
    _printer.printHeader()
    for _ip in ip_list:
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
        # print the list of known STUN servers and exit
        for server in STUN_SERVERS:
            print(server)
        return 0

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
            stun_log.error(
                "Error getting information of instance [%s]: %s" % (args.instance_id, str(e)))
            return 1
        # in that case, just issue a debug info
        stun_log.debug("Error getting information of current instance: %s", str(e))

    _all_p_ips = []

    if _instance is None:
        if args.instance_id is not None:
            # user specified a remote instance, there is no fallback to stun
            stun_log.error(
                "Instance not found: %s" % args.instance_id)
            return 1
        # can we really end up here ?
        stun_log.debug("current Instance not found")
    else:
        _all_p_ips=[{'ip':v.get_public_ip(),'vnic_name':v.get_display_name(),'vnic_ocid':v.get_ocid()} for v in _instance.all_vnics()]
        stun_log.debug('%s ips retreived from sdk information' % len(_all_p_ips))

    if len(_all_p_ips) == 0:
        # fall back to pystun
        stun_log.debug('No ip found , fallback to STUN')
        _ip = get_ip_info(source_ip=args.sourceip,
                          stun_host=args.stun_server)[1]
        stun_log.debug('STUN gave us : %s' % _ip)
        if _ip:
            _all_p_ips.append({'ip':_ip})

    if len(_all_p_ips) == 0:
        # none of the methods give us information
        stun_log.info("No public IP address found.\n")
        return 1
    _display_ip_list(_all_p_ips, args.all, args.output_mode, args.details)
    return 0


if __name__ == "__main__":
    sys.exit(main())
