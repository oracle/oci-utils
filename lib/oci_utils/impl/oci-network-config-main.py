#
# Copyright (c) 2017, 2019 Oracle and/or its affiliates. All rights reserved.
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
from oci_utils.exceptions import OCISDKError
from oci_utils.vnicutils import VNICUtils

_logger = logging.getLogger("oci-utils.oci-network-config")

def uniq_item_validator(value):
    """
    validate unicity
    """
    already_seen = getattr(uniq_item_validator,"_item_seen",[])

    if value in already_seen:
        raise argparse.ArgumentTypeError("Invalid arguments: item both included and excluded: %s" % value)
    already_seen.append(value)
    getattr(uniq_item_validator,"_item_seen",already_seen)

    return value

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
    configure_parser.add_argument('-s', '--show', action='store_true',
                        help='After operation completed, show information on all provisioning and interface configuration.')

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
    deconfigure_parser.add_argument('-s', '--show', action='store_true',
                        help='After operation completed, show information on all provisioning and interface configuration.')
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
    attach_vnic.add_argument('-s', '--show', action='store_true',
                        help='After operation completed, show information on all provisioning and interface configuration.')

    detach_vnic = subparser.add_parser('detach-vnic',description='Detach and delete the VNIC with the given OCID'
                             ' or primary IP address')
    dg = detach_vnic.add_mutually_exclusive_group(required=True)
    dg.add_argument('--ocid', action='store', metavar='OCID',
                        help='detach the vNIC with the given VNIC')
    dg.add_argument('-I','--ip-address', action='store', metavar='IP_ADDR',
                        help='detach the vNIC with the given ip address configured on it')
    detach_vnic.add_argument('-s', '--show', action='store_true',
                        help='After operation completed, show information on all provisioning and interface configuration.')

    add_sec_addr = subparser.add_parser('add-secondary-addr',description="Adds the given secondary private IP.")
    add_sec_addr.add_argument('-I','--ip-address', action='store', metavar='IP_ADDR',
                        help='Secondary private IP to to be added',required=True)
    add_sec_addr.add_argument('--ocid', action='store', metavar='OCID',
                        help='Uses vNIC with the given VNIC',required=True)
    add_sec_addr.add_argument('-s', '--show', action='store_true',
                        help='After operation completed, show information on all provisioning and interface configuration.')

    rem_sec_addr = subparser.add_parser('remove-secondary-addr',description="Removes the given secondary private IP.")
    rem_sec_addr.add_argument('-I','--ip-address', action='store', metavar='IP_ADDR',
                        help='Secondary private IP to to be removed',required=True)
    rem_sec_addr.add_argument('-s', '--show', action='store_true',
                        help='After operation completed, show information on all provisioning and interface configuration.')
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
        sess = oci_utils.oci_api.OCISession()
        # it seems that having a client is not enough, we may not be able to query anything on it
        # workaround :
        # try a dummy call to be sure that we can use this session
        sess.this_instance()
        setattr(uniq_item_validator, "_session", sess)
    except Exception as e:
        _logger.error("Failed to access OCI services: %s" % str(e))

    return sess


def oci_show_network_config():
    """
    Show the current network configuration of the instance based on
    information obtained through OCI API calls, if the OCI SDK is
    configured.

    Returns
    -------
       No return value.
    """

    sess = get_oci_api_session()
    if sess is None:
        _logger.error("Failed to get API session.")
        return
    inst = sess.this_instance()
    if inst is None:
        _logger.error("Failed to get information from OCI.")
        return
    vnics = inst.all_vnics()
    i = 1
    print("VNIC configuration for instance %s" % inst.get_display_name())
    print()
    for vnic in vnics:
        primary = ""
        if vnic.is_primary():
            primary = " (primary)"
        print("VNIC %d%s: %s" % (i, primary, vnic.get_display_name()))
        print("     Hostname: %s" % vnic.get_hostname())
        print("     OCID: %s" % vnic.get_ocid())
        print("     MAC address: %s" % vnic.get_mac_address())
        print("     Public IP address: %s" % vnic.get_public_ip())
        print("     Private IP address: %s" % vnic.get_private_ip())

        _subn = vnic.get_subnet()
        if _subn is not None:
            print("     Subnet: %s (%s)" % (_subn.get_display_name(), _subn))
        else:
            print("     Subnet: Not found")

        privips = vnic.all_private_ips()
        if len(privips) > 0:
            print("     Private IP addresses:")
            for privip in privips:
                print("         IP address: %s" % privip.get_address())
                print("         OCID: %s" % privip.get_ocid())
                print("         Hostname: %s" % privip.get_hostname())
                print("         Subnet: %s (%s)" %
                      (privip.get_subnet().get_display_name(),
                       privip.get_subnet().get_cidr_block()))
                print()
        else:
            print()
        i += 1


def system_show_network_config(vnic_utils):
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

    _logger.info("Operating System level network configuration")

    ret = vnic_utils.get_network_config()

    _fmt = "{:6} {:15} {:15} {:5} {:15} {:10} {:3} {:15} {:5} {:11} {:5} {:17} {}"
    print(_fmt.format('CONFIG', 'ADDR', 'SPREFIX', 'SBITS', 'VIRTRT',
                      'NS', 'IND', 'IFACE', 'VLTAG', 'VLAN', 'STATE', 'MAC', 'VNIC'))
    for item in ret:
        print(_fmt.format(item['CONFSTATE'],
                          item['ADDR'], item['SPREFIX'],
                          item['SBITS'], item['VIRTRT'],
                          item['NS'], item['IND'],
                          item['IFACE'], item['VLTAG'],
                          item['VLAN'], item['STATE'],
                          item['MAC'], item['VNIC']))


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
    except OCISDKError as e:
        raise Exception('Failed to create VNIC: %s' % str(e)) from e

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
        priv_ip = vnic.add_private_ip(private_ip=add_options.ip_address)
    except OCISDKError as e:
        raise Exception('Failed to provision private IP: %s' % str(e)) from e

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
        system_show_network_config(vnic_utils)
        oci_show_network_config()
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
            time.sleep(10)
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

    if 'show' in args and args.show:
        system_show_network_config(vnic_utils)
        oci_show_network_config()

    return 0


if __name__ == "__main__":
    sys.exit(main())
