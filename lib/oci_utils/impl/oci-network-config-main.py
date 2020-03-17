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
import oci_utils.oci_api
from oci_utils.exceptions import OCISDKError
from oci_utils.vnicutils import VNICUtils

__logger = logging.getLogger("oci-utils.oci-network-config")


def parse_args():
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
    parser.add_argument('-s', '--show', action='store_true',
                        help='Show information on all provisioning and '
                             'interface configuration. This is the default '
                             'action if no options are given.')
    parser.add_argument('--create-vnic', action='store_true',
                        help='Create a new VNIC and attach it to '
                             'this instance')
    parser.add_argument('--nic-index', action='store', metavar='INDEX',
                        type=int, default=0,
                        help='physical NIC card index. When used with '
                             'the --create-vnic option, assign the new VNIC '
                             'to the specified physical NIC card.')
    parser.add_argument('--detach-vnic', action='store', metavar='VNIC',
                        help='Detach and delete the VNIC with the given OCID'
                             ' or primary IP address')
    parser.add_argument('--add-private-ip', action='store_true',
                        help='Add a secondary private IP to an existing VNIC')
    parser.add_argument('--del-private-ip', action='store', metavar='ADDR',
                        help='delete the secondary private IP address with '
                             'the given IP address')
    parser.add_argument('--private-ip', action='store', metavar='ADDR',
                        help='When used with the --create-vnic or '
                             'add-private-ip options, '
                             'assign the given private IP address to the VNIC')
    parser.add_argument('--subnet', action='store',
                        help='When used with the --create-vnic option, '
                             'connect the new VNIC to the given subnet.')
    parser.add_argument('--vnic-name', action='store', metavar='NAME',
                        help='When used with the --create-vnic option, '
                             'use NAME as the display name of the new VNIC')
    parser.add_argument('--assign-public-ip', action='store_true',
                        help='When used with the --create-vnic option, '
                             'assign a public IP address to the new VNIC.')
    parser.add_argument('--vnic', action='store', metavar='OCID',
                        help='When used with the --add-private-ip option, '
                             'assign the private IP to the given VNIC')
    parser.add_argument('-a', '--auto', '-c', '--configure',
                        action='store_true',
                        help='Add IP configuration for VNICs that are not '
                             'configured and delete for VNICs that are no '
                             'longer provisioned.')
    parser.add_argument('-d', '--deconfigure', action='store_true',
                        help='Deconfigure all VNICs (except the primary). If '
                             'a -e option is also present only the secondary '
                             'IP address(es) are deconfigured.')
    parser.add_argument('-e', nargs=2, metavar=('IP_ADDR', 'VNIC_OCID'),
                        dest='sec_ip', action='append',
                        help='Secondary private IP address to configure or '
                             'deconfigure.  Use in conjunction with -c or -d.')
    parser.add_argument('-n', '--ns', action='store', metavar='FORMAT',
                        help='When configuring, place interfaces in namespace '
                             'identified by the given format. Format can '
                             'include $nic and $vltag variables.')
    parser.add_argument('-r', '--sshd', action='store_true',
                        help='Start sshd in namespace (if -n is present)')
    parser.add_argument('-X', '--exclude', metavar='ITEM', action='append',
                        type=str, dest='exclude',
                        help='Persistently exclude ITEM from automatic '
                             'configuration/deconfiguration.  Use the '
                             '--include option to include the ITEM again.')
    parser.add_argument('-I', '--include', metavar='ITEM', action='append',
                        type=str, dest='include',
                        help='Include an ITEM that was previously excluded '
                             'using the --exclude option in automatic '
                             'configuration/deconfiguration.')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Suppress information messages')
    args = parser.parse_args()
    return args


def get_oci_api_session(opt_name=None):
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
    sess = None
    if oci_utils.oci_api.HAVE_OCI_SDK:
        try:
            sess = oci_utils.oci_api.OCISession()
        except Exception as e:
            sdk_error = str(e)
            if opt_name is not None:
                __logger.error("To use the %s option, you need to "
                               "install and configure the OCI Python SDK "
                               "(python-oci-sdk)\n" % opt_name)
                __logger.error(sdk_error)
            else:
                __logger.error("Failed to access OCI services: %s" % sdk_error)

    return sess


