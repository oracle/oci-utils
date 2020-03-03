# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Script to import an on-premise virtual server from an object storage to the
custom images in the Oracle Cloud Infrastructure. An image which passed the
checks and modifications of - and was uploaded by the oci-image-migrate
utility should import fine.
"""
import argparse
import json
import logging.config
import os
import sys

from oci_utils.migrate import console_msg, exit_with_msg, get_config_data, read_yn
from oci_utils.migrate import migrate_tools
from oci_utils.migrate import migrate_utils

if sys.version_info.major < 3:
    exit_with_msg('Python version 3 is a requirement to run this utility.')

_logger = logging.getLogger('oci-utils.import_ci')


def parse_args():
    """
    Parse the command line arguments and return an object representing the
    command
    line as returned by the argparse's parse-args().
    arguments:
    -i|--image-name <image name>; mandatory.
    -b|--bucket-name <bucket name>; mandatory.
    -c|--compartment-name <compartment name>; mandatory.
    -l|--launch-mode [PARAVIRTUALIZED|EMULATED|NATIVE]; optional, the default
         is PARAVIRTUALIZED.
    -d|--display-name <display name>; optional.

    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(
        description='Utility to import a (verified and modified) on-premise '
                    'legacy images which was uploaded to object storage in '
                    'the custom images folder of the Oracle Cloud '
                    'Infrastructure.',
        add_help=False)
    #
    parser.add_argument('-i', '--image-name',
                        action='store',
                        dest='image_name',
                        required=True,
                        help='The name of the object representing the '
                             'uploaded image.')
    parser.add_argument('-b', '--bucket-name',
                        action='store',
                        dest='bucket_name',
                        required=True,
                        help='The name of the object storage.')
    parser.add_argument('-c', '--compartment-name',
                        action='store',
                        dest='compartment_name',
                        required=True,
                        help='The name of the destination compartment.')
    parser.add_argument('-d', '--display-name',
                        action='store',
                        dest='display_name',
                        help='Image name as it will show up in the custom '
                             'images; the default is the image name.',
                        default=None)
    parser.add_argument('-l', '--launch-mode',
                        action='store',
                        dest='launch_mode',
                        help='The mode the instance created from the custom '
                             'image will be started; the default '
                             'is PARAVIRTUALIZED.',
                        choices=['PARAVIRTUALIZED', 'EMULATED', 'NATIVE'],
                        default='PARAVIRTUALIZED')
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        dest='verbose_flag',
                        default=False,
                        help='Show verbose information.')
    parser.add_argument('--help', action='help', help='Display this help')
    parser._optionals.title = 'Arguments'
    args = parser.parse_args()
    if args.display_name is None:
        args.display_name = args.image_name
    return args


