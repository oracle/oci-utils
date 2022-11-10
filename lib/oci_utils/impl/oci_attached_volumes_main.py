#
# Copyright (c) 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.
#

import argparse
import json
import logging
import os
import re
import socket
import subprocess
import sys
import urllib

from oci_utils import oci_api
from oci_utils.iscsiadm import discovery

try:
    import oci as oci_sdk
except ImportError as e:
    print('OCI SDK is not installed: %s.' % str(e))
    sys.exit(1)

MAX_VOLUMES = 36
_logger = logging.getLogger('oci-attached_volumes')


def def_usage_parser(s_parser):
    """
    Define the usage parser.

    Parameters
    ----------
    s_parser: subparsers.

    Returns
    -------
        ArgumentParser: the usage subcommand parser.
    """
    usage_parser = s_parser.add_parser('usage',
                                       description='Displays usage',
                                       help='Displays usage'
                                       )
    return usage_parser


def def_attached_parser(s_parser):
    """
    Define the attached subparser.

    Parameters
    ----------
    s_parser: subparsers.

    Returns
    -------
        ArgumentParser: the attached subcommand parser.
    """
    attached_parser = s_parser.add_parser('attached',
                                          description='Show only the attached volumes.',
                                          help='Show data of the attached volumes.')
    iqnall = attached_parser.add_mutually_exclusive_group(required=True)
    iqnall.add_argument('-i', '--iqn',
                        action='store_true',
                        default=False,
                        help='Show only iqn.')
    iqnall.add_argument('-a', '--all',
                        action='store_true',
                        help='Show all data.')
    attached_parser.add_argument('-o', '--output-mode',
                                 choices=('text', 'json', 'parsable'),
                                 default='text',
                                 help='Output mode text or json format, only valid with --all.'
                                 )
    return attached_parser


def def_all_volume_parser(s_parser):
    """
    Define the all volumes parser.

    Parameters
    ----------
    s_parser: subparsers.

    Returns
    -------
        ArgumentParser: the attached subcommand parser
    """
    all_volume_parser = s_parser.add_parser('all',
                                            description='Show all volumes in availability domain.',
                                            help='Show all volumes in the availability domain if correct privileges '
                                                 'are present.')
    all_volume_parser.add_argument('-o', '--output-mode',
                                   choices=('text', 'json'),
                                   default='text',
                                   help='Output mode text or json format.'
                                   )

    return all_volume_parser


