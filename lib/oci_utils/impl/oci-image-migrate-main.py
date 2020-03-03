# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Script to migrate on-premise virtual servers to the Oracle Cloud
Infrastructure. The candidate image needs to comply with:
- BIOS or UEFI boot;
- image size is maximum 300GB;
- contain one disk containing Master Boot Record and boot loader;
- no additional volumes are required to complete the boot process;
- the boot and root partitions are not encrypted;
- the image is a single file in VMDK or QCOW2 format;
- the boot loader uses UUID or LVM to locate the boot volume;
- the network configuration does not contain hardcoded MAC addresses;
"""

import argparse
import importlib
import logging.config
import os
import pkgutil
import re
import sys
import time

from oci_utils.migrate import exit_with_msg, get_config_data, pause_msg, read_yn
from oci_utils.migrate import migrate_tools
from oci_utils.migrate import migrate_utils
from oci_utils.migrate.exception import OciMigrateException

if sys.version_info.major < 3:
    exit_with_msg('Python version 3 is a requirement to run this utility.')

_logger = logging.getLogger('oci-utils.oci-image-migrate')
#
# Dictionary containing utilities which might be needed with the packages
# which provide them.
try:
    helpers_list = get_config_data('helpers_list')
except Exception as e:
    exit_with_msg('Failed to retrieve the list of required utilities. Verify '
                  'the existence and contents of the configuration file '
                  'oci-migrate-conf.yaml.')


def parse_args():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args())
    arguments:
     -i|--input-image <on-premise image>; mandatory.
     -b|--bucket <bucket name>; mandatory.
     -o|--output-image <output image name>; optional.
     -v|--verbose produces verbose output.
     -h|--help

    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(
        description='Utility to support preparation of on-premise legacy '
                    'images for importing in the Oracle Cloud Infrastructure.',
        add_help=False)
    #
    parser.add_argument('-i', '--input-image',
                        action='store',
                        dest='input_image',
                        type=argparse.FileType('r'),
                        required=True,
                        help='The on-premise image for migration to OCI.')
    parser.add_argument('-b', '--bucket',
                        action='store',
                        dest='bucket_name',
                        required=True,
                        help='The destination bucket in OCI to store '
                             'the converted image.')
    parser.add_argument('-o', '--output-image',
                        action='store',
                        dest='output_image',
                        help='The output image name.')
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        dest='verbose_flag',
                        default=False,
                        help='Show verbose information.')
    parser.add_argument('--help',
                        action='help',
                        help='Display this help')
    parser._optionals.title = 'Arguments'

    args = parser.parse_args()
    return args


def import_formats():
    """
    Import modules which handle different image formats and construct the
    format data dictionary. Check the object definitions for the
    'format_data' attribute.

    Returns
    -------
        dict: Dictionary containing for each image format at least:
              { magic number : { name : <type name>,
                                 module : <module name>,
                                 clazz : <the class name>,
                                 prereq : <prequisites dictionary>
                                }
              }
    """
    attr_format = 'format_data'
    imagetypes = dict()
    packagename = 'oci_utils.migrate'
    pkg = __import__(packagename)
    _logger.debug('pkg name: %s' % pkg)
    path = os.path.dirname(sys.modules.get(packagename).__file__)
    _logger.debug('path: %s' % path)
    #
    # loop through modules in path, look for the attribute 'format_data' which
    # defines the basics of the image type, i.e. the magic number, the name and
    # essentially the class name and eventually prequisites.
    for _, module_name, _ in pkgutil.iter_modules([path]):
        type_name = packagename + '.' + module_name
        _logger.debug('type_name: %s' % type_name)
        try:
            impret = importlib.import_module(type_name)
            _logger.debug('import result: %s' % impret)
            attrret = getattr(sys.modules[type_name], attr_format)
            _logger.debug('attribute format_data: %s' % attrret)
            for key in attrret:
                if key != get_config_data('dummy_format_key'):
                    imagetypes.update(attrret)
                else:
                    _logger.debug('%s is the dummy key, skipping.' % key)
        except Exception as e:
            _logger.debug('attribute %s not found in %s: %s'
                          % (attr_format, type_name, str(e)))
    return imagetypes


def show_utilities(found, missing):
    """
    Display the status of the required utilities.

    Parameters
    ----------
    found: list
        List of found utilities.
    missing: list
        List of missing utilities.

    Returns
    -------
        No return value.
    """
    if found:
        print('\n  %30s\n%s' % ('  Utilities found:', '  ' + '-'*60))
        for util in found:
            print('  %30s' % util)
    if missing:
        print('\n  %30s\n%s' % ('  Utilities not found:', '  ' + '-'*60))
        for util in missing:
            print('  %30s, needs package %s' % (util, helpers_list[util]))
    print('\n')


def show_supported_formats_data(supported_images):
    """
    Display the data collected from the image type modules.

    Parameters
    ----------
    supported_images: dict
        Data about the supported image types.

    Returns
    -------
        No return value.
    """
    print('\n  %25s\n  %25s\n  %25s : %-20s\n  %25s   %-20s'
          % ('Supported image formats', '-'*25,
             'Magic Key', 'Format data', '-'*20, '-'*20))
    for key in sorted(supported_images):
        print('  %25s : ' % key)
        one_image = supported_images[key]
        for yek in sorted(one_image):
            print('  %35s : %s' % (yek, one_image[yek]))
        print('\n')


def collect_image_data(img_object):
    """
    Verify the prerequisites of the image file with respect to the migration
    to the Oracle Cloud Infrastructure.

    Parameters
    ----------
    img_object: Qcow2Head, VmdkHead, SomeTypeHead..  object
        The image object.

    Returns
    -------
        dict:
            The image data.
    """
    try:
        res, img_info = img_object.image_data()
    except Exception as e:
        _logger.critical('   Unable to collect or invalid image data: %s'
                         % str(e), exc_info=True)
        raise OciMigrateException('Unable to collect or invalid image data: %s'
                                  % str(e))
    # need to return the img_info object in the end...
    return res, img_info


def test_helpers():
    """
    Verify which utilities are available.

    Returns
    -------
        helpers: List of available utilities.
        missing: List of missing utilities.
    """
    helpers = []
    missing = []
    path_env_var = os.getenv('PATH')
    _logger.debug('PATH is %s' % path_env_var)
    for util in helpers_list:
        cmd = ['which', util]
        try:
            ocipath = migrate_tools.run_popen_cmd(cmd).decode('utf-8')
            _logger.debug('%s path is %s' % (util, ocipath))
        except Exception as e:
            _logger.error('   Cannot find %s anymore: %s' % (util, str(e)),
                          exc_info=True)
        try:
            _logger.debug('Availability of %s' % util)
            fullcmd = migrate_tools.exec_exists(util)
            _logger.debug('full path: %s' % fullcmd)
            if migrate_tools.exec_exists(util):
                helpers.append(util)
            else:
                missing.append(util)
        except Exception as e:
            _logger.error('   utility %s is not installed: %s'
                          % (helpers_list[util], str(e)))
    return helpers, missing


def qemu_img_version():
    """
    Retrieve the version of qemu-img.

    Returns:
    -------
        versiondata: str
        versionnb: int
    """
    _logger.debug('Retrieve qemu-img release data.')
    cmd = ['qemu-img', '--version']
    versionstring = migrate_tools.run_popen_cmd(cmd).decode('utf-8').splitlines()
    ptrn = re.compile(r'[. -]')
    _logger.debug('qemu-img version: %s' % versionstring)
    for lin in versionstring:
        if 'version' in lin:
            ver_elts = ptrn.split(lin)
            for elt in ver_elts:
                if elt.isnumeric():
                    return lin, int(elt)
    return 0


def main():
    """
    Main

    Returns
    -------
        int
            0 on success, 1 otherwise.
    """
    #
    # set locale
    lc_all_to_set = get_config_data('lc_all')
    os.environ['LC_ALL'] = "%s" % lc_all_to_set
    _logger.debug('Locale set to %s' % lc_all_to_set)
    #
    # python version
    pythonver = sys.version_info[0]
    args = parse_args()
    #
    _logger.debug('Python version is %s' % pythonver)
    #
    # Verbose mode is False by default
    verbose_flag = args.verbose_flag
    migrate_tools.verbose_flag = verbose_flag
    _logger.debug('Verbose level set to %s' % verbose_flag)
    #
    # Operator needs to be root.
    if migrate_tools.is_root():
        _logger.debug('User is root.')
    else:
        exit_with_msg('  *** ERROR *** %s needs to be run as root user'
                      % sys.argv[0])
    try:
        #
        # input image
        if args.input_image:
            imagepath = args.input_image.name
            resultfilename = get_config_data('resultfilepath') \
                            + '_' \
                            + os.path.splitext(os.path.basename(imagepath))[0] \
                            + '.res'
            migrate_tools.resultfilename = resultfilename
            migrate_tools.result_msg(msg='\n  Running %s at %s\n'
                                     % (os.path.basename(' '.join(sys.argv)),
                                     time.ctime()), flags='w', result=True)
        else:
            raise OciMigrateException('Missing argument: input image path.')
        #
        # Import the 'format' modules and collect the format data
        supported_formats = import_formats()
        if verbose_flag:
            show_supported_formats_data(supported_formats)
        #
        # Check the utilities installed.
        util_list, missing_list = test_helpers()
        _logger.debug('%s' % util_list)
        if verbose_flag:
            show_utilities(util_list, missing_list)
        if missing_list:
            raise OciMigrateException('%s needs packages %s installed.\n'
                                      % (sys.argv[0], missing_list), 1)
        #
        # if qemu-img is used, the minimal version is 3
        qemuversioninfo = qemu_img_version()
        if qemuversioninfo[1] < 3:
            raise OciMigrateException('Minimal version of qemu-img is 3, %s found.' % qemuversioninfo[0])
        else:
            _logger.debug('release data ok')
        #
        # Check if oci-cli is configured.
        if os.path.isfile(get_config_data('ociconfigfile')):
            migrate_tools.result_msg(msg='oci-cli config file exists.')
        else:
            raise OciMigrateException('oci-cli is not configured.')
        #
        # Get the nameserver definition
        if migrate_tools.get_nameserver():
            _logger.debug('Nameserver identified as %s' % migrate_tools.nameserver)
        else:
            migrate_tools.error_msg('Failed to identify nameserver, using %s, '
                                    'but might cause issues.' % migrate_tools.nameserver)
        #
        # bucket
        bucket_name = args.bucket_name
        migrate_tools.result_msg(msg='Bucket name:  %s' % bucket_name, result=True)
        #
        # Verify if object storage exits.
        try:
            bucket_data = migrate_utils.bucket_exists(bucket_name)
            migrate_tools.result_msg(msg='Object storage %s exists.' % bucket_name, result=True)
        except Exception as e:
            raise OciMigrateException(str(e))
        #
        # output image
        if args.output_image:
            output_name = args.output_image
        else:
            output_name = os.path.splitext(os.path.basename(imagepath))[0]
        migrate_tools.result_msg(msg='Output name:  %s\n' % output_name, result=True)
        #
        # bucket
        bucket_name = args.bucket_name
        migrate_tools.result_msg(msg='Bucket name:  %s' % bucket_name, result=True)
        #
        # Verify if object already exists.
        if migrate_utils.object_exists(bucket_data, output_name):
            raise OciMigrateException('Object %s already exists in object '
                                      'storage %s.' % (output_name, bucket_name))
        else:
            _logger.debug('Object %s does not yet exists in object storage %s' % (output_name, bucket_name))
    except Exception as e:
        exit_with_msg('  *** ERROR *** %s\n' % str(e))
    #
    # More on command line arguments.
    #
    # initialise output
    migrate_tools.result_msg(msg='Results are written to %s.'
                                 % resultfilename, result=True)
    migrate_tools.result_msg(msg='Input image:  %s' % imagepath, result=True)
    #
    # output image
    if args.output_image:
        output_name = args.output_image
    else:
        output_name = os.path.splitext(os.path.basename(imagepath))[0]
    migrate_tools.result_msg(msg='Output name:  %s\n' % output_name, result=True)
    #
    # Verify if readable.
    fn_magic = migrate_tools.get_magic_data(imagepath)
    if fn_magic is None:
        exit_with_msg('*** ERROR *** An error occured while trying to read '
                      'magic number of File %s.' % imagepath)
    else:
        pause_msg('Image Magic Number: %s' % fn_magic)
        _logger.debug('Magic number %s successfully read' % fn_magic)
    #
    # Verify if image type is supported.
    _logger.debug('Magic number of %s is %s' % (imagepath, fn_magic))
    if fn_magic not in supported_formats:
        exit_with_msg('*** ERROR *** Image type %s is not recognised.' % fn_magic)
    else:
        _logger.debug('Image type recognised.')
    #
    # Get the correct class.
    imageclazz = supported_formats[fn_magic]
    migrate_tools.result_msg(msg='Type of image %s identified as %s'
                             % (imagepath, imageclazz['name']), result=True)
    pause_msg('Image type is %s' % imageclazz['name'])
    #
    # Locate the class and module
    imageclassdef = getattr(sys.modules['oci_utils.migrate.%s'
                                        % supported_formats[fn_magic]['name']],
                            imageclazz['clazz'])
    image_object = imageclassdef(imagepath)
    #
    # Generic data collection
    try:
        imgres, imagedata = collect_image_data(image_object)
        if verbose_flag:
            migrate_utils.show_image_data(image_object)
        if imgres:
            _logger.debug('Image processing succeeded.')
        else:
            _logger.critical('   Image processing failed.', exc_info=False)
        #
        if imagedata:
            _logger.debug('%s passed verification.' % imagepath)
        else:
            _logger.critical('   %s failed image check.' % imagepath, exc_info=False)
    except Exception as e:
        _logger.critical('   %s failed image check: %s' % (imagepath, str(e)))
        exit_with_msg('*** ERROR *** Problem detected during investigation of '
                      'the image %s: %s, exiting.' % (imagepath, str(e)))
    #
    # passed prerequisites and changes?
    prereq_passed = True
    #
    # Image type specific prerequisites
    prereq_msg = ''
    sup, msg = image_object.type_specific_prereq_test()
    if sup:
        migrate_tools.result_msg(msg='%s' % msg, result=True)
    else:
        prereq_passed = False
        prereq_msg = msg
    #
    # Generic prerequisites verification
    try:
        gen_prereq, msg = image_object.generic_prereq_check()
        if gen_prereq:
            prereq_msg += '\n  %s passed the generic preqrequisites.' % imagepath
        else:
            prereq_passed = False
            prereq_msg += msg
        #
        if imgres:
            prereq_msg += '\n\n  %s data collection and processing succeeded.' \
                      % imagepath
        else:
            prereq_passed = False
        #
        if prereq_passed:
            migrate_tools.result_msg(msg=prereq_msg, result=True)
            if imagedata['boot_type'] == 'BIOS':
                migrate_tools.result_msg(msg='\n  Boot type is BIOS, '
                                             'use launch_mode PARAVIRTUALIZED '
                                             '(or EMULATED) at import.',
                                         result=True)
            elif imagedata['boot_type'] == 'UEFI':
                migrate_tools.result_msg(msg='\n  Boot type is UEFI, '
                                             'use launch_mode EMULATED at '
                                             'import.', result=True)
            else:
                exit_with_msg('*** ERROR *** Something wrong checking the '
                              'boot type')
        else:
            prereq_msg += '\n\n  %s processing failed, check the logfile ' \
                          'and/or set environment variable _OCI_UTILS_DEBUG.' \
                          % imagepath
            raise OciMigrateException(prereq_msg)
    except Exception as e:
        exit_with_msg('*** ERROR ***  %s' % str(e))
    #
    # While prerequisite check did not hit a fatal issue, there might be
    # situations where upload should not proceed.
    if not migrate_tools.migrate_preparation:
        exit_with_msg('*** ERROR *** Unable to proceed with uploading image '
                      'to Oracle Cloud Infrastructure: %s'
                      % migrate_tools.migrate_non_upload_reason)
    #
    # Ask for agreement to proceed.
    if not read_yn('\n  Agree to proceed uploading %s to %s as %s?'
                   % (imagepath, bucket_name, output_name), waitenter=True):
        exit_with_msg('\n  Exiting.')
    #
    # Prerequisite verification and essential image updates passed, uploading
    # image.
    _, clmns = os.popen('stty size', 'r').read().split()
    try:
        uploadprogress = migrate_tools.ProgressBar(
            int(clmns), 0.2, progress_chars=['uploading %s' % output_name])
        #
        # Verify if object already exists.
        if migrate_utils.object_exists(bucket_data, output_name):
            raise OciMigrateException('Object %s already exists object '
                                      'storage %s.' % (output_name, bucket_name))
        else:
            _logger.debug('Object %s does not yet exists in object storage %s'
                          % (output_name, bucket_name))
        #
        # Upload the image.
        migrate_tools.result_msg(msg='\n  Uploading %s, this might take a while....'
                                 % imagepath, result=True)
        uploadprogress.start()
        uploadres = migrate_utils.upload_image(imagepath, bucket_name,
                                               output_name)
        _logger.debug('Uploadresult: %s' % uploadres)
        migrate_tools.result_msg(msg='  Finished....\n', result=True)
        uploadprogress.stop()
    except Exception as e:
        _logger.error('   Error while uploading %s to %s: %s.'
                      % (imagepath, bucket_name, str(e)))
        exit_with_msg('*** ERROR *** Error while uploading %s to %s: %s.'
                      % (imagepath, bucket_name, str(e)))
    finally:
        #
        # if progressthread was started, needs to be terminated.
        if migrate_tools.isthreadrunning(uploadprogress):
            uploadprogress.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
