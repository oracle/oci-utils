#
# Copyright (c) 2017, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Script for collecting the cloud network, its subnets, and ip allocation details.
It need oci-sdk installed.
"""

import argparse
import logging
import sys

from oci_utils import oci_api
from oci_utils.impl.oci_resources import OCISecurityList

_logger = logging.getLogger("oci-utils.oci-network-inspector")


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
                                                 'network.')
    parser.add_argument('-C', '--compartment',
                        metavar='OCID',
                        action='store',
                        help='ocid of a compartment you like to explore ')
    parser.add_argument('-N', '--vcn',
                        metavar='OCID',
                        action='store',
                        help='ocid of a given Virtual Cloud Network')

    args = parser.parse_args()
    return args


def _print_security_list(sec_list, indent):
    """
    Print the security list.

    Parameters
    ----------
    indent: str
        The indentation string.

    Returns
    -------
        No return value.
    """
    print("%sSecurity List: %s" % (indent, sec_list.get_display_name()))
    for rule in sec_list.get_ingress_rules():
        prot = OCISecurityList.protocol.get(rule.protocol, rule.protocol)
        src = rule.source
        des = "---"
        desport = "-"
        srcport = "-"
        _logger.debug('rule protocol: %s', rule.protocol)
        if rule.protocol == "6" or rule.protocol == "17":
            if rule.protocol == "6":
                option = rule.tcp_options
            else:
                option = rule.udp_options
            if bool(option):
                if bool(option.destination_port_range):
                    try:
                        if option.destination_port_range.min != option.destination_port_range.max:
                            desport = "%s-%s" % (option.destination_port_range.min, option.destination_port_range.max)
                        else:
                            desport = option.destination_port_range.min
                    except Exception as e:
                        _logger.debug('Error during print: %s', str(e), exc_info=True)

                if bool(option.source_port_range):
                    try:
                        if option.source_port_range.min != option.source_port_range.max:
                            srcport = "%s-%s" % (option.source_port_range.min, option.source_port_range.max)
                        else:
                            srcport = option.source_port_range.min
                    except Exception as e:
                        _logger.debug('Error during print: %s', str(e), exc_info=True)

        elif rule.protocol == "1":
            srcport = "-"
            option = rule.icmp_options
            desport = "type--"
            if bool(option):
                try:
                    desport = "type-%s" % option.type
                except Exception as e:
                    _logger.debug('Error during print: %s', str(e), exc_info=True)

                try:
                    des = "code-%s" % option.code
                except Exception as e:
                    des = "code--"
        print("%s  Ingress: %-5s %20s:%-6s %20s:%s" % (indent, prot, src, srcport, des, desport))

    for rule in sec_list.get_egress_rules():
        prot = OCISecurityList.protocol.get(rule.protocol, rule.protocol)
        des = rule.destination
        src = "---"
        desport = "-"
        srcport = "-"
        if rule.protocol == "6" or rule.protocol == "17":
            if rule.protocol == "6":
                option = rule.tcp_options
            else:
                option = rule.udp_options

            if bool(option):
                try:
                    if option.destination_port_range.min != option.destination_port_range.max:
                        desport = "%s-%s" % (option.destination_port_range.min, option.destination_port_range.max)
                    else:
                        desport = option.destination_port_range.min
                except Exception:
                    desport = "-"

                try:
                    if option.source_port_range.min != option.source_port_range.max:
                        srcport = "%s-%s" % (option.source_port_range.min, option.source_port_range.max)
                    else:
                        srcport = option.source_port_range.min

                except Exception:
                    srcport = "-"
        elif rule.protocol == "1":
            srcport = "-"
            option = rule.icmp_options
            if bool(option):
                try:
                    desport = "type-%s" % option.type
                except Exception:
                    desport = "type--"
                try:
                    des = "code-%s" % option.code
                except Exception:
                    des = "code--"
        print("%s  Egress : %-5s %20s:%-6s %20s:%s" % (indent, prot, src, srcport, des, desport))


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
    except Exception as e:
        _logger.error("Need OCI Service to inspect the networks.\n"
                      "Make sure to install and configure OCI Python SDK (python36-oci-sdk)\n %s", str(e))
        return 1

    comps = []
    if args.compartment:
        comp = sess.get_compartment(ocid=args.compartment)
        if comp is None:
            _logger.error("Compartment [%s] not found\n", args.compartment)
            return 1
        comps.append(comp)
    else:
        comp = sess.all_compartments()
        _logger.debug('no compartment specified, requesting all, got (%d)', len(comp))
        comps.extend(comp)

    if len(comps) == 0:
        _logger.error("No Compartment found\n")
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
            _logger.error("VCN not found: %s\n", args.vcn)
            return 1
    else:
        # get all vcns for the compartment.
        for comp in comps:
            comp_vcns = comp.all_vcns()
            if _logger.isEnabledFor(logging.DEBUG):
                _logger.debug('Requesting VCNs of [%s], got (%d)', comp.get_display_name(), len(comp_vcns))
            for vcn in comp_vcns:
                vcn.set_compartment_name(comp.get_display_name())
            vcns += comp_vcns

    if len(vcns) == 0:
        if args.vcn is not None:
            _logger.error("VCN not found: %s\n", args.vcn)
        else:
            _logger.error("No VCN information found")
        return 1

    comp_ocid = None
    for vcn in vcns:
        _compartment = vcn.get_compartment()
        if _compartment is None:
            #
            _logger.error("No compartment returned for VCN %s\n", str(vcn))
            continue
        if _compartment.get_ocid() != comp_ocid:
            print("")
            print("Compartment: %s (%s)" % (_compartment.get_display_name(), _compartment.get_ocid()))
            comp_ocid = _compartment.get_ocid()
        print("")
        print("  vcn: %s (%s)" % (vcn.get_display_name(), vcn.get_ocid()))
        sll = vcn.all_security_lists()
        for _, value in list(sll.items()):
            _print_security_list(value, "    ")

        for subnet in vcn.all_subnets():
            print("")
            print("     Subnet: %s (%s)" % (subnet.get_display_name(), subnet.get_ocid()))
            print("                Availibility domain: %s" % subnet.get_availability_domain_name())
            print("                Cidr_block: %s" % subnet.get_cidr_block())
            print("                DNS Domain Name: %s" % subnet.get_domain_name())

            for sl_id in subnet.get_security_list_ids():
                try:
                    _print_security_list(sll.get(sl_id), "       ")
                except Exception as e:
                    _logger.error("The security list %s is not in the VCN's list. \nException:%s", sl_id, e)

            # '''
            # vnics = subnet.all_vnics()
            # for vnic in vnics:
            #     primary = "sec"
            #     if vnic.is_primary():
            #         primary = "primary"
            #     print "      Vnic: %s(%s)(%s)" % (vnic.data.display_name,
            #         primary, vnic.get_ocid())
            #     if subnet.data.prohibit_public_ip_on_vnic == False:
            #         print "        Public IP: %s" % vnic.get_public_ip()
            #     print "        Private IP: %s (primary)" % vnic.get_private_ip()
            #     for ip in vnic.all_private_ips():
            #         print "        Private IP: %s" % ip
            # '''
            for ip in subnet.all_private_ips():
                primary = ""
                if ip.is_primary():
                    primary = "primary"
                print("       Private IP: %s(%s) Host: %s" % (ip.get_address(), primary, ip.get_hostname()))
                try:
                    vnic = ip.get_vnic()
                    if vnic:
                        print("         Vnic: %s (%s)" % (vnic.get_ocid(), vnic.get_state()))
                        if subnet.is_public_ip_on_vnic_allowed():
                            print("         Vnic PublicIP: %s" % vnic.get_public_ip())
                        instance = vnic.get_instance()
                        print("         Instance: %s" % instance.get_hostname())
                        print("   Instance State: %s" % instance.get_state())
                        print("         Instance ocid: %s" % (instance.get_ocid()))
                    else:
                        vnic_id = ip.get_vnic_ocid()
                        print("         Vnic: %s(%s)" % (vnic_id, "NotFound"))
                        print("         Instance: (maybe)%s(%s)" % (ip.get_display_name(), "NotFound"))
                except Exception as e:
                    _logger.error('%s.', str(e))
                    _logger.debug('Failed to collect data on vnic: %s', str(e), stack_info=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
