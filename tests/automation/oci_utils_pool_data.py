#!/bin/python3
# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Find a the value af an attribute of a kvm pool based on the value of an attribute of the volume.
"""
import argparse
import subprocess
import sys

oci_kvm_path = '/bin/oci-kvm'
pool_fields = ['name',
               'uuid',
               'autostart',
               'active',
               'persistent',
               'volumes',
               'state',
               'capacity',
               'allocation',
               'available']


def parse_args():
    """
    Parse command line parameters.

    Returns
    -------
        namespace parsed arguments.
    """
    choicelist = pool_fields
    parser = argparse.ArgumentParser(description='Utility for collecting 1 attribute of 1 pool')
    parser.add_argument('-i', '--input_field',
                        action='store',
                        type=str,
                        required=True,
                        choices=choicelist,
                        help='The vnic field to select the pool.')
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


def get_pool_data(index, val, field):
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
    cmd = [oci_kvm_path, 'list-pool', '--output-mode', 'parsable']
    all_pool_data = subprocess.check_output(cmd).decode('utf-8').splitlines()

    for pool in all_pool_data:
        pool_list = pool.split('#')
        if index not in pool_fields or field not in pool_fields:
            return None
        if pool_list[pool_fields.index(index)] == val:
                return pool_list[pool_fields.index(field)]
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
    print(get_pool_data(args.input_field, args.input_value, args.output_field))


if __name__ == "__main__":
    sys.exit(main())