def api_show_network_config():
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
        __logger.error("Failed to get API session.")
        return
    inst = sess.this_instance()
    if inst is None:
        __logger.error("Failed to get information from OCI.")
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
                print("         Subnet: %s (%s)" % \
                    (privip.get_subnet().get_display_name(),
                     privip.get_subnet().get_cidr_block()))
                print()
        else:
            print()
        i += 1


def do_show_network_config(vnic_utils):
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
    if oci_utils.oci_api.HAVE_OCI_SDK:
        api_show_network_config()

    __logger.info("Operating System level network configuration")

    (ret, out) = vnic_utils.get_network_config()
    if ret:
        __logger.error("Failed to execute the VNIC configuration script.")
    else:
        print("%s" % out.decode('utf-8'))


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
        StandardError
            if session cannot be acquired
            if the VNIC cannot be detached

    """
    # needs the OCI SDK installed and configured
    sess = get_oci_api_session(opt_name="--detach-vnic")
    if sess is None:
        raise Exception("Failed to get API session.")
    vnics = sess.this_instance().all_vnics()
    for vnic in vnics:
        if vnic.get_ocid() == detach_options.detach_vnic or \
           vnic.get_private_ip() == detach_options.detach_vnic:
            if not vnic.is_primary():
                vnic_utils.delete_all_private_ips(vnic.get_ocid())
                vnic.detach()
                break
            else:
                raise Exception("The primary VNIC cannot be detached.")
    return sess.this_shape()


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
        StandardError
            if session cannot be acquired
    """
    # needs the OCI SDK installed and configured
    sess = get_oci_api_session(opt_name="--create-vnic")
    if sess is None:
        raise Exception("Failed to get API session.")
    subnet_id = None
    if create_options.subnet:
        if create_options.subnet.startswith('ocid1.subnet.'):
            subnet = sess.get_subnet(create_options.subnet)
            if subnet is None:
                raise Exception(
                    "Subnet not found: %s\n" % create_options.subnet)
            else:
                subnet_id = subnet.get_ocid()
        else:
            subnets = sess.find_subnets(create_options.subnet)
            if len(subnets) == 0:
                raise Exception(
                    "No subnet matching %s found\n" % create_options.subnet)
            elif len(subnets) > 1:
                __logger.error("More than one subnet matching %s found:\n"
                               % create_options.subnet)
                for sn in subnets:
                    __logger.error("   %s\n" % sn.get_display_name())
                raise Exception("More than one subnet matching")
            subnet_id = subnets[0].get_ocid()
    try:
        vnic = sess.this_instance().attach_vnic(
            private_ip=create_options.private_ip,
            assign_public_ip=create_options.assign_public_ip,
            subnet_id=subnet_id,
            nic_index=create_options.nic_index,
            display_name=create_options.vnic_name)
    except OCISDKError as e:
        raise Exception('Failed to create VNIC: %s' % e)

    public_ip = vnic.get_public_ip()
    if public_ip is not None:
        __logger.info(
            'creating VNIC: %s (public IP %s)' % (vnic.get_private_ip(),
                                                  public_ip))
    else:
        __logger.info('creating VNIC: %s' % vnic.get_private_ip())


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
        StandardError
            On any error.
    """
    # needs the OCI SDK installed and configured
    sess = get_oci_api_session(opt_name="--add-private-ip")
    if sess is None:
        raise Exception("Failed to get API session.")

    if add_options.vnic:
        if add_options.vnic.startswith('ocid1.vnic.'):
            vnic = sess.get_vnic(add_options.vnic)
            if vnic is None:
                raise Exception("VNIC not found: %s" % add_options.vnic)
            else:
                pass
        else:
            raise Exception("Invalid VNIC OCID: %s" % add_options.vnic)

    else:
        vnics = sess.this_instance().all_vnics()
        if len(vnics) > 1:
            __logger.error("More than one VNIC found."
                           "Use the --vnic option to select the one to add "
                           "a secondary IP for:")
            for vnic in vnics:
                __logger.error("   %s: %s" % (vnic.get_private_ip(),
                                              vnic.get_ocid()))
            raise Exception("Too many VNICs found")
        vnic = vnics[0]
    try:
        priv_ip = vnic.add_private_ip(private_ip=add_options.private_ip)
    except OCISDKError as e:
        raise Exception('Failed to provision private IP: %s' % e)

    __logger.info(
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
    StandardError
        error getting session
    """
    # needs the OCI SDK installed and configured
    sess = get_oci_api_session(opt_name="--del-private-ip")
    if sess is None:
        raise Exception("Failed to get API session.")
    # find the private IP
    priv_ip = sess.this_instance().find_private_ip(
        delete_options.del_private_ip)
    if priv_ip is None:
        raise Exception(
            "Secondary private IP not found: %s" %
            delete_options.del_private_ip)

    if priv_ip.is_primary():
        raise Exception("Cannot delete IP %s, it is the primary private "
                            "address of the VNIC." %
                            delete_options.del_private_ip)
    vnic_id = None
    try:
        vnic_id = priv_ip.get_vnic_ocid()
    except Exception:
        pass

    if not priv_ip.delete():
        raise Exception('failed to delete secondary private IP %s' %
                            delete_options.del_private_ip)

    __logger.info('deconfigure secondary private IP %s' %
                  delete_options.del_private_ip)
    # delete from vnic_info and de-configure the interface
    return vnic_utils.del_private_ip(delete_options.del_private_ip, vnic_id)


