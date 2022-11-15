#!/bin/python3
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import argparse
import errno
import getpass
import glob
import json
import logging
import os
import re
import sys
import termios
import tty
from datetime import date
from datetime import datetime
from subprocess import call

import oci

#
# locale
lc_all = 'en_US.UTF8'
#
# logfile
default_log = '/tmp/configure_image_%s.log' % datetime.now().strftime('%Y%m%d_%H%M')
#
# custom scripts
custom_kvm_build_scripts = ['custom_install.sh', 'custom_firstboot.sh', 'custom_post_install_task.sh']

_logger = logging.getLogger(__name__)


def print_g(msg, term=True, destination=default_log):
    """
    Write msg to stdout and to file.

    Parameters
    ----------
    msg: str
        The text.
    term: bool
        If true, write to stdout.
    destination: str
        Path of destination file.

    Returns
    -------
        No return value.
    """
    if term:
        print('%s' % msg)
    with open(destination, 'a') as f:
        f.write('%s\n' % msg)
        f.flush()


def parse_args():
    """
    Parse the command line arguments.
    -p | --profile <profile in the cli/sdk config file>
    -c | --config <path of config file>
    -d | --data-directory <path of data directory>
    -f | --var-file <path of json file with results>
    -t | --type [OL|AL]

    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(description='Configure Oracle Linux KVM image build.')
    parser.add_argument('-p', '--profile',
                        action='store',
                        dest='profile',
                        default='DEFAULT',
                        help='The profile in the cli/sdk config file, default is DEFAULT.')
    parser.add_argument('-c', '--config',
                        action='store',
                        dest='configfile',
                        default='~/.oci/config',
                        help='The cli/sdk config file, default is ~/.oci/config.')
    parser.add_argument('-d', '--data-directory',
                        action='store',
                        dest='datadir',
                        default='~/imagebuild/data',
                        help='Root directory with data for the image build, default is ~/imagebuild/data.')
    parser.add_argument('-f', '--var-file',
                        action='store',
                        dest='varfilename',
                        default='image_vars',
                        help='Filename to store the variables; the extension .tfvars.json is added automatically.')
    parser.add_argument('-t', '--type',
                        action='store',
                        choices=['OL', 'AL'],
                        dest='oltype',
                        help='Build Oracle Linux or Autonomous Linux, mandatory.',
                        required=True)
    parser.add_argument('-r', '--release',
                        action='store',
                        choices=['7', '8'],
                        dest='olrelease',
                        help='Build OL7 or OL8 release, mandatory.',
                        required=True)
    parser._optionals.title = 'Arguments'
    args = parser.parse_args()
    return args


def _clear_term():
    """
    Clears the terminal window.

    Returns
    -------
        No return value.
    """
    _ = call('clear' if os.name == 'posix' else 'cls')
    return True


def _getch():
    """
    Read a single keypress from stdin.

    Returns
    -------
        The resulting character.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def _read_yn(prompt, yn=True, waitenter=False, suppose_yes=False, default_yn=False):
    """
    Read yes or no form stdin, No being the default.

    Parameters
    ----------
        prompt: str
            The message.
        yn: bool
            Add (y/N) to the prompt if True.
        waitenter: bool
            Wait for the enter key pressed if True, proceed immediately
            otherwise.
        suppose_yes: bool
            if True, consider the answer is yes.
        default_yn: bool
            The default answer.
    Returns
    -------
        bool: True on yes, False otherwise.
    """
    yn_prompt = prompt + ' '
    #
    # if yes is supposed, write prompt and return True.
    if suppose_yes:
        _ = sys.stdout.write(yn_prompt)
        sys.stdout.flush()
        return True
    #
    # add y/N to prompt if necessary.
    if yn:
        if default_yn:
            yn_prompt += ' (Y/n)'
            yn = 'Y'
        else:
            yn_prompt += ' (y/N) '
            yn = 'N'
    #
    # if wait is set, wait for return key.
    if waitenter:
        resp_len = 0
        while resp_len == 0:
            resp = input(yn_prompt).lstrip()
            resp_len = len(resp)
        yn_i = list(resp)[0].rstrip()
    #
    # if wait is not set, proceed on any key pressed.
    else:
        _ = sys.stdout.write(yn_prompt)
        sys.stdout.flush()
        yn_i = _getch().rstrip()

    sys.stdout.write('\n')
    if bool(yn_i):
        yn = yn_i
    return bool(yn.upper() == 'Y')


