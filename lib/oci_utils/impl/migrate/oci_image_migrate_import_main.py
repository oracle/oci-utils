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
import logging.config
import os
import sys

from oci_utils.migrate import ProgressBar
from oci_utils.migrate import console_msg
from oci_utils.migrate import exit_with_msg
from oci_utils.migrate import migrate_data
from oci_utils.migrate import migrate_tools
from oci_utils.migrate import oci_cli_tools
from oci_utils.migrate import read_yn
from oci_utils.migrate import system_tools
from oci_utils.migrate import terminal_dimension
from oci_utils.migrate.exception import OciMigrateException
from oci_utils.migrate.migrate_tools import get_config_data

_logger = logging.getLogger('oci-utils.oci-image-import')


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
    -y| --yes suppose the answer YES to all Y/N questions
    -v|--verbose produces verbose output.


    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(
        prog='oci-image-migrate-import',
        description='Utility to import a (verified and modified) on-premise '
                    'legacy image which was uploaded to object storage in '
                    'the custom images folder of the Oracle Cloud '
                    'Infrastructure.')
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
    parser.add_argument('--yes', '-y',
                        action='store_true',
                        dest='yes_flag',
                        default=False,
                        help='Answer YES to all y/n questions.')
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        dest='verbose_flag',
                        default=False,
                        help='Show verbose information.')
    parser._optionals.title = 'Arguments'
    args = parser.parse_args()
    if args.display_name is None:
        args.display_name = args.image_name
    return args


def main():
    """
    Import image from object storage into custom images repository.

    Returns
    -------
        int: 0 on success, raises exception on failure.
    """
    #
    # set locale
    lc_all_to_set = get_config_data('lc_all')
    os.environ['LC_ALL'] = "%s" % lc_all_to_set
    _logger.debug('Locale set to %s', lc_all_to_set)
    #
    # command line
    cmdline_args = parse_args()
    console_msg(msg='Importing %s from %s into %s as %s and setting '
                    'launch_mode to %s.' % (cmdline_args.image_name,
                                            cmdline_args.bucket_name,
                                            cmdline_args.bucket_name,
                                            cmdline_args.display_name,
                                            cmdline_args.launch_mode))
    compartment = cmdline_args.compartment_name
    bucket = cmdline_args.bucket_name
    object_name = cmdline_args.image_name
    display_name = cmdline_args.display_name
    launch_mode = cmdline_args.launch_mode
    migrate_data.verbose_flag = cmdline_args.verbose_flag
    migrate_data.yes_flag = cmdline_args.yes_flag
    #
    # collect data
    try:
        #
        # oci configuration
        oci_config = migrate_tools.get_oci_config()
        _logger.debug('Found oci config file')
        #
        # compartment data for tenancy
        tenancy = oci_config['tenancy']
        _logger.debug('Tenancy: %s', tenancy)
        compartment_dict = oci_cli_tools.get_tenancy_data(tenancy)
        #
        # object storage namespace
        os_namespace = oci_cli_tools.get_os_namespace()
        console_msg(msg='Object storage namespace: %s' % os_namespace)
        #
        # compartment ocid
        compartment_id = oci_cli_tools.find_compartment_id(compartment,
                                                           compartment_dict)
        #
        # object storage exist and data
        object_storage_data = oci_cli_tools.bucket_exists(bucket)
        console_msg(msg='Object storage %s present.' % bucket)
        #
        # object present in object storage
        if oci_cli_tools.object_exists(object_storage_data, object_name):
            _logger.debug('Object %s present in object_storage %s', object_name, bucket)
        else:
            raise OciMigrateException('Object %s does not exist in the  object '
                                      'storage %s.' % (object_name, bucket))
        #
        # display name present
        if oci_cli_tools.display_name_exists(display_name, compartment_id):
            raise OciMigrateException('Image with name %s already exists.'
                                      % display_name)
        _logger.debug('%s does not exist', display_name)
    except Exception as e:
        exit_with_msg('Error while importing %s data: %s' % (object_name, str(e)))
    #
    # Ask for confirmation to proceed with upload.
    if not read_yn('\n  Import %s to %s as %s'
                   % (object_name, compartment, display_name),
                   waitenter=True,
                   suppose_yes=migrate_data.yes_flag):
        exit_with_msg('Exiting.\n')
    #
    # Start the import.
    try:
        _ = oci_cli_tools.import_image(object_name,
                                       display_name,
                                       compartment_id,
                                       os_namespace,
                                       bucket,
                                       launch_mode)
    except Exception as e:
        exit_with_msg('Failed to import %s: %s' % (object_name, str(e)))
    #
    # Follow up the import.
    finished = False
    _, nb_columns = terminal_dimension()
    import_progress = ProgressBar(nb_columns, 0.2, progress_chars=['importing %s' % display_name])
    import_progress.start()
    try:
        while not finished:
            if oci_cli_tools.get_lifecycle_state(display_name, compartment_id) == 'AVAILABLE':
                finished = True
    except Exception as e:
        _logger.error('Failed to follow up on the import of %s, giving up: %s', display_name, str(e))

    if system_tools.is_thread_running(import_progress):
        import_progress.stop()
    console_msg(msg='Done')
    return 0


if __name__ == "__main__":
    sys.exit(main())
