#!/bin/python3
# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Find a the value af an attribute of a vnic based on the value of an attribute of the vnic.
"""
import argparse
import subprocess
import sys

oci_network_path = '/bin/oci-network-config'
vnic_fields = ['state',
               'link',
               'status',
               'ipaddress',
               'vnic',
               'mac',
               'hostname',
               'subnet',
               'routerip',
               'namespace',
               'index',
               'vlantag',
               'vlan']


def parse_args():
    """
    Parse command line parameters.

    Returns
    -------
        namespace parsed arguments.
    """
    parser = argparse.ArgumentParser(description='Utility for collecting 1 attribute of 1 vnic')
    parser.add_argument('-i', '--input_field',
                        action='store',
                        type=str,
                        required=True,
                        choices=vnic_fields,
                        help='The vnic field to select the vnic.')
    parser.add_argument('-v', '--input-value',
                        action='store',
                        type=str,
                        required=True,
                        help='The value of the select field.')
    parser.add_argument('-o', '--output-field',
                        choices=vnic_fields,
                        type=str,
                        required=True,
                        help='The field the value requested from.')
    return parser


def get_vnic_data(index, val, field):
    """
        Return val for vnic based on index.

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
    cmd = [oci_network_path, 'show', '--details', '--output-mode', 'parsable']
    all_vnic_data = subprocess.check_output(cmd).decode('utf-8').splitlines()

    for vnic in all_vnic_data:
        vnic_list = vnic.split('#')
        if index not in vnic_fields or field not in vnic_fields:
            return None
        if vnic_list[vnic_fields.index(index)] == val:
            return vnic_list[vnic_fields.index(field)]
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
    print(get_vnic_data(args.input_field, args.input_value, args.output_field))


if __name__ == "__main__":
    sys.exit(main())