def main():
    #
    # set locale
    lc_all_to_set = get_config_data('lc_all')
    os.environ['LC_ALL'] = "%s" % lc_all_to_set
    _logger.debug('Locale set to %s' % lc_all_to_set)
    #
    # command line
    cmdlineargs = parse_args()
    console_msg(msg='Importing %s from %s into %s as %s and setting '
                    'launch_mode to %s.' % (cmdlineargs.image_name,
                                           cmdlineargs.bucket_name,
                                           cmdlineargs.bucket_name,
                                           cmdlineargs.display_name,
                                           cmdlineargs.launch_mode))
    compartment = cmdlineargs.compartment_name
    bucket = cmdlineargs.bucket_name
    object_name = cmdlineargs.image_name
    display_name = cmdlineargs.display_name
    launch_mode = cmdlineargs.launch_mode
    verbose_flag = cmdlineargs.verbose_flag
    #
    # oci config file 
    try:
        ocicfg = migrate_utils.get_oci_config()
        console_msg('Found oci config file')
        tenancy = ocicfg['tenancy']
        console_msg(msg='Tenancy = %s' % tenancy)
        _logger.debug('Tenancy: %s' % tenancy)
        cmd = ['oci', 'iam', 'compartment', 'list', '-c', '%s' % tenancy,
               '--all']
        if verbose_flag:
            console_msg(msg='Running: %s' % cmd)
        cmpdict = json.loads(migrate_tools.run_popen_cmd(cmd))
    except Exception as e:
        exit_with_msg('Failed to locate or read the oci config file, is oci '
                      'cli installed?: %s' % str(e))
    #
    # namespace
    cmd = ['oci', 'os', 'ns', 'get']
    try:
        if verbose_flag:
            console_msg(msg='Running: %s' % cmd)
        nsdict = json.loads(migrate_tools.run_popen_cmd(cmd))
        namespace = nsdict['data']
        console_msg(msg='Namespace: %s' % namespace)
    except Exception as e:
        exit_with_msg('Failed to identify the namespace: %s' % str(e))
    #
    # compartment
    try:
        foundcom = False
        for k, v in list(cmpdict.items()):
            for x in v:
                if x['name'] == compartment:
                    compdata = x
                    # print(compdata)
                    console_msg(msg='Compartment data: %s' % compdata['id'])
                    compartment_id = compdata['id']
                    foundcom = True
                    break
        if not foundcom:
            exit_with_msg('Failed to find %s' % compartment)
    except Exception as e:
        exit_with_msg('Failed to find %s: %s' % (compartment, str(e)))
    #
    # bucket
    try:
        bucketcontents = migrate_utils.bucket_exists(bucket)
        if verbose_flag:
            console_msg(msg='Object storage %s present.' % bucket)
    except Exception as e:
        exit_with_msg('Object storage %s not found: %s' % (bucket, str(e)))
    #
    # bucket data
    try:
        cmd = ['oci', 'os', 'bucket', 'get', '--bucket-name', '%s' % bucket]
        if verbose_flag:
            console_msg(msg='Running: %s' % cmd)
        bucketlist = migrate_tools.run_popen_cmd(cmd)
        if bucketlist is not None:
            bucketdict = json.loads(bucketlist)
            _logger.debug('Object storage data: %s' % bucketdict)
        else:
            if verbose_flag:
                console_msg(msg='Bucket data for %s is empty.' % bucket)
    except Exception as e:
        exit_with_msg('Failed to get data of %s: %s' % (bucket, str(e)))
    #
    # bucket contents
    try:
        cmd = ['oci', 'os', 'object', 'list', '--bucket-name', '%s' % bucket]
        if verbose_flag:
            console_msg('Running: %s' % cmd)
        bucketcontents = migrate_tools.run_popen_cmd(cmd)
        if bucketcontents is not None:
            bucketcontentsdict = json.loads(bucketcontents)
            _logger.debug(('Object storage contents: %s' % bucketcontentsdict))
        else:
            if verbose_flag:
                console_msg(msg='Bucket %s is emtpy.' % bucket)
    except Exception as e:
        exit_with_msg('Failed to get contents of %s: %s' % (bucket, str(e)))
        #
    # object exists?
    if migrate_utils.object_exists(bucketcontents, object_name):
        if verbose_flag:
            console_msg(msg='Object %s present in %s.' % (object_name, bucket))
    else:
        exit_with_msg('Object %s missing from %s.' % (object_name, bucket))
    #
    # display name exists?
    cmd = ['oci', 'compute', 'image', 'list', '--compartment-id',
           '%s' % compartment_id, '--display-name',
           '%s' % display_name]
    if verbose_flag:
        console_msg('Running: %s' % cmd)
    objstat = migrate_tools.run_popen_cmd(cmd)
    if objstat is not None:
        exit_with_msg('Image with name %s already exists.' % display_name)
    else:
        if verbose_flag:
            console_msg('Image with name %s not yet imported.' % display_name)
        else:
            _logger.debug('Image with name %s not yet imported.' % display_name)
    #
    # upload?
    if not read_yn('\n  Import %s to %s as %s'
                   % (object_name, compartment, display_name), waitenter=True):
        exit_with_msg('Exiting.\n')
    cmd = ['oci', 'compute', 'image', 'import', 'from-object', '--bucket-name',
           '%s' % bucket, '--compartment-id', '%s' % compartment_id,
           '--name', '%s' % object_name, '--namespace', '%s' % namespace,
           '--launch-mode', launch_mode, '--display-name', '%s' % display_name]
    if verbose_flag:
        console_msg(msg='Running: %s' % cmd)
    try:
        resval = migrate_tools.run_popen_cmd(cmd)
    except Exception as e:
        exit_with_msg('Failed to import %s: %s' % (object_name, str(e)))
    #
    # follow up
    cmd = ['oci', 'compute', 'image', 'list', '--compartment-id',
           '%s' % compartment_id, '--display-name', '%s' % display_name]
    finished = False
    _, clmns = os.popen('stty size', 'r').read().split()
    importwait = migrate_tools.ProgressBar(int(clmns), 0.2,
                                           progress_chars=['importing %s' %
                                                           display_name])
    importwait.start()
    while not finished:
        objstat = json.loads(migrate_tools.run_popen_cmd(cmd))
        for ob in objstat['data']:
            if ob['display-name'] == display_name:
                if ob['lifecycle-state'] == 'AVAILABLE':
                    finished = True
            else:
                console_msg(msg='%s not found.' % display_name)
    if migrate_tools.isthreadrunning(importwait):
        importwait.stop()
    console_msg(msg='Done')
    return 0


if __name__ == "__main__":
    sys.exit(main())
