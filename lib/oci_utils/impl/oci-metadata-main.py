#
# Copyright (c) 2017, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
This utility displays instance metadata when run on Oracle Cloud Infrastructure
instances.  See the manual page for more information.
"""
import argparse
import json
import logging
import os
import sys
# import collections
from collections.abc import Mapping, Iterable

import oci_utils
from oci_utils import oci_regions
from oci_utils.impl.oci_resources import OCIInstance
from oci_utils.metadata import InstanceMetadata
from oci_utils.metadata import _get_by_path, _get_path_keys
from oci_utils.oci_api import OCISession

oci_metadata_detail = {
    'displayName': 'Display Name',
    'hostnameLabel': 'Hostname Label',
    'timeCreated': 'Created at',
    'image': 'Image ID',
    'lifecycleState': 'Lifecycle State',
    'shape': 'Instance shape',
    'region': 'Region',
    'availabilityDomain': 'Availability Domain',
    'compartmentId': 'Compartment OCID',
    'id': 'OCID',
    'macAddr': 'MAC address',
    'subnetCidrBlock': 'Subnet CIDR block',
    'subnetId': 'Subnet ID',
    'vnicId': 'VNIC OCID',
    'privateIp': 'Private IP address',
    'publicIp': 'Public IP address',
    'faultDomain': 'Fault domain',
    'virtualRouterIp': 'Virtual router IP address',
    'vlanTag': 'VLAN Tag',
    'nicIndex': 'NIC Index',
    'metadata': 'Metadata',
    'definedTags': 'Defined Tags',
    'freeformTags': 'Freeform Tags',
    'extendedMetadata': 'Extended Metadata',
    'launchMode': 'Launch Mode',
    'ipxeScript': 'iPXE Script',
    'sourceDetails': 'Source Details',
    'launchOptions': 'Launch Options',
    'skipSourceDestCheck': 'Skip Source/Dest Check',
    'canonicalRegionName': 'Canonical Region Name', }

lower_metadata_fields = {key.lower(): key for key in oci_metadata_detail}

oci_metadata_display_order = [
    'displayName',
    'region',
    'canonicalRegionName',
    'availabilityDomain',
    'faultDomain',
    'id',
    'compartmentId',
    'shape',
    'image',
    'timeCreated',
    'state',
    'vnicId',
    'vlanTag',
    'nicIndex',
    'privateIp',
    'publicIp',
    'macAddr',
    'subnetCidrBlock',
    'virtualRouterIp',
    'definedTags']

human_readable_type = {
    str: 'string type',
    dict: 'json format'}

oci_metadata_ignores = [
    'freeformTags',
    'launchMode',
    'ipxeScript',
    'sourceDetails',
    'launchOptions',
    'skipSourceDestCheck',
    'canonicalRegionName', ]

# exportable keys
exportable_keys = ["metadata", "extendedMetadata"]

_logger = logging.getLogger("oci-utils.oci-metadata")


def parse_args():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args()).

    Returns
    -------
        The argparse namespace.
    """
    parser = argparse.ArgumentParser(prog='oci-metadata',
                                     description='Utility for displaying metadata for an instance running in '
                                                 'the Oracle Cloud Infrastructure.',
                                     add_help=False)
    parser.add_argument('-h', '--human-readable', action='store_true',
                        help='Display human readable output (default)')
    parser.add_argument('-j', '--json', action='store_true',
                        help='Display json output')
    parser.add_argument('-g', '--get', metavar='KEY', dest='keys',
                        action='append', type=str.lower,
                        help='Display the value of a specific key. Key can be any single field-name in metadata json '
                             'output,or a path like /instance/id, or /vnics/*/vnicid')
    parser.add_argument('--value-only', action='store_true',
                        help='Used with one -g option, return a list of values matching the key.')

    parser.add_argument('--export', action='store_true',
                        help='Used with the -g option, export the keys as environment variables.')
    parser.add_argument('--trim', action='store_true',
                        help='Used with the -g option, trim the key path to the last component.')
    parser.add_argument('-u', '--update', nargs='+', metavar='KEY=VALUE ',
                        dest='setkeys',
                        action='append', type=str,
                        help='Update the value for a specific key.  '
                             'KEY can be displayName or a key in the extended metadata. '
                             'VALUE can be a string, JSON data or a pointer to a file containing JSON data. '
                             'Note: do not put spaces around "=".'
                        )
    parser.add_argument('-i', '--instance-id', metavar='OCID',
                        action='store', type=str,
                        help='get or set metadata for the specified instance')
    parser.add_argument('--help', action='help',
                        help='Display this help')

    args = parser.parse_args()
    return args


