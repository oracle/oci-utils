# oci-utils
#
# Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Script to upload an on-premise image of a virtual server to an object storage
in the Oracle Cloud Infrastructure.
"""
import argparse
import json
import logging.config
import os
import sys
import time

from oci_utils.migrate import console_msg, exit_with_msg, get_config_data, \
    read_yn, terminal_dimension
from oci_utils.migrate import migrate_tools
from oci_utils.migrate import migrate_utils
from oci_utils.migrate.exception import OciMigrateException


_logger = logging.getLogger('oci-utils.import_up')


def parse_args():
    """
    Parse the command line arguments and return an object representing the
    command
    line as returned by the argparse's parse-args().
    arguments:
    -i|--image-name <image name>; mandatory.
    -b|--bucket-name <bucket name>; mandatory.
    -o|--output-name <output image name>; optional

    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(
        description='Utility to upload on-premise legacy images to object '
                    'storage of the Oracle Cloud Infrastructure.')
    #
    parser.add_argument('-i', '--image-name',
                        action='store',
                        dest='input_image',
                        type=argparse.FileType('r'),
                        required=True,
                        help='The on-premise image name uploaded image.')
    parser.add_argument('-b', '--bucket-name',
                        action='store',
                        dest='bucket_name',
                        required=True,
                        help='The name of the object storage.')
    parser.add_argument('-o', '--output-name',
                        action='store',
                        dest='output_name',
                        help='The name the image will be stored in the object '
                             'storage.')
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        dest='verbose_flag',
                        default=False,
                        help='Show verbose information.')
    parser._optionals.title = 'Arguments'
    args = parser.parse_args()
    if args.output_name is None:
        args.output_name = args.image_name
    return args


def main():
    #
    # set locale
    lc_all_to_set = get_config_data('lc_all')
    os.environ['LC_ALL'] = "%s" % lc_all_to_set
    _logger.debug('Locale set to %s' % lc_all_to_set)
    #
    # command line
    cmdline_args = parse_args()
    #
    # input image
    if cmdline_args.input_image:
        image_path = cmdline_args.input_image.name
        console_msg(msg='\n  Running %s at %s\n'
                        % (os.path.basename(' '.join(sys.argv)), time.ctime()))
    else:
        raise OciMigrateException('Missing argument: input image path.')
    #
    # object storage
    bucket_name = cmdline_args.bucket_name
    #
    # output image
    if cmdline_args.output_name:
        output_name = cmdline_args.output_name
    else:
        output_name = os.path.splitext(os.path.basename(image_path))[0]
    verbose_flag = cmdline_args.verbose_flag
    #
    # message
    console_msg(msg='Uploading %s to object storage %s in the Oracle Cloud '
                    'Infrastructure as %s.' % (image_path,
                                               bucket_name,
                                               output_name))
    #
    # collect data
    try:
        #
        # The oci configuration.
        oci_config = migrate_utils.get_oci_config()
        _logger.debug('Found oci config file')
        #
        # The object storage exist and data.
        object_storage_data = migrate_utils.bucket_exists(bucket_name)
        console_msg(msg='Object storage %s present.' % bucket_name)
        #
        # The object is present in object storage.
        if migrate_utils.object_exists(object_storage_data, output_name):
            raise OciMigrateException('Object %s already exists object '
                                      'storage %s.' % (output_name, bucket_name))
        else:
            _logger.debug('Object %s does not yet exists in object storage %s'
                          % (output_name, bucket_name))
    except Exception as e:
        exit_with_msg('Failed to collect essential data: %s' % str(e))
    #
    # Ask for confirmation to proceed.
    if not read_yn('\n  Agree to proceed uploading %s to %s as %s?'
                   % (image_path, bucket_name, output_name), waitenter=True):
        exit_with_msg('\n  Exiting.')
    #
    # Uploading the image to the Oracle Cloud Infrastructure.
    _, nbcols = terminal_dimension()
    try:
        upload_progress = migrate_tools.ProgressBar(
            nbcols, 0.2, progress_chars=['uploading %s' % output_name])
        #
        # Verify if object already exists.
        if migrate_utils.object_exists(object_storage_data, output_name):
            raise OciMigrateException('Object %s already exists object '
                                      'storage %s.' % (output_name, bucket_name))
        else:
            _logger.debug('Object %s does not yet exists in object storage %s'
                          % (output_name, bucket_name))
        #
        # Upload the image.
        console_msg(msg='\n  Uploading %s, this might take a while....' % image_path)
        upload_progress.start()
        upload_result = migrate_utils.upload_image(image_path,
                                                   bucket_name,
                                                   output_name)
        _logger.debug('Upload result: %s' % upload_result)
        console_msg(msg='  Finished....\n')
        upload_progress.stop()
    except Exception as e:
        _logger.error('  Error while uploading %s to %s: %s.'
                      % (image_path, bucket_name, str(e)))
        exit_with_msg('*** ERROR *** Error while uploading %s to %s: %s.'
                      % (image_path, bucket_name, str(e)))
    finally:
        # if progress thread was started, needs to be terminated.
        if migrate_tools.isthreadrunning(upload_progress):
            upload_progress.stop()


if __name__ == "__main__":
    sys.exit(main())