def _is_int(string_data):
    """
    Verifies if string is a valid int.

    Parameters
    ----------
    string_data: str
        The string to be evaluated.

    Returns
    -------
        bool: True on success, false otherwise.
    """
    return re.match(r"[-+]?\d+$", string_data) is not None


def _get_current_user():
    """
    Get the current username.

    Returns
    -------
        str: the username.
    """
    return getpass.getuser()


def _get_current_user_home():
    """
    Get the home directory of the current user.

    Returns
    -------
        str: the full path of the home directory.
    """
    return os.path.expanduser('~')


def _from_stdin(prompt, default=None):
    """
    Read from stdin, if default is not set to None, some input is expected.

    Parameters
    ----------
    prompt: str
        The stdin prompt.
    default:
        Default value.

    Returns
    -------
        value read
    """
    while True:
        return_val = input('%-40s: ' % prompt)
        if bool(return_val):
            return return_val
        if default is not None:
            return default


def get_configdata(profile, configfile='~/.oci/config'):
    """
    Read the oci sdk/cli config file.

    Parameters
    ----------
        profile: str
            the config profile.
        configfile: str
            the path of the configfile.
    Returns
    -------
        code: int 0 for success, 1 for failure
        dict: the config data.
    """
    sdkconfigfile = configfile
    if configfile.startswith('~/'):
        sdkconfigfile = os.path.expanduser('~') + configfile[1:]
    if os.path.exists(sdkconfigfile):
        try:
            return 0, oci.config.from_file(file_location=sdkconfigfile, profile_name=profile)
        except Exception as e:
            exit_msg = str(e)
    else:
        exit_msg = '%s does not exist' % sdkconfigfile
    return 1, exit_msg


def _select_from(some_list, prompt, default_val=0):
    """
    Select an item from a list.

    Parameters
    ----------
    some_list: list
        list of items.
    prompt: str
        prompt
    default_val: int
        default index value if no input.

    Returns
    -------
        The list element.
    """
    while 1 == 1:
        selected_nb = input("%s ==> " % prompt)
        if not bool(selected_nb):
            selected_nb = str(default_val)
        if _is_int(selected_nb):
            select_index = int(selected_nb)
            if 0 <= select_index < len(some_list):
                break
            print_g('Index %d out of range.' % select_index)
        else:
            print_g('Invalid input: %s' % selected_nb)
    _logger.debug('Selected %s', some_list[select_index])
    return some_list[select_index]


def this_path(this_file=None):
    """
    Root of the operation.

    Parameters
    ----------
    this_file: str
       Filename, default is this script location.

    Returns
    -------
        str: path
    """
    exec_dir = os.path.dirname(os.path.realpath(sys.argv[0] or 'whocares'))
    return exec_dir if not this_file else os.path.join(exec_dir, this_file)


def _get_today():
    """
    Get todays date as a sting in YYYY.MM.DD format

    Returns
    -------
       str: today in requested format.

    """
    return date.today().strftime("%Y.%m.%d")


def _get_timestamp():
    """
    Get timestamp as a string in YYYYMMDD-HHMISS format.

    Returns
    -------
        str: timestamp in requested format.
    """
    return datetime.now().strftime('%Y%m%d-%H%M%S')


def select_compartment_id(config_dict, prompt):
    """
    Select a compartment in the tenancy.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.

    prompt: str
        The prompt
    Returns
    -------
        str: the compartment ocid.
    """
    try:
        oci_identity = oci.identity.IdentityClient(config_dict)
        oci_compartments = oci.pagination.list_call_get_all_results(oci_identity.list_compartments, config_dict['tenancy'])
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for comp in oci_compartments.data:
        print_g('%4d %-30s %s' % (oci_compartments.data.index(comp), comp.name, comp.id))
    compartment_data = _select_from(oci_compartments.data, prompt)
    print_g(compartment_data, term=False)
    print_g(msg='Selected compartment:\n%30s: %s' % (compartment_data.name, compartment_data.id))
    return compartment_data.id


def select_availability_domain_name(config_dict, compartment_id, prompt):
    """
    Select an availability domain.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    compartment_id: str
        The compartment ocid
    prompt: str
        The prompt

    Returns
    -------
        str: the availability domain name
    """
    try:
        oci_identity = oci.identity.IdentityClient(config_dict)
        oci_availabitly_domains = oci.pagination.list_call_get_all_results(oci_identity.list_availability_domains, compartment_id)
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        _logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for domain in oci_availabitly_domains.data:
        print_g('%4d %-30s %s' % (oci_availabitly_domains.data.index(domain), domain.name, domain.id))
    availability_domain = _select_from(oci_availabitly_domains.data, prompt)
    print_g(availability_domain, term=False)
    print_g('Selected availability domain: \n%30s' % availability_domain.name)
    return availability_domain.name