def pretty_print_section(metadata, indent):
    """
    Display a section of the metadata, indented by the given indent string.

    Parameters
    ----------
    metadata :
        The metadata structure.
    indent : str
        The indentation string.

    Returns
    -------
        No return value.
    """
    # first display the keys that are in the oci_metadata_display_order list
    if not isinstance(metadata, dict):
        for element in list(metadata):
            if isinstance(element, dict):
                pretty_print_section(element, indent + "  ")
            else:
                # if type(element) is str:
                print("%s%s" % (indent, element))
    for key in oci_metadata_display_order:
        if key not in metadata:
            continue

        display_key = key
        if key in oci_metadata_detail:
            display_key = oci_metadata_detail[key]
        value = metadata[key]

        if isinstance(metadata[key], dict):
            print("%s%s:" % (indent, display_key))
            pretty_print_section(value, indent + "  ")
            continue

        if key == 'region':
            if value in oci_regions:
                value = oci_regions[value]
        elif key == 'timeCreated':
            # value = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(metadata['timeCreated']/1000))
            pass
        print("%s%s: %s" % (indent, display_key, value))

    for key in metadata:
        # already printed the ones in oci_metadata_display_order
        if key in oci_metadata_display_order:
            continue
        if key in oci_metadata_ignores:
            continue
        # print it last unless it's listed in oci_metadata_display_order
        if key == 'metadata':
            continue
        display_key = key
        if key in oci_metadata_detail:
            display_key = oci_metadata_detail[key]

        value = metadata[key]

        if isinstance(metadata[key], dict):
            print("%s%s:" % (indent, display_key))
            pretty_print_section(value, indent + "  ")
            continue

        print("%s%s: %s" % (indent, display_key, value))

    # print it last unless it's listed in oci_metadata_display_order
    if 'metadata' in metadata and 'metadata' not in oci_metadata_display_order:
        print("%sInstance Metadata:" % indent)
        pretty_print_section(metadata['metadata'], indent + "  ")


def pretty_print(metadata):
    """
    Display the metadata.

    Parameters
    ----------
    metadata :
        The metadata structure.

    Returns
    -------
         No return value.
    """
    if 'instance' in metadata:
        print("Instance details:")
        pretty_print_section(metadata['instance'], '  ')

    if 'publicIp' in metadata or 'vnics' in metadata:
        print("Networking details:")

        if 'publicIp' in metadata:
            print("  Public IP address: %s" % metadata['publicIp'])

        if 'vnics' in metadata:
            if len(metadata['vnics']) > 1:
                if_num = 1
                for vnic_data in metadata['vnics']:
                    print("  VNIC %s:" % if_num)
                    pretty_print_section(vnic_data, '    ')
                    if_num += 1
            else:
                pretty_print_section(metadata['vnics'][0], '  ')
    elif 'instance' not in metadata:
        # None of the previous sections, for trimmed.
        pretty_print_section(metadata, '')


def dumper(obj):
    """
    JSON serialize an object.

    Parameters
    ----------
    obj : dict
        The object to be serialized.

    Returns
    -------
        str
            JSON encodable version of the passed object.
    """

    try:
        return obj.toJSON()
    except Exception:
        try:
            return obj.__dict__()
        except Exception:
            return obj.__str__()


def parse_var(key_value):
    """
    Parse a key, value pair, seperated by "=".

    Parameters
    ----------
    key_value : str
        The 'key=value'.

    Returns
    -------
        tuple
            key, value
    """
    items = key_value.split('=')
    key = items[0].strip()
    if len(items) > 1:
        value = '='.join(items[1:])
        if len(value) == 0:
            _logger.warning("Value is empty")

        if value.startswith("{"):
            json_acceptable_string = value.replace("'", "\"")
            try:
                tmp = json.loads(json_acceptable_string)
                value = tmp
            except Exception as e:
                _logger.error("Invalid value '%s': %s", value, e)
                sys.exit(1)

        elif value.startswith("file:"):
            try:
                fname = value[5:]
                if os.path.isfile(fname):
                    fp = open(fname, 'r')
                    d = json.loads(fp.read().replace("'", "\""))
                    value = d
                    fp.close()
                else:
                    _logger.error("Invalid file path: %s", fname)
                    sys.exit(1)
            except Exception as e:
                _logger.error("Invalid file content (%s): %s", fname, e)
                sys.exit(1)
    else:
        _logger.error(" -u or --update expects key='value' format, not %s", key_value)
        sys.exit(1)

    return key, value


