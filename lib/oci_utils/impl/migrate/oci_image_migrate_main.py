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
import logging.config
import os
import re
import sys
import time

from oci_utils.migrate import error_msg
from oci_utils.migrate import exit_with_msg
from oci_utils.migrate import migrate_data
from oci_utils.migrate import migrate_tools
from oci_utils.migrate import pause_msg
from oci_utils.migrate import read_yn
from oci_utils.migrate import result_msg
from oci_utils.migrate import system_tools
from oci_utils.migrate.exception import OciMigrateException
from oci_utils.migrate.migrate_tools import get_config_data


_logger = logging.getLogger('oci-utils.oci-image-migrate')
#
# Dictionary containing utilities which might be needed with the packages
# which provide them.
try:
    helpers_list = get_config_data('helpers_list')
except Exception as e:
    exit_with_msg('Failed to retrieve the list of required utilities. Verify '
                  'the existence and contents of the configuration file '
                  'oci-migrate-conf.yaml: %s' % str(e))


def parse_args():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args())
    arguments:
     -i|--input-image <on-premise image>; mandatory.
     -y| --yes suppose the answer YES to all Y/N questions
     -v|--verbose produces verbose output.
     -h|--help

    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(
        prog='oci-image-migrate',
        description='Utility to support preparation of on-premise legacy '
                    'images for importing in the Oracle Cloud Infrastructure.')
    #
    parser.add_argument('-i', '--input-image',
                        action='store',
                        dest='input_image',
                        type=argparse.FileType('r'),
                        required=True,
                        help='The on-premise image for migration to OCI.')
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
    return args


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
    _logger.debug('__ Show found and missing utilities.')
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
    _logger.debug('__ Show supported image formats.')
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
    img_object: Qcow2Head, VmdkHead, TemplateTypeHead..  object
        The image object.

    Returns
    -------
        dict:
            The image data.
    """
    _logger.debug('__ Collect the image data.')
    try:
        res, img_info = img_object.image_data()
    except Exception as e:
        _logger.critical('   Unable to collect or invalid image data: %s', str(e), exc_info=True)
        raise OciMigrateException('Unable to collect or invalid image data.') from e
    #
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
    _logger.debug('__ Verify presence of utilities.')
    helpers = []
    missing = []
    path_env_var = os.getenv('PATH')
    _logger.debug('PATH is %s', path_env_var)
    for util, package in helpers_list.items():
        try:
            _logger.debug('Availability of %s', util)
            full_command = system_tools.exec_exists(util)
            _logger.debug('full path: %s', full_command)
            if system_tools.exec_exists(util) is not None:
                helpers.append(util)
            else:
                missing.append(util)
        except Exception as e:
            _logger.error('   %s is not found, verify presence of %s: %s', helpers_list[util], package, str(e))
    return helpers, missing


def qemu_img_version():
    """
    Retrieve the version of qemu-img.

    Returns:
    -------
        version_data: str
        version_nb: int
    """
    _logger.debug('__ Retrieve qemu-img release data.')
    cmd = ['qemu-img', '--version']
    cmd_dict = system_tools.run_popen_cmd(cmd)
    if bool(cmd_dict):
        version_string = cmd_dict['output'].decode('utf-8').splitlines()
    else:
        return -1
    ptrn = re.compile(r'[. -]')
    _logger.debug('qemu-img version: %s', version_string)
    for lin in version_string:
        if 'version' in lin:
            ver_elts = ptrn.split(lin)
            for elt in ver_elts:
                if elt.isnumeric():
                    return lin, int(elt)
    return 0


def get_os_release_data():
    """
    Collect information on the linux operating system and release.
    Currently is only able to handle linux type os.

    Returns
    -------
        ostype: str
            The os type
        major_release: str
            the major release
        dict: Dictionary containing the os and version data on success,
            None otherwise.
    """
    osdata = '/etc/os-release'
    try:
        with open(osdata, 'r') as f:
            osreleasedata = [line.strip() for line in f.read().splitlines() if '=' in line]
        osdict = dict([re.sub(r'"', '', kv).split('=') for kv in osreleasedata])
    except Exception as e:
        return None, None, None
    os_type = osdict['ID']
    major_release = re.split('\\.', osdict['VERSION_ID'])[0]

    return os_type, major_release, osdict


def verify_support():
    """
    Verify if the instance os and release are supported to run this code.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    ostype, majorrelease, _ = get_os_release_data()
    if ostype not in ['ol', 'redhat', 'centos']:
        _logger.info('OS type %s is not supported.', ostype)
        return False
    if majorrelease not in ['7', '8', '9']:
        _logger.info('OS %s %s is not supported', ostype, majorrelease)
        return False
    return True


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
    _logger.debug('Locale set to %s', lc_all_to_set)
    #
    # python version
    python_version = sys.version_info[0]
    _logger.debug('Python version is %s', python_version)
    #
    # parse the commandline
    args = parse_args()
    #
    # Operator needs to be root.
    if system_tools.is_root():
        _logger.debug('User is root.')
    else:
        exit_with_msg('  *** ERROR *** This program needs to be run with root privileges.')
    #
    # Verify if instance is supported to run this code.
    if not verify_support():
        sys.exit(1)
    #
    # Verbose mode is False by default
    migrate_data.verbose_flag = args.verbose_flag
    _logger.debug('Verbose level set to %s', migrate_data.verbose_flag)
    #
    # Yes flag
    migrate_data.yes_flag = args.yes_flag
    _logger.debug('Answer to yes/no questions supposed to be yes always.')
    #
    # collect and save configuration data
    migrate_data.oci_image_migrate_config = get_config_data('*')
    #
    try:
        #
        # input image
        if args.input_image:
            image_path = args.input_image.name
            result_filename = get_config_data('result_filepath') \
                              + '_' \
                              + os.path.splitext(os.path.basename(image_path))[0] \
                              + '.res'
            migrate_data.result_filename = result_filename
            result_msg(msg='\n  Running %s at %s\n' % ((os.path.basename(sys.argv[0])
                                                        + ' '
                                                        + ' '.join(sys.argv[1:])), time.ctime()),
                       flags='w', result=True)
        else:
            raise OciMigrateException('Missing argument: input image path.')
        #
        # Import the 'format' modules and collect the format data
        supported_formats = migrate_tools.import_formats()
        if not bool(supported_formats):
            exit_with_msg('  *** ERROR ***  No image format modules found')
        if migrate_data.verbose_flag:
            show_supported_formats_data(supported_formats)
        #
        # Check the utilities installed.
        util_list, missing_list = test_helpers()
        _logger.debug('%s', util_list)
        if migrate_data.verbose_flag:
            show_utilities(util_list, missing_list)
        if missing_list:
            raise OciMigrateException('%s needs packages %s installed.\n'
                                      % (sys.argv[0], missing_list))
        #
        # if qemu-img is used, the minimal version is 2
        qemu_version_info = qemu_img_version()
        if qemu_version_info[1] < 2:
            raise OciMigrateException('Minimal version of qemu-img is 2, '
                                      '%s found.' % qemu_version_info[0])
        _logger.debug('release data ok')
        #
        # Get the nameserver definition
        if system_tools.get_nameserver():
            result_msg(msg='nameserver %s identified.' % migrate_data.nameserver, result=False)
            _logger.debug('Nameserver identified as %s', migrate_data.nameserver)
        else:
            error_msg('Failed to identify nameserver, using %s, but might cause issues.' % migrate_data.nameserver)
    except Exception as e:
        _logger.error('*** ERROR *** %s\n', str(e))
        exit_with_msg('  *** ERROR *** %s\n' % str(e))
    #
    # More on command line arguments.
    #
    # initialise output
    result_msg(msg='Results are written to %s.' % migrate_data.result_filename, result=True)
    result_msg(msg='Input image:  %s' % image_path, result=True)
    #
    # Verify if readable.
    fn_magic = migrate_tools.get_magic_data(image_path)
    if fn_magic is None:
        exit_with_msg('*** ERROR *** An error occurred while trying to read '
                      'magic number of File %s.' % image_path)
    else:
        pause_msg('Image Magic Number: %s' % fn_magic)
        _logger.debug('Magic number %s successfully read', fn_magic)
    #
    # Verify if image type is supported.
    _logger.debug('Magic number of %s is %s', image_path, fn_magic)
    if fn_magic not in supported_formats:
        exit_with_msg('*** ERROR *** Image type %s is not recognised.' % fn_magic)
    else:
        _logger.debug('Image type recognised.')
    #
    # Get the correct class.
    image_clazz = supported_formats[fn_magic]
    result_msg(msg='Type of image %s identified as %s' % (image_path, image_clazz['name']), result=True)
    pause_msg('Image type is %s' % image_clazz['name'])
    #
    # Locate the class and module
    image_class_def = getattr(sys.modules['oci_utils.migrate.image_types.%s'
                                          % supported_formats[fn_magic]['name']], image_clazz['clazz'])
    image_object = image_class_def(image_path)
    #
    # Local volume groups.
    vgs_result = system_tools.exec_vgs_noheadings()
    migrate_data.local_volume_groups = vgs_result if bool(vgs_result) else []
    _logger.debug('Workstation volume groups: %s', migrate_data.local_volume_groups)
    #
    # Rename local volume groups
    if bool(migrate_data.local_volume_groups):
        rename_msg = '\n   The workstation has logical volumes defined. To avoid ' \
                     'duplicates, the \n   logical volume groups will be temporary' \
                     ' renamed to a hexadecimal uuid.\n   If you are sure the ' \
                     'image to be uploaded does not contain logical volumes,\n' \
                     '   or there are no conflicting volume group names, '\
                     'the rename can be skipped\n\n   Keep the volume group names?'
        if not read_yn(rename_msg,
                       waitenter=True,
                       suppose_yes=migrate_data.yes_flag):
            if migrate_tools.verify_local_fstab():
                fstab_msg = '\n   The fstab file on this workstation seems to ' \
                            'contain device references\n   using /dev/mapper ' \
                            'devices. The volume group names on this ' \
                            'workstation\n   will be renamed temporarily. ' \
                            '/dev/mapper devices referring to logical volumes\n' \
                            '   can create problems in this context. To avoid ' \
                            'this situation\n   exit now and modify the ' \
                            'device specification to LABEL or UUID.\n\n   Continue?'
                if not read_yn(fstab_msg,
                               waitenter=True,
                               suppose_yes=migrate_data.yes_flag):
                    exit_with_msg('Exiting.')
                _logger.debug('Rename local volume groups to avoid conflicts.')
                vgrename_res = system_tools.exec_rename_volume_groups(migrate_data.local_volume_groups, 'FORWARD')
                if not vgrename_res:
                    _logger.warning('Failed to rename local volume groups.')
                    if not read_yn('\n   Failed to rename the local volume groups. '
                                   'Continue on your own responsibility?',
                                   waitenter=True, suppose_yes=migrate_data.yes_flag):
                        exit_with_msg('Exiting.')
                migrate_data.local_volume_group_rename = True
            else:
                _logger.debug('fstab file has no /dev/mapper devices.')
        else:
            _logger.debug('Not renaming the volume groups.')
            _ = system_tools.reset_vg_list(migrate_data.local_volume_groups)
    else:
        _logger.debug('No local volume groups, no conflicts.')
    #
    # Generic data collection
    try:
        imgres, imagedata = collect_image_data(image_object)
        if migrate_data.verbose_flag:
            migrate_tools.show_image_data(image_object)
        if imgres:
            _logger.debug('Image processing succeeded.')
        else:
            _logger.critical('   Image processing failed.', exc_info=False)
        #
        if imagedata:
            _logger.debug('%s passed.', image_path)
        else:
            _logger.critical('   %s failed.', image_path, exc_info=False)
    except Exception as e:
        _logger.critical('   %s failed: %s', image_path, str(e))
        exit_with_msg('*** ERROR *** Problem detected during investigation of '
                      'the image %s: %s, exiting.' % (image_path, str(e)))
    #
    # Restore volume group names.
    if migrate_data.local_volume_group_rename:
        _logger.debug('Restore local volume groups.')
        vgrename_res = system_tools.exec_rename_volume_groups(migrate_data.local_volume_groups, 'BACKWARD')
        if not vgrename_res:
            _logger.warning('Failed to restore local volume group names.')
    else:
        _logger.debug('No local volume group names to restore.')
    #
    # passed prerequisites and changes?
    prereq_passed = True
    #
    # Image type specific prerequisites
    prereq_msg = ''
    sup, msg = image_object.type_specific_prereq_test()
    if sup:
        result_msg(msg='%s' % msg, result=True)
    else:
        prereq_passed = False
        prereq_msg = msg
    #
    # Generic prerequisites verification
    try:
        gen_prereq, msg = image_object.generic_prereq_check()
        if gen_prereq:
            prereq_msg += '\n  %s passed the generic preqrequisites.' % image_path
        else:
            prereq_passed = False
            prereq_msg += msg
        #
        if imgres:
            prereq_msg += '\n\n  %s data collection and processing succeeded.' % image_path
        else:
            prereq_passed = False
        #
        if prereq_passed:
            result_msg(msg=prereq_msg, result=True)
            if imagedata['boot_type'] == 'BIOS':
                result_msg(msg='\n  Boot type is BIOS, use launch_mode PARAVIRTUALIZED (or EMULATED) at import.',
                           result=True)
            elif imagedata['boot_type'] == 'UEFI':
                result_msg(msg='\n  Boot type is UEFI, use launch_mode NATIVE (or EMULATED) at import.',
                           result=True)
            else:
                raise OciMigrateException('Checking the boot type failed.')
        else:
            prereq_msg += '\n\n  %s processing failed, check the logfile and/or set environment variable ' \
                          '_OCI_UTILS_DEBUG.' % image_path
            raise OciMigrateException(prereq_msg)
    except Exception as e:
        exit_with_msg('*** ERROR ***  %s' % str(e))
    #
    # While prerequisite check did not hit a fatal issue, there might be
    # situations where upload should not proceed.
    if not migrate_data.migrate_preparation:
        exit_with_msg('*** ERROR *** Unable to proceed with uploading image '
                      'to Oracle Cloud Infrastructure: %s'
                      % migrate_data.migrate_non_upload_reason)
    else:
        result_msg('Successfully verified and processed image %s and is ready for upload.' % image_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