def select_image_id(config_dict, compartment_id, prompt):
    """
    Select an image.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    compartment_id: str
        The compartment ocid
    prompt: str
        The prompt

    Returns
    -------
        str: the image ocid
    """
    try:
        oci_imageclient = oci.core.ComputeClient(config_dict)
        # oci_images = oci_imageclient.list_images(compartment_id, operating_system='Oracle Linux')
        # oci_images = oci_imageclient.list_images(compartment_id, limit=500)
        oci_images_data = oci.pagination.list_call_get_all_results(oci_imageclient.list_images, compartment_id, operating_system='Zero').data
        oci_images_data += oci.pagination.list_call_get_all_results(oci_imageclient.list_images, compartment_id, operating_system='Custom').data
        oci_images_data += oci.pagination.list_call_get_all_results(oci_imageclient.list_images, compartment_id, operating_system='Oracle Linux').data
        oci_images_data += oci.pagination.list_call_get_all_results(oci_imageclient.list_images, compartment_id, operating_system='Oracle Autonomous Linux').data
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        _logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for image in oci_images_data:
        # print_g('%4d %-30s %s' % (oci_images.data.index(image), image.display_name, image.id))
        # print_g('%4d %-30s %s %s' % (oci_images.data.index(image), image.display_name, image.operating_system, image.id))
        print_g('%4d %-40s %s' % (oci_images_data.index(image), image.display_name, image.operating_system))
    image_data = _select_from(oci_images_data, prompt)
    print_g(image_data, term=False)
    print_g('Selected image: \n%30s: %s' % (image_data.display_name, image_data.id))
    return image_data.id


def select_vcn_id(config_dict, compartment_id, prompt):
    """
    Select a VCN.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    compartment_id: str
        The compartment ocid
    prompt: str
        The prompt

    Returns
    -------
        str: the VCN ocid
    """
    try:
        oci_vncclient = oci.core.VirtualNetworkClient(config_dict)
        oci_vcns = oci.pagination.list_call_get_all_results(oci_vncclient.list_vcns, compartment_id)
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        _logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for vcn in oci_vcns.data:
        print_g('%4d %-30s %s' % (oci_vcns.data.index(vcn), vcn.display_name, vcn.id))
    vcn = _select_from(oci_vcns.data, prompt)
    print_g(vcn, term=False)
    print_g('Selected VCN: \n%30s: %s' % (vcn.display_name, vcn.id))
    return vcn.id


def select_subnet_id(config_dict, compartment_id, vcn_id, prompt):
    """
    Select a subnet.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    compartment_id: str
        The compartment ocid
    vcn_id: str
        The VCN ocid
    prompt: str
        The prompt

    Returns
    -------
        str: the subnet ocid
    """
    try:
        oci_subnetclient = oci.core.VirtualNetworkClient(config_dict)
        oci_subnets = oci.pagination.list_call_get_all_results(oci_subnetclient.list_subnets, compartment_id, vcn_id=vcn_id)
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        _logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for subnet in oci_subnets.data:
        print_g('%4d %-30s %s' % (oci_subnets.data.index(subnet), subnet.display_name, subnet.id))
    subnet = _select_from(oci_subnets.data, prompt)
    print_g(subnet, term=False)
    print_g('Selected subnet: \n%30s: %s' % (subnet.display_name, subnet.id))
    return subnet.id


def select_shape(config_dict, image_ocid, prompt):
    """
    Select a compatible shape for the image.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    image_ocid: str
        The ocid of the image.
    prompt: str
        The prompt.

    Returns
    -------
        str: The shape
    """
    try:
        oci_imageclient = oci.core.ComputeClient(config_dict)
        oci_shapes = oci.pagination.list_call_get_all_results(oci_imageclient.list_image_shape_compatibility_entries, image_ocid)
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        _logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    while 1 == 1:
        for shape_dict in oci_shapes.data:
            print_g('%4d %-30s' % (oci_shapes.data.index(shape_dict), shape_dict.shape))
        shape = _select_from(oci_shapes.data, prompt)
        #
        # is shape Flex?
        if bool(re.search('Flex', shape.shape)):
            print_g('*** Flex shapes are not supported here.')
            _ = sys.stdout.write('Press Key to continue.')
            sys.stdout.flush()
            _ = _getch().rstrip()
        else:
            break

    print_g(shape, term=False)
    print_g('Selected shape: \n%30s' % shape.shape)
    return shape.shape


