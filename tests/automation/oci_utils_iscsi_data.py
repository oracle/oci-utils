#!/bin/python3
# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Find a the value af an attribute of an iscsi volume based on the value of an attribute of the volume.
"""
import argparse
import subprocess
import sys

oci_iscsi_path = '/bin/oci-iscsi-config'
volume_attached_fields = ['iqn',
                          'name',
                          'ocid',
                          'persistentportal',
                          'currentportal',
                          'state',
                          'device',
                          'size']
volume_all_fields = ['name',
                     'size',
                     'attached',
                     'ocid',
                     'iqn',
                     'compartment',
                     'availabilitydomain']


def parse_args():
    """
    Parse command line parameters.

    Returns
    -------
        namespace parsed arguments.
    """
    choicelist = list(set(volume_all_fields + volume_attached_fields))
    parser = argparse.ArgumentParser(description='Utility for collecting 1 attribute of 1 volume.')
    parser.add_argument('-i', '--input_field',
                        action='store',
                        type=str,
                        required=True,
                        choices=choicelist,
                        help='The volume field to select the volume.')
    parser.add_argument('-v', '--input-value',
                        action='store',
                        type=str,
                        required=True,
                        help='The value of the select field.')
    parser.add_argument('-o', '--output-field',
                        choices=choicelist,
                        type=str,
                        required=True,
                        help='The field the value requested from.')
    return parser


def get_volume_data(index, val, field):
    """
    Return val for volume based on index.

    Parameters
    ----------
    index: str
        base field name.
    val: str
        base field value.
    field: str
        requested field value.

    Returns
    -------
        str: the requested value, None if absent.
    """
    cmd = [oci_iscsi_path, 'show', '--detail', '--no-truncate', '--output-mode', 'parsable', '--all']
    all_volume_data = subprocess.check_output(cmd).decode('utf-8').splitlines()

    for vol in all_volume_data:
        vol_list = vol.split('#')
        if vol_list[2].startswith('ocid1.'):
            if index not in volume_attached_fields or field not in volume_attached_fields:
                continue
            # is a volume in the 'attached' list
            if vol_list[volume_attached_fields.index(index)] == val:
                return vol_list[volume_attached_fields.index(field)]
        else:
            if index not in volume_all_fields or field not in volume_all_fields:
                continue
            # is a volume in the 'all' list
            if vol_list[volume_all_fields.index(index)] == val:
                return vol_list[volume_all_fields.index(field)]
    return None


def main():
    """
    main

    Returns
    -------
        No retunr value.
    """
    parser = parse_args()
    args = parser.parse_args()
    print(get_volume_data(args.input_field, args.input_value, args.output_field))


if __name__ == "__main__":
    sys.exit(main())