def parse_vars(items):
    """
    Parse a series of key-value pairs and return a dictionary.

    Parameters
    ----------
    items: list
        List of key,value pairs.

    Returns
    -------
        dict
            Parse key, value pairs
    """
    d = {}
    if items:
        for item_list in items:
            for item in item_list:
                key, value = parse_var(item)
                if key.find('/') >= 0:
                    _logger.error("Key should be simple without path (%s)", key)
                    sys.exit(1)
                d[key] = value
    return d


def verify_setkeys(set_keys):
    """
    Verify the key, value pair according to the OCIInstance.settable_field_type.

    Parameters
    ----------
    set_keys: dict
        The list of key-value pairs

    Returns
    -------
        bool
            True on succes, False otherwise.
    """
    if set_keys is None:
        _logger.error("You must provide a key=value for update option.")
        return False
    keys = list(set_keys.keys())
    for k in keys:
        if k in OCIInstance.settable_field_type:
            v = set_keys[k]
            if isinstance(v, OCIInstance.settable_field_type[k]):
                continue
            _logger.error(" Key %s expects value of %s, not %s.",
                          k, human_readable_type[OCIInstance.settable_field_type[k]], human_readable_type[type(v)])
            return False
        if k.lower() in OCIInstance.lower_settable_fields:
            v = set_keys.pop(k)
            k = OCIInstance.lower_settable_fields.get(k.lower())
            if isinstance(v, OCIInstance.settable_field_type[k]):
                set_keys[k] = v
            else:
                _logger.error(" Key %s expects value of %s, not %s.",
                              k, human_readable_type[OCIInstance.settable_field_type[k]], human_readable_type[type(v)])
                return False

        if k.lower() in lower_metadata_fields or k.lower() in oci_utils.metadata. _attribute_map:
            _logger.error(" Key(%s) is one of the reserved names.", k)
            return False

        if "extendedMetadata" in list(set_keys.keys()):
            extended_metadata = set_keys["extendedMetadata"]
        else:
            extended_metadata = {}

            extended_metadata[k] = set_keys[k]
            set_keys['extendedMetadata'] = extended_metadata
    return True


def get_values(key, metadata):
    """
    Get the metadata for a specified key.

    Parameters
    ----------
    key: str
       The key.
    metadata: dict
       The metadata.

    Returns
    -------
        dict
            The data for the provided ky on success, None otherwise.
    """
    if isinstance(metadata, list):
        if key.isdigit():
            return metadata[int(key)]
        values = []

        for i in range(len(metadata)):
            v = get_values(key, metadata[i])
            if isinstance(v, list):
                values.extend(v)
            elif v is not None:
                values.append(v)
        return values
    if not isinstance(metadata, dict):
        return None
    if key in metadata:
        return metadata[key]

    values = []
    for k in metadata:
        if key == k.lower():
            return metadata[k]
        v = get_values(key, metadata[k])
        if isinstance(v, list):
            values.extend(v)
        elif v is not None:
            values.append(v)
    return values


def get_trimed_key_values(keys, metadata):
    """
    Parameters
    ----------
    keys: list
        a list of getting keys.
    metadata: dict
        a dict of matching values

    Returns
    -------
        dict:
            The trimmed metadata.
    """
    metadata = convert_key_values_to_string(metadata)
    exportKeys = {}
    for key in keys:
        ks = key.split('/')
        if len(ks[-1]) > 0:
            ke = ks[-1]
        else:
            ke = ks[-2]
        if ke in lower_metadata_fields:
            ke = lower_metadata_fields[ke]
        exportKeys[ke] = []
        if len(ks) > 1:
            # path key
            newkey_list = []
            try:
                _get_path_keys(metadata, ks[1:], newkey_list)
            except Exception as e:
                _logger.error('%s', str(e))
                continue
            for _key in newkey_list:
                v = _get_by_path(metadata, _key)
                if v:
                    exportKeys[ke].append(v)
            continue
        v = get_values(ke, metadata)
        if isinstance(v, list):
            exportKeys[ke].extend(v)
        elif v is not None:
            exportKeys[ke].append(v)

    remove_list_for_single_item_list(exportKeys)
    return exportKeys


def remove_list_for_single_item_list(dic):
    """
    If a key in the dictionary have a list value, which has
    one or less item,  then the key
    will be equal to the item in the list.

    Parameters
    ----------
        dic: a dictionary

    Returns
    -------
        dic: the changed dictionary
    """
    for k, v in dic.items():
        if isinstance(v, list):
            if len(v) == 0:
                dic[k] = None
            elif len(v) == 1:
                dic[k] = v[0]