def get_image_name_prefix():
    """
    Get the image name prefix.

    Returns
    -------
        str: the prefix.
    """
    while 1 == 1:
        try:
            image_prefix = input('Provide image name prefix:> ').strip()
            if len(image_prefix) > 0:
                return image_prefix
        except Exception as e:
            _logger.debug('Failed to read image name prefix, retry.')


def get_OL_version():
    """
    Get the Oracle Linux version from prompt.

    Returns
    -------
        str: the version.
    """
    while 1 == 1:
        try:
            ol_version = input('Provide Oracle Linux version used:> ').strip()
            if len(ol_version) > 0:
                return ol_version
        except Exception as e:
            _logger.debug('Failed to read Oracle Linux version.')


def collect_build_parameters(config_data):
    """
    Callect the data from oci required by packer to build the image.

    Parameters
    ----------
    config_data: dict
        The oci configuration file data.
    Returns
    -------
        dict: the data.
    """
    #
    # initialise data structure
    image_data = dict()
    #
    # Compartment ocid
    print_g('Instance Compartment.\n')
    image_data['user_compartment_ocid'] \
        = select_compartment_id(config_data, 'Select instance compartment.')
    _clear_term()
    #
    # Network compartment ocid
    print_g('Network Compartment.\n')
    image_data['user_network_compartment_ocid'] \
        = select_compartment_id(config_data,
                                'Select network compartment.')
    _clear_term()
    #
    # Virtual cloud network ocid
    print_g('Virtual Cloud Network.\n')
    image_data['user_vcn_ocid'] \
        = select_vcn_id(config_data,
                        image_data['user_network_compartment_ocid'],
                        'Select virtual cloud network.')
    _clear_term()
    #
    # Subnet ocid
    print_g('Subnet.\n')
    image_data['user_subnet_ocid'] \
        = select_subnet_id(config_data,
                           image_data['user_network_compartment_ocid'],
                           image_data['user_vcn_ocid'], 'Select subnet.')
    _clear_term()
    #
    # Image ocid
    print_g('Image.\n')
    image_data['user_base_image_ocid'] \
        = select_image_id(config_data,
                          image_data['user_compartment_ocid'],
                          'Select image.')
    _clear_term()
    #
    # Availability domain
    print_g('Availabiltiy Domain.\n')
    image_data['user_availability_domain'] \
        = select_availability_domain_name(config_data,
                                          image_data['user_compartment_ocid'],
                                          'Select availability domain.')
    _clear_term()
    #
    # Shape
    print_g('Shape.\n')
    image_data['user_shape_name'] \
        = select_shape(config_data, image_data['user_base_image_ocid'], 'Select shape')
    _clear_term()
    #
    # OL version
    print_g('OL version.\n')
    image_data['user_OL_version'] = get_OL_version()
    _clear_term()

    return image_data


def collect_instance_parameters(image_data, ol_type, ol_release):
    """
    Callect the data from the operator required by packer to build the image.

    Parameters
    ----------
    image_data: dict
        The current data.
    ol_type: str
        [OL | AL]
    ol_release: str
        [7 | 8]
    Returns
    -------
        dict: the updated data.
    """
    #
    # date strings
    today_date_str = _get_today()
    # print_g(msg='Today string: %s' % today_date_str)
    today_timestamp = _get_timestamp()
    # print_g(msg='Timestamp:    %s' % today_timestamp)
    #
    # flavor
    image_data['user_flavor'] = 'Autonomous' if ol_type == 'AL' else 'NonAutonomous'
    print_g(msg='Flavor: %s' % image_data['user_flavor'])
    #
    # image name
    release_part = '-07-KVM-' + today_date_str if ol_release == '7' else '-08-KVM-' + today_date_str
    image_data['user_image_name'] = 'AL' + release_part if ol_type == 'AL' else 'OL' + release_part
    print_g(msg='Image name: %s' % image_data['user_image_name'])
    #
    # instance name
    release_part = '-07-KVM-builder' + today_timestamp if ol_release == '7' else '-08-KVM-builder' + today_timestamp
    image_data['user_instance_name'] = 'AL' + release_part if ol_type == 'AL' else 'OL' + release_part
    print_g(msg='Instance name: %s' % image_data['user_instance_name'])

    return image_data


