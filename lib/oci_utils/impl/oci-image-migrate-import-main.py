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

from oci_utils.migrate import console_msg, exit_with_msg, read_yn
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
    -b|--bucket-name <bucket name>; mandatdory.
    -c|--compartment-name <compartment name>; mandatory.
    -l|--launch-mode [PARAVIRTUALIZED|EMULATED|NATIVE]; optional, the default
         is PARAVIRTUALIZED.
    -d|--displayname <display name>; optional.
    
    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(
        description='Utility to import a (verified and modified) on-premise '
                    'legacy images which was uploaded to object storage in '
                    'the custom images folderof the Oracle Cloud '
                    'Infrastructure.',
        add_help=False)
    #
    parser.add_argument('-i', '--image-name',
                        action='store',
                        dest='imagename',
                        required=True,
                        help='The name of the object representing the '
                             'uploaded image.')
    parser.add_argument('-b', '--bucket-name',
                        action='store',
                        dest='bucketname',
                        required=True,
                        help='The name of the object storage.')
    parser.add_argument('-c', '--compartment-name',
                        action='store',
                        dest='compartmentname',
                        required=True,
                        help='The name of the destination compartment.')
    parser.add_argument('-d', '--display-name',
                        action='store',
                        dest='displayname',
                        help='Image name as it will show up in the custom '
                             'images; the default is the image name.',
                        default=None)
    parser.add_argument('-l', '--launch-mode',
                        action='store',
                        dest='launchmode',
                        help='The mode the instance created from the custom '
                             'image will be started; the default '
                             'is PARAVIRTUALIZED.',
                        choices=['PARAVIRTUALIZED', 'EMULATED', 'NATIVE'],
                        default='PARAVIRTUALIZED')
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        dest='verboseflag',
                        default=False,
                        help='Show verbose information.')
    parser.add_argument('--help', action='help', help='Display this help')
    parser._optionals.title = 'Arguments'
    args = parser.parse_args()
    if args.displayname is None:
        args.displayname = args.imagename
    return args


def main():
    #
    # command line
    cmdlineargs = parse_args()
    console_msg(msg='Importing %s from %s into %s as %s and setting '
                    'launchmode to %s.' % (cmdlineargs.imagename,
                                           cmdlineargs.bucketname,
                                           cmdlineargs.bucketname,
                                           cmdlineargs.displayname,
                                           cmdlineargs.launchmode))
    compartment = cmdlineargs.compartmentname
    bucket = cmdlineargs.bucketname
    objectname = cmdlineargs.imagename
    displayname = cmdlineargs.displayname
    launchmode = cmdlineargs.launchmode
    verboseflag = cmdlineargs.verboseflag
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
        if verboseflag:
            console_msg(msg='Running: %s' % cmd)
        cmpdict = json.loads(migrate_tools.run_popen_cmd(cmd))
    except Exception as e:
        exit_with_msg('Failed to locate or read the oci config file, is oci '
                      'cli installed?: %s' % str(e))
    #
    # namespace
    cmd = ['oci', 'os', 'ns', 'get']
    try:
        if verboseflag:
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
        for k, v in cmpdict.items():
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
        if verboseflag:
            console_msg(msg='Object storage %s present.' % bucket)
    except Exception as e:
        exit_with_msg('Object storage %s not found: %s' % (bucket, str(e)))
    #
    # bucket data
    try:
        cmd = ['oci', 'os', 'bucket', 'get', '--bucket-name', '%s' % bucket]
        if verboseflag:
            console_msg(msg='Running: %s' % cmd)
        bucketlist = migrate_tools.run_popen_cmd(cmd)
        if bucketlist is not None:
            bucketdict = json.loads(bucketlist)
            _logger.debug('Object storage data: %s' % bucketdict)
        else:
            if verboseflag:
                console_msg(msg='Bucket data for %s is empty.' % bucket)
    except Exception as e:
        exit_with_msg('Failed to get data of %s: %s' % (bucket, str(e)))
    #
    # bucket contents
    try:
        cmd = ['oci', 'os', 'object', 'list', '--bucket-name', '%s' % bucket]
        if verboseflag:
            console_msg('Running: %s' % cmd)
        bucketcontents = migrate_tools.run_popen_cmd(cmd)
        if bucketcontents is not None:
            bucketcontentsdict = json.loads(bucketcontents)
            _logger.debug(('Object storage contents: %s' % bucketcontentsdict))
        else:
            if verboseflag:
                console_msg(msg='Bucket %s is emtpy.' % bucket)
    except Exception as e:
        exit_with_msg('Failed to get contents of %s: %s' % (bucket, str(e)))
        #
    # object exists?
    if migrate_utils.object_exists(bucketcontents, objectname):
        if verboseflag:
            console_msg(msg='Object %s present in %s.' % (objectname, bucket))
    else:
        exit_with_msg('Object %s missing from %s.' % (objectname, bucket))
    #
    # display name exists?
    cmd = ['oci', 'compute', 'image', 'list', '--compartment-id',
           '%s' % compartment_id, '--display-name',
           '%s' % displayname]
    if verboseflag:
        console_msg('Running: %s' % cmd)
    objstat = migrate_tools.run_popen_cmd(cmd)
    if objstat is not None:
        exit_with_msg('Image with name %s already exists.' % displayname)
    else:
        if verboseflag:
            console_msg('Image with name %s not yet imported.' % displayname)
        else:
            _logger.debug('Image with name %s not yet imported.' % displayname)
    #
    # upload?
    if not read_yn('\n  Uploading %s to %s as %s'
                   % (objectname, compartment, displayname)):
        exit_with_msg('Exiting.\n')
    cmd = ['oci', 'compute', 'image', 'import', 'from-object', '--bucket-name',
           '%s' % bucket, '--compartment-id', '%s' % compartment_id,
           '--name', '%s' % objectname, '--namespace', '%s' % namespace,
           '--launch-mode', launchmode, '--display-name', '%s' % displayname]
    if verboseflag:
        console_msg(msg='Running: %s' % cmd)
    try:
        resval = migrate_tools.run_popen_cmd(cmd)
    except Exception as e:
        exit_with_msg('Failed to import %s: %s' % (objectname, str(e)))
    #
    # follow up
    cmd = ['oci', 'compute', 'image', 'list', '--compartment-id',
           '%s' % compartment_id, '--display-name', '%s' % displayname]
    finished = False
    _, clmns = os.popen('stty size', 'r').read().split()
    importwait = migrate_tools.ProgressBar(int(clmns), 0.2,
                                           progress_chars=['importing %s' %
                                                           displayname])
    importwait.start()
    while not finished:
        objstat = json.loads(migrate_tools.run_popen_cmd(cmd))
        for ob in objstat['data']:
            if ob['display-name'] == displayname:
                if ob['lifecycle-state'] == 'AVAILABLE':
                    finished = True
            else:
                console_msg(msg='%s not found.' % displayname)
    if migrate_tools.isthreadrunning(importwait):
        importwait.stop()
    console_msg(msg='Done')
    return 0


if __name__ == "__main__":
    sys.exit(main())