def get_args_parser():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args()).

    Returns
    -------
        The commandline argparse namespace.
    """
    parser = argparse.ArgumentParser(prog='oci-iscsi-config',
                                     description='Utility for listing iSCSI volume data.'
                                     )
    subparser = parser.add_subparsers(dest='command')
    #
    # usage
    _ = def_usage_parser(subparser)
    #
    # attached volumes
    _ = def_attached_parser(subparser)
    #
    # all volumes
    _ = def_all_volume_parser(subparser)

    return parser


def get_instance_id():
    """
    Get the ocid of this instance from the metadata.

    Returns
    -------
        str: the instance ocid
    """
    url = 'http://169.254.169.254/opc/v2/instance/id'
    try:
        req = urllib.request.Request(url=url)
        req.add_header('Authorization', 'Bearer Oracle')
        response = urllib.request.urlopen(req)
        instance_ocid = response.readline().decode('utf-8')
        # print('--- %-35s: %s ---' % ('This instance instance_id', instance_ocid))
        return instance_ocid
    except Exception as e:
        # print('Failed to collect instance_id: %s' % str(e))
        sys.exit(1)


def get_compartment_id():
    """
    Get the ocid of the current compartment from the metadata.

    Returns
    -------
        str: the compartment ocid
    """
    url = 'http://169.254.169.254/opc/v2/instance/compartmentId'
    try:
        req = urllib.request.Request(url=url)
        req.add_header('Authorization', 'Bearer Oracle')
        response = urllib.request.urlopen(req)
        compartment_ocid = response.readline().decode('utf-8')
        # print('--- %-35s: %s ---' % ('This compartment compartment_id', compartment_ocid))
        return compartment_ocid
    except Exception as e:
        # print('Failed to collect compartment_id: %s' % str(e))
        sys.exit(1)


def test_collecting_instance_data(instance_ocid):
    """
    Test the collection of the instance data.

    Parameters
    ----------
    instance_ocid: str
        The instance ocid

    Returns
    -------
        instance.data on success, False otherwise.
    """
    try:
        signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        compute_client = oci_sdk.core.compute_client.ComputeClient(config={}, signer=signer)
        instance_data = compute_client.get_instance(instance_id=instance_ocid).data
        return instance_data
    except Exception as e:
        # not the correct IP authentication.
        return False


def test_collecting_all_volumes_data(compartment_id):
    """
    Test the collection of the data of all volumes in the compartment.

    Parameters
    ----------
    compartment_id: str
        The compartment id.

    Returns
    -------
        volumes list on success, False otherwise.
    """
    try:
        signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        block_storage_client = oci_sdk.core.blockstorage_client.BlockstorageClient(config={}, signer=signer)
        block_storage_data = oci_sdk.pagination.list_call_get_all_results(block_storage_client.list_volumes,
                                                                          compartment_id=compartment_id).data
        # print('--- Successfully verified Instance Principal Authentication for collecting all volumes data. '
        #       'Found %d volume(s).' % len(block_storage_data))
        return block_storage_data
    except Exception as e:
        print('Failed to collect all volume data: %s\nMissing the correct privilege.' % str(e))
        # traceback.print_exception(*sys.exc_info())
    return False


def scan_attached_volumes():
    """
    Scan ip address verifying if block volume attached.

    Returns
    -------
    list: list of dicts with ip, port, iqn.
    """
    all_iqns = list()
    for r in range(MAX_VOLUMES + 1):
        ipaddr = "169.254.2.%d" % (r + 1)
        iqns = discovery(ipaddr)
        # print(iqns)
        for iqn in iqns:
            vol = {'iqn': iqn,
                   'ipaddr': ipaddr,
                   'port': 3260}
            all_iqns.append(vol)
    return all_iqns


def test_collecting_attached_volume_data(compartment_ocid, instance_ocid, arguments):
    """
    Test the collection of the data on attached volumes.
    Parameters
    ----------
    compartment_ocid: str
        The compartment ocid.
    instance_ocid: str
        The instance ocid
    arguments: namespace
        The command line.

    Returns
    -------
        Attached volumes list on success, False otherwise
    """
    try:
        v_att_list = oci_api.OCISession().this_instance().all_volumes()

        # signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        # compute_client = oci_sdk.core.compute_client.ComputeClient(config={}, signer=signer)
        # v_att_list = oci_sdk.pagination.list_call_get_all_results(compute_client.list_volume_attachments,
        #                                                           compartment_id=compartment_ocid,
        #                                                           instance_id=instance_ocid).data
        all_iqns = list()
        for volume in v_att_list:
            vol = {'iqn': volume.get_iqn(),
                   'ipaddr': volume.get_portal_ip(),
                   'port': volume.get_portal_port()}
            if arguments.all:
                vol['display_name'] = volume.get_display_name()
                vol['ocid'] = volume.get_ocid()
                # vol['created'] = str(volume.time_created)
                # vol['volume_id'] = volume.volume_id
            all_iqns.append(vol)
        return all_iqns
    except Exception as e:
        print('Failed to collect attached volume data: %s\nShould not happen here.' % str(e))
        # traceback.print_exception(*sys.exc_info())
    return False


def print_par(tag, value, size):
    """
    Print a variable lenght format string.

    Parameters
    ----------
    tag: str
        head
    value: str
        value
    size: int
        lenght

    Returns
    -------
        No return value
    """
    print(f"{tag:>{size}}: {value}")


def show_attached_volume_data(arguments, context):
    """
    Show the data for attached volumes.

    Parameters
    ----------
    arguments: namespace
        The command line arguements.

    context: dict
        The context.

    Returns
    -------
        int: 0 on success, -1 on failure
    """
    if context['instance_principal']:
        attached_volumes = test_collecting_attached_volume_data(compartment_ocid=context['compartment_id'],
                                                                instance_ocid=context['instance_id'],
                                                                arguments=arguments)
    else:
        attached_volumes = scan_attached_volumes()
        #
        # scanning does only provide ip,port, iqn
        arguments.iqn = True

    if arguments.iqn:
        for volume in attached_volumes:
            if arguments.output_mode == 'json':
                print('%s' % json.dumps(volume, indent=4))
            elif arguments.output_mode == 'parsable':
                print('#%s#%s#%s#' %
                      (volume['ipaddr'],
                       volume['port'],
                       volume['iqn']))
            elif arguments.output_mode == 'text':
                print('%s:%s %s ' %
                      (volume['ipaddr'],
                       volume['port'],
                       volume['iqn']))
            else:
                print('Missing output-mode parameter\n')
                return -1
    elif arguments.all:
        for volume in attached_volumes:
            if arguments.output_mode == 'json':
                print('%s' % json.dumps(volume, indent=4))
            elif arguments.output_mode == 'parsable':
                print('#%s#%s#%s#%s#%s#' %
                      (volume['ipaddr'],
                       volume['port'],
                       volume['iqn'],
                       volume['display_name'],
                       volume['ocid']))
            elif arguments.output_mode == 'text':
                print_par('ipaddr:port', '%s:%s' % (volume['ipaddr'], volume['port']), 12)
                print_par('iqn', volume['iqn'], 20)
                print_par('display name', volume['display_name'], 20)
                print_par('ocid', volume['ocid'], 20)
            else:
                print('Missing output-mode parameter\n')
                return -1
    else:
        print('Missing iqn or all paramater')
        return -1
    return 1


def show_all_volume_data(volumes, args):
    """
    Show data for all volumes in the availability domain.

    Parameters
    ----------
    volumes: list
        list of volume objects.
    args: namespace
        command line

    Returns
    -------
    int: 0 on success, -1 otherwise.
    """
    if args.output_mode == 'text':
        for volume in volumes:
            print_par('display name', volume.display_name, 12)
            print_par('size', volume.size_in_gbs, 20)
            print_par('ocid', volume.id, 20)
            if 'Operations' in volume.defined_tags:
                print_par('created by', volume.defined_tags['Operations']['CreateBy'], 20)
            elif 'Oracle-Tags' in volume.defined_tags:
                print_par('created by', volume.defined_tags['Oracle-Tags']['CreatedBy'], 20)
            else:
                print_par('created by', 'unknown', 20)
            print_par('create time', str(volume.time_created), 20)
            print_par('state', volume.lifecycle_state, 20)
    elif args.output_mode == 'json':
        all_vols = dict()
        for volume in volumes:
            all_vols[volume.display_name] = dict()
            vol_data = dict()
            vol_data['size'] = '%s GB' % volume.size_in_gbs
            vol_data['ocid'] = volume.id
            if 'Operations' in volume.defined_tags:
                vol_data['created by'] = volume.defined_tags['Operations']['CreateBy']
            elif 'Oracle-Tags' in volume.defined_tags:
                vol_data['created by'] = volume.defined_tags['Oracle-Tags']['CreatedBy']
            else:
                vol_data['created by'] = 'unknown'
            vol_data['create time'] = str(volume.time_created)
            vol_data['state'] = volume.lifecycle_state
            all_vols[volume.display_name] = vol_data
        print('%s' % json.dumps(all_vols, indent=4))
    else:
        print('Invalid output mode')
        return -1
    return 0


def main():
    """
    Test if Instance Principal Authentication is configured correctly.

    Returns
    -------
        int
            0 on success, 1 otherwise.
    """
    #
    # command line
    parser = get_args_parser()
    args = parser.parse_args()
    #
    # no arguments defaults to usage
    if args.command is None or args.command == 'usage':
        parser.print_help()
        sys.exit(0)
    #
    # the instance id from the metadata
    instance_id = get_instance_id()
    #
    # the compartment id from the metadata
    compartment_id = get_compartment_id()
    #
    # test the instance data collection
    instance_info = test_collecting_instance_data(instance_id)
    display_name = instance_info.display_name if instance_info else 'this instance'
    #
    # if instance info fails, unlikely instance principals are defined to collect all data from instance.
    instance_principal = bool(instance_info)
    #
    context = dict()
    context['instance_id'] = instance_id
    context['compartment_id'] = compartment_id
    context['display_name'] = display_name
    context['instance_principal'] = instance_principal
    #
    # attached volumes
    if args.command == 'attached':
        if show_attached_volume_data(args, context) < 0:
            parser.print_help()
    #
    # all volumes
    if args.command == 'all':
        if not instance_principal:
            print('Missing privileges to collect data for all volumes.')
            return -1
        #
        # test the listing of all volumes in the compartment.
        all_volumes = test_collecting_all_volumes_data(compartment_id)
        if show_all_volume_data(all_volumes, args) < 0:
            parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