def build_data(image_data, dir_root):
    """
    Add data necessary for the build.
    Parameters
    ----------
    image_data: dict
       The current data.
    dir_root: str
       The root dir to start looking for the custom scripts.
    Returns
    -------
        dict: the updated data.
    """
    #
    # look in directory tree for the custom_*sh scripts
    cs_path = None
    for custom_script in custom_kvm_build_scripts:
        cs_path = glob.glob(dir_root + '/**/%s' % custom_script, recursive=True)
        if bool(cs_path):
            print_g(msg='script %s' % cs_path)
            script_name = os.path.basename(custom_script)
            script_base = os.path.splitext(script_name)[0]
            image_data['user_' + script_base] = script_name
            image_data['user_' + script_base + '_path'] = cs_path[0]
        cs_path = None
    return image_data


def show_parameters(data):
    """
    Show collected data.

    Parameters
    ----------
    data: dict
        The data.

    Returns
    -------
        No return value.
    """
    _clear_term()
    print('Data collected to build an image:\n')
    for k, v in data.items():
        print('%40s: %s' % (k, v))
    print('\n')


def main():
    """
    Configure auto tests.

    Returns
    -------
       int: 0 on success, raises exception on failure.
    """
    logging.basicConfig(filename='/tmp/oci_utils_configure_image.log', level=logging.DEBUG)
    #
    # parse the commandline
    args = parse_args()
    #
    # init log
    try:
        with open(default_log, 'w') as f:
            f.write('')
            f.flush()
            print_g(msg='Log file %s initialised.' % default_log, term=True)
    except Exception as e:
        _logger.error('Failed to initialise log file %s: %s', default_log, str(e))
        sys.exit(1)
    #
    # current user
    operator = _get_current_user()
    operator_home = _get_current_user_home()
    _clear_term()
    print_g(msg='%30s: %s\n%30s: %s' % ('Username', operator, 'Home', operator_home), term=True)
    #
    # date strings
    # today_date_str = _get_today()
    # print_g(msg='Today string: %s' % today_date_str)
    # today_timestamp = _get_timestamp()
    # print_g(msg='Timestamp:    %s' % today_timestamp)
    #
    # parse the commandline
    args = parse_args()
    #
    # get configuration data
    ret, configuration = get_configdata(args.profile, args.configfile)
    if ret == 1:
        _logger.error('Failed to read config file %s', args.configfile)
        print_g('*** ERROR *** %s' % configuration)
        sys.exit(1)

    print_g(msg='Configuration', term=True)
    for k, v in configuration.items():
        print_g(msg='%30s: %s' % (k, v), term=True)
    #
    # continue?
    resp = _read_yn(prompt='Continue?', yn=True, default_yn=True)
    if not resp:
        sys.exit('Exiting.')
    else:
        _clear_term()
    #
    # data from oci
    image_data = collect_build_parameters(configuration)
    #
    # data from operator
    image_data = collect_instance_parameters(image_data, args.oltype, args.olrelease)
    #
    # data for build
    image_data = build_data(image_data, operator_home)
    #
    # packer var file, create dir if not exits.
    data_dir = operator_home + '/imagebuild_data' if args.datadir.startswith('~') else args.datadir
    # tfvarsfile = data_dir + '/' + args.varfilename + '_' + image_data['user_image_name'] + '.tfvars.json'
    tfvarsfile = data_dir + '/' + args.varfilename + '.tfvars.json'
    try:
        os.makedirs(os.path.dirname(tfvarsfile))
    except OSError as e:
        if e.errno != errno.EEXIST:
            sys.exit('Failed to create directory %s: %s' % (os.path.dirname(tfvarsfile), str(e)))
    print_g(msg='%30s: %s' % ('Packer var file', tfvarsfile), term=True)
    #
    # validate
    show_parameters(image_data)
    resp = _read_yn('Proceed with this data?')
    if not resp:
        sys.exit('Data not saved, terminating.')
    print('Saving data in %s' % tfvarsfile)
    #
    # save data
    try:
        with open(tfvarsfile, 'w') as tfvj:
            json.dump(image_data, tfvj, indent=4)
        return 0
    except Exception as e:
        raise Exception('Failed to write %s:' % tfvarsfile) from e


if __name__ == "__main__":
    sys.exit(main())