def main():
    """
    Main

    Returns
    -------
        int
            0 on success;
            1 on failure.
    """
    args = parse_args()

    if os.geteuid() != 0:
        __logger.error("You must run this program with root privileges")
        return 1

    if args.create_vnic:
        if args.add_private_ip:
            __logger.error(
                "Cannot use --create-vnic and --add-private-ip at the "
                "same time")
            return 1
        try:
            do_create_vnic(args)
        except Exception as e:
            __logger.debug('cannot create the VNIC', exc_info=True)
            __logger.error('cannot create the VNIC: %s' % str(e))
            return 1
    try:
        vnic_utils = VNICUtils()
        vnic_info = vnic_utils.get_vnic_info()[1]
    except Exception as e:
        __logger.warning("OCI SDK Error: %s" % str(e))
        __logger.exception('OCI SDK Error')
        return 1

    shape = None
    if args.detach_vnic:
        try:
            shape = do_detach_vnic(args, vnic_utils)
            time.sleep(10)
        except Exception as e:
            __logger.error(str(e))
            return 1

    if args.ns:
        vnic_utils.set_namespace(args.ns)

    if args.sshd:
        vnic_utils.set_sshd(args.sshd)

    excludes = vnic_info['exclude']
    if excludes is None:
        excludes = []

    ret = 0
    out = ""
    if args.add_private_ip:
        try:
            (ip, vnic_id) = do_add_private_ip(vnic_utils, args)
            __logger.info("IP %s has been assigned to vnic %s." % (ip, vnic_id))
        except Exception as e:
            __logger.error('failed ot add private ip: %s' % str(e))
            return 1

    elif args.del_private_ip:
        try:
            (ret, out) = do_del_private_ip(vnic_utils, args)
        except Exception as e:
            __logger.error('failed ot delete private ip: %s' % str(e))
            return 1

    if args.exclude:
        for exc in args.exclude:
            if args.include and exc in args.include:
                __logger.error(
                    "Invalid arguments: item both included and excluded: %s"
                    % exc)
            vnic_utils.exclude(exc)
        excludes = vnic_info['exclude']
    if args.include:
        for inc in args.include:
            vnic_utils.include(inc)
        excludes = vnic_info['exclude']

    if excludes and not args.quiet:
        if __logger.isEnabledFor(logging.INFO):
            __logger.info(
                "Info: Addresses excluded from automatic configuration: %s" %
                ", ".join(excludes))

    if args.auto or args.create_vnic or args.add_private_ip:
        (ret, out) = vnic_utils.auto_config(quiet=args.quiet, show=args.show,
                                            sec_ip=args.sec_ip)
    elif args.detach_vnic and shape and shape.startswith("BM"):
        (ret, out) = vnic_utils.auto_config(quiet=args.quiet, show=args.show,
                                            sec_ip=args.sec_ip)
    elif args.deconfigure:
        (ret, out) = vnic_utils.auto_deconfig(quiet=args.quiet, show=args.show,
                                              sec_ip=args.sec_ip)

    if ret:
        __logger.error("Failed to execute the VNIC configuration script.")
    if out:
        __logger.debug(str(out))

    if not args.quiet or args.show:
        do_show_network_config(vnic_utils)

    return 0


if __name__ == "__main__":
    sys.exit(main())
