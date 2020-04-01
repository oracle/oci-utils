#
# Copyright (c) 2017, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Script for collecting the cloud network, its subnets, and ip allocation details.
It need oci-sdk installed.
"""

import argparse
import logging
import sys

try:
    import json
except ImportError:
    import simplejson as json
from oci_utils import oci_api
# import oci_utils.oci_api
from oci_utils.exceptions import OCISDKError

__logger = logging.getLogger("oci-utils.oci-network-inspector")


def parse_args():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args()).

    Returns
    -------
        The argparse namespace.
    """
    parser = argparse.ArgumentParser(description='Utility for exploring '
                                                 'the network, its subnets '
                                                 'and ips assigned for a '
                                                 'given compartment or '
                                                 'network.', add_help=False)
    parser.add_argument('-C', '--compartment',
                        metavar='OCID',
                        action='store',
                        help='ocid of a compartment you like to explore ')
    parser.add_argument('-N', '--vcn',
                        metavar='OCID',
                        action='store',
                        help='ocid of a given Virtual Cloud Network')
    parser.add_argument('--help',
                        action='help',
                        help='Display this help')

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

    # needs the OCI SDK installed and configured
    try:
        sess = oci_api.OCISession()
        # sess = oci_utils.oci_api.OCISession()
    except OCISDKError as e:
        __logger.error("Need OCI Service to inspect the networks.\n"
                       "Make sure to install and configure "
                       "OCI Python SDK (python-oci-sdk)\n %s" % str(e))
        return 1

    comps = []
    if args.compartment:
        comp = sess.get_compartment(ocid=args.compartment)
        if comp is None:
            __logger.error("Compartment [%s] not found\n" % args.compartment)
            return 1
        comps.append(comp)
    else:
        comp = sess.all_compartments()
        comps.extend(comp)

    if len(comps) == 0:
        __logger.error("No Compartment found\n")
        return 1

    vcns = []
    if args.vcn:
        if args.vcn.startswith('ocid1.vcn.oc1.'):
            vcn = sess.get_vcn(args.vcn)
            if vcn is not None:
                vcns.append(vcn)
        else:
            vcn = sess.find_vcns(args.vcn)
            if vcn is not None:
                vcns.extend(vcn)
        if len(vcns) == 0:
            __logger.error("VCN not found: %s\n" % args.vcn)
            return 1
    else:
        # get all vcns for the compartment.
        for comp in comps:
            comp_vcns = comp.all_vcns()
            for vcn in comp_vcns:
                vcn.set_compartment_name(comp.get_display_name())
            vcns += comp_vcns

    if len(vcns) == 0:
        __logger.error("VCN not found: %s\n" % args.vcn)
        return 1

    comp_ocid = None
    for vcn in vcns:
        _compartment = vcn.get_compartment()
        if _compartment is None:
            __logger.error("no compartment returned for VCN %s\n" % str(vcn))
            continue
        if _compartment.get_ocid() != comp_ocid:
            print("")
            print("Compartment: %s (%s)" % \
                  (_compartment.get_display_name(), _compartment.get_ocid()))
            comp_ocid = _compartment.get_ocid()
        print("")
        print("  vcn: %s " % vcn.get_display_name())
        sll = vcn.all_security_lists()
        for _, value in list(sll.items()):
            value.print_security_list("    ")

        for subnet in vcn.all_subnets():
            print("")
            print("     Subnet: %s Availibility domain: %s" % (
                subnet.get_display_name(), subnet.get_availability_domain()))
            print("         Cidr_block: %s Domain name: %s" % \
                  (subnet.get_cidr_block(), subnet.get_domain_name()))

            for sl_id in subnet.get_security_list_ids():
                try:
                    sll.get(sl_id).print_security_list("       ")
                except Exception as e:
                    __logger.error("The security list %s is not in the VCN's "
                                   "list. \nException:%s" % (sl_id, e))

            '''
            vnics = subnet.all_vnics()
            for vnic in vnics:
                primary = "sec"
                if vnic.is_primary():
                    primary = "primary"
                print "      Vnic: %s(%s)(%s)" % (vnic.data.display_name,
                    primary, vnic.get_ocid())
                if subnet.data.prohibit_public_ip_on_vnic == False:
                    print "        Public IP: %s" % vnic.get_public_ip()
                print "        Private IP: %s (primary)" % vnic.get_private_ip()
                for ip in vnic.all_private_ips():
                    print "        Private IP: %s" % ip
            '''
            for ip in subnet.all_private_ips_with_primary():
                primary = ""
                if ip.is_primary():
                    primary = "primary"
                print("       Private IP: %s(%s) Host: %s" % \
                      (ip.get_address(), primary, ip.get_hostname()))
                vnic = ip.get_vnic()
                if vnic:
                    print("         Vnic: %s (%s)" % \
                          (vnic.get_ocid(), vnic.get_state()))
                    if subnet.is_public_ip_on_vnic_allowed():
                        print("         Vnic PublicIP: %s" % \
                              vnic.get_public_ip())
                    instance = vnic.get_instance()
                    print("         Instance: %s(%s)" % \
                          (instance.get_hostname(), instance.get_state()))
                    print("         Instance ocid: %s" % (instance.get_ocid()))
                else:
                    vnic_id = ip.get_vnic_ocid()
                    print("         Vnic: %s(%s)" % (vnic_id, "NotFound"))
                    print("         Instance: (maybe)%s(%s)" % \
                          (ip.get_display_name(), "NotFound"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
