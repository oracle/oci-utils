#
# Copyright (c) 2017, 2019 Oracle and/or its affiliates. All rights reserved.
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

try:
    import json
except ImportError:
    import simplejson as json
from oci_utils.packages.stun import get_ip_info, STUN_SERVERS
from oci_utils import oci_api
from oci_utils.exceptions import OCISDKError

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
    parser.add_argument('-h', '--human-readable', action='store_true',
                        help='Display human readable output (default)')
    parser.add_argument('-j', '--json', action='store_true',
                        help='Display json output')
    parser.add_argument('-g', '--get', action='store_true',
                        help='Print the IP address only')
    parser.add_argument('-a', '--all', action='store_true',
                        help='list all of the public IP addresses for the '
                             'instance.')
    parser.add_argument('-s', '--sourceip', action='store', default="0.0.0.0",
                        help='Specify the source IP address to use'),
    parser.add_argument('-S', '--stun-server', action='store',
                        help='Specify the STUN server to use'),
    parser.add_argument('-L', '--list-servers', action='store_true',
                        help='Print a list of known STUN servers and exit'),
    parser.add_argument('--instance-id', metavar='OCID', action='store',
                        help='Display the public IP address of the given '
                             'instance instead of the current one.  Requires '
                             'the OCI Python SDK to be installed and '
                             'configured')
    parser.add_argument('--help', action='help', help='Display this help')

    args = parser.parse_args()
    return args


def main():
    """
    Main

    Returns
    -------
        int
            0 on success, 1 otherwise.
    """
    args = parse_args()

    if args.list_servers:
        # print the list of known STUN servers and exit
        for server in STUN_SERVERS:
            print(server)
        sys.exit(0)

    external_ip = None
    external_ips = []
    if args.instance_id is None and args.sourceip == '0.0.0.0' and \
       args.stun_server is None:
        try:
            _found = False
            if oci_api.HAVE_OCI_SDK:
                _this_instance = oci_api.OCISession().this_instance()
                _all_p_ips = _this_instance.all_public_ips()
                if len(_all_p_ips) > 0:
                    _found = True
                    external_ips.append(_all_p_ips[0])
            if not _found:
                # fall back to STUN if we did not find any
                _p_ip = get_ip_info(source_ip='0.0.0.0')[1]
                if _p_ip is not None:
                    external_ips.append(_p_ip)
        except Exception as e:
            stun_log.error("%s\n" % e)

    if (external_ip is None or args.all) \
            and (oci_api.HAVE_OCI_SDK or args.instance_id is not None):
        # try the OCI APIs first

        try:
            sess = oci_api.OCISession()
            if args.instance_id is not None:
                inst = sess.get_instance(args.instance_id)
            else:
                inst = sess.this_instance()

            if inst is None:
                stun_log.error(
                    "Instance not found: %s\n" % args.instance_id)
                sys.exit(1)
            for vnic in inst.all_vnics():
                external_ip = vnic.get_public_ip()
                if vnic.is_primary() and external_ip not in external_ips:
                    external_ips.insert(0, external_ip)
                else:
                    if external_ip is None:
                        continue
                    if args.all:
                        if external_ip in external_ips:
                            continue
                        external_ips.append(external_ip)
                    else:
                        break
        except OCISDKError:
            if args.instance_id is not None:
                stun_log.error(
                    "The OCI Python SDK must be installed and configured when "
                    "using the --instance-id option.\n")
                sys.exit(1)

    if external_ip is None or args.all:
        # fall back to pystun
        external_ip = get_ip_info(source_ip=args.sourceip,
                                  stun_host=args.stun_server)[1]

        if args.all and external_ip not in external_ips:
            external_ips.append(external_ip)

    if args.all:
        if args.json:
            print(json.dumps({'publicIps': external_ips}))
        elif args.get:
            print(external_ips)
        else:
            print("Public IP addresses: ")
            print("  Primary public IP: %s " % external_ips[0])
            if len(external_ips) < 2:
                print("  Other public IP(s): None")
                return 0
            print("  Other public IP(s):")
            for ip in external_ips[1:]:
                print("    %s" % ip)
        return 0
    elif external_ip is not None:
        if args.json:
            print(json.dumps({'publicIp': external_ip}))
        elif args.get:
            print(external_ip)
        else:
            print("Public IP address: %s" % external_ip)

        return 0
    else:
        stun_log.info("No public IP address found.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
