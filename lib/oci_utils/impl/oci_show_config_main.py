# oci-utils
#
# Copyright (c) 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Read the OCI SDK config and return the config data through stdout.
"""

import argparse
import json
import sys

from oci_utils import oci_api

debug = False


def parse_args():
    """
    Define the args parser 


    Returns
    -------
        ArgumentParser: the parser.
    """
    parser = argparse.ArgumentParser(prog='show_config',
                                     description='Utility to show oci config file for 1 profile')
    parser.add_argument('-c', '--config',
                        action='store',
                        dest='configfile',
                        default='~/.oci/config',
                        help='The cli/sdk config file, default is ~/.oci/config.')
    parser.add_argument('-p', '--profile',
                        action='store',
                        dest='profile',
                        default='DEFAULT',
                        help='The profile, default is DEFAULT')
    args = parser.parse_args()
    return args


def response(status, **kwargs):
    """
    Send a json formatted response to stdout, jdata is already json formatted.

    Parameters
    ----------
    status: str
        The status.
    kwargs: key,value
        The data to convert to json.

    Returns
    -------
        str
           The json formatted version of **kwargs
    """
    resp = {'status': status}
    for key, val in kwargs.items():
        resp[key] = val
    sys.stdout.write(json.dumps(resp) + '\n')
    sys.stdout.flush()


def main():
    """
    Main program

    Returns
    -------
        int
            0
    """
    args = parse_args()

    try:
        session = oci_api.OCISession(config_file=args.configfile, config_profile=args.profile, authentication_method=oci_api.DIRECT)
    except Exception as e:
        response('*** ERROR ***', data=str(e))
        return 1

    response('OK', data=session.oci_config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