def print_trimed_key_values(keys, metadata):
    """
    Print the trimmed key and its value.

    Parameters
    ----------
        keys: a list of getting keys.
        metadata: a dict of matching values

    Returns
    -------
        No return value.
    """

    kValues = get_trimed_key_values(keys, metadata)
    for k, v in kValues.items():
        if isinstance(v, list):
            for item in v:
                print(k + ": " + str(item))
        else:
            if k == 'region':
                region = oci_regions[v] if v in oci_regions else str(v)
                print(k + ": " + region)
            else:
                print(k + ": " + str(v))


def print_value_only(keys, metadata):
    """
    Print the values only for the matching key.


    Parameters
    ----------
        keys: a list of getting keys.
        metadata: a dict of matching values

    Returns
    -------
        No return value.
    """

    kValues = get_trimed_key_values(keys, metadata)
    for k, v in kValues.items():
        if isinstance(v, list):
            for item in v:
                print(str(item))
        else:
            if k == 'region':
                region = oci_regions[v] if v in oci_regions else str(v)
                print(region)
            else:
                print(str(v))


def export_keys(keys, metadata):
    """
    Export the key and values in the metadata.

    Parameters
    ----------
    keys: list
        The list of keys.
    metadata: dict
        The metadata.

    Returns
    -------
        No return value.
    """

    kValues = get_trimed_key_values(keys, metadata)
    for k, v in kValues.items():
        x = 'export '
        x += k + '=\"'
        if isinstance(v, list):
            end = ""
            for item in v:
                x += end + str(item)
                end = " "
        else:
            x += str(v)
        x += '\" '
        print(x)


def convert_key_values_to_string(this_dict):
    """
    Recursively converts dictionary keys to strings.

    Parameters
    ----------
    this_dict: dict
        The dictionary to convert.

    Returns
    -------
        The string representation.
    """
    # Recursively converts dictionary keys to strings.
    if isinstance(this_dict, str):
        return str(this_dict)
    if isinstance(this_dict, Mapping):
        nd = {}
        for k, v in this_dict.items():
            nd[str(k)] = convert_key_values_to_string(v)
        return nd
    if isinstance(this_dict, Iterable):
        return type(this_dict)(
            convert_key_values_to_string(x) for x in this_dict)
    return this_dict


def main():
    """
    Visualize the metadata.

    Returns
    -------
        0 on success, 1 on failure.
    """
    args = parse_args()

    inst_id = None
    if args.instance_id:
        inst_id = args.instance_id

    if args.export and not args.keys:
        _logger.error("--export only works with --get or -g.")
        return 1

    if args.trim and not args.keys:
        _logger.error("--trim only works with --get or -g. ")
        return 1

    if args.setkeys:
        # set
        if args.keys:
            _logger.error("-g or --get option conflicts with -u or --update.")
            return 1

        k_v = parse_vars(args.setkeys)
        if not verify_setkeys(k_v):
            return 1

        try:
            # meta = oci_utils.oci_api.OCISession().update_instance_metadata(
            # instance_id=inst_id, **k_v)
            meta = OCISession().update_instance_metadata(instance_id=inst_id, **k_v)
            if meta is None:
                #
                # if meta is None, the session failed to update the metadata; the session is writing the error message;
                # this should change...
                return 1
            metadata = meta.filter(list(k_v.keys()))
        except Exception as e:
            _logger.error("%s", str(e), exc_info=True)
            return 1
    else:
        # get
        if args.value_only:
            if len(args.keys) != 1:
                _logger.error("Error: --value-only option works only with one -g or --get option.")
                return 1

        try:
            # if we have an ID, use the session.
            if inst_id is not None:
                meta = OCISession().get_instance(instance_id=inst_id).get_metadata()
            else:
                meta = InstanceMetadata().refresh()
            metadata = meta.filter(args.keys)
        except Exception as e:
            _logger.debug('Failed to get metadata for %s', inst_id, exc_info=True)
            _logger.error("%s", str(e))
            return 1

    if metadata is None:
        if args.keys:
            _logger.error("No matching metadata for '%s' found.", str(args.keys))
        elif args.setkeys:
            _logger.error("No matching metadata for '%s' found.", str(args.setkeys))
        else:
            _logger.error("No metadata found for instance (%s).", inst_id)
        return 1

    if args.value_only:
        print_value_only(args.keys, metadata)
        return 0

    if args.export:
        export_keys(args.keys, metadata)
        return 0

    if args.trim:
        print_trimed_key_values(args.keys, metadata)
        return 0

    if args.json:
        print(json.dumps(metadata, default=dumper, indent=2))
        return 0

    pretty_print(metadata)
    return 0


if __name__ == "__main__":
    sys.exit(main())
