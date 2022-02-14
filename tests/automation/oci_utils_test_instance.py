#!/bin/python3
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import argparse
import errno
import getpass
import inspect
import json
import logging
import os
import re
import shutil
import socket
import sys
import termios
import tty
from datetime import datetime
from subprocess import call

import oci

#
# locale
lc_all = 'en_US.UTF8'

software_tree = 'git_repo'
logdir = 'logs'
autotestdir = 'autotests'
tfvars_file = 'instance_variables'
default_log = 'instance_config.log'
config_log = ''

default_values = {
    "os_user": "whocares",
    "os_user_home": "whocares",
    "auth": "whocares",
    "user_ocid": "whocares",
    "server_ip": "whocares",
    "fingerprint": "whocares",
    "oci_private_key": "whocares",
    "tenancy_ocid": "whocares",
    "region": "whocares",
    "ssh_public_key": "whocares",
    "ssh_private_key": "whocares",
    "compartment_ocid": "whocares",
    "source_ocid": "whocares",
    "subnet_ocid": "whocares",
#    "vcn_ocid": "whocares",
#    "network_compartment_ocid": "whocares",
    "vnic_display_name": "whocares",
    "availability_domain": "whocares",
    "instance_display_name": "whocares",
    "shape": "whocares",
#    "authentication": "whocares",
    "source_type": "whocares",
    "remote_user": "whocares",
#    "autotest_root": "whocares",
    "log_file_path": "/logs",
    "script_path": "whocares",
#    "dns_search_domains" : ".oracle.com",
#    "dns_server_ip" : "100.110.7.250",
#    "http_proxy_url": "http://www-proxy-hqdc.us.oracle.com:80",
#    "https_proxy_url": "http://www-proxy-hqdc.us.oracle.com:80",
#    "http_no_proxy": "169.254.169.254,.oraclecloud.com,.oraclecorp.com,.us.oracle.com"
}

_logger = logging.getLogger(__name__)


def print_g(msg, term=True, destination=None):
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
    if not bool(destination):
        destination = config_log
    with open(destination, 'a') as f:
        f.write('%s\n' % msg)
        f.flush()


def print_g40(head, msg, term=True, destination=None):
    """
    Write a message %40s: msg to stdout and file.

    Parameters
    ----------
    head: str
        The head.
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
    print_g('%40s: %s' % (head, msg), term, destination)


def parse_args():
    """
    Parse the command line arguments.

    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(description='Configure oci utils auto test instance.')
    parser.add_argument('-n', '--name',
                        action='store',
                        dest='display_name',
                        help='The display name of the instance to create. There is no default, '
                             'if not provided, the script asks for it.')
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
                        default='_DDDD_',
                        help='Root directory with data for auto test run, default is ~/<display_name>/data.')
    parser.add_argument('-f', '--var-file',
                        action='store',
                        dest='varfilename',
                        default=tfvars_file,
                        help='filename to store the variables; the extension .tfvars.json is added automatically.')
    parser._optionals.title = 'Arguments'
    args = parser.parse_args()
    return args


def _clear():
    """
    Clear screen.

    Returns
    -------
        bool: True
    """
    _ = call('clear' if os.name == 'posix' else 'cls')
    return True


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


def initialise_log(base_dir, *args):
    """
    Initialise the logfile.

    Parameters
    ----------
    base_dir: str
        Path of the log directory.
    args: tuple
        Log file path base.

    Returns
    -------
        str: full path of the log file.
    """
    now = datetime.now()
    log_path = base_dir
    for dirfrag in list(args):
        log_path = os.path.join(log_path, dirfrag)
    os.makedirs(log_path, exist_ok=True)
    global config_log
    config_log = os.path.join(log_path, default_log + '_' + now.strftime('%Y%m%d%H%M'))
    with open(config_log, 'w') as f:
        f.write('')
        f.flush()
    return config_log


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


def _test_softwaretree_defined(root_dir):
    """
    Verify if software_tree is defined.

    Parameters
    ----------
    root_dir: str
        user home directory

    Returns
    -------
        bool: True on success, False otherwise.
    """
    return os.path.isdir(os.path.join(root_dir, software_tree))


def _create_dir(dirname, backup=False):
    """
    Create a directory, make a backup copy if already exists.

    Parameters
    ----------
    dirname: str
        Full path
    backup: bool
        If True, make a backup if already exists.
    Returns
    -------
        bool: True on success, false otherwise.
    """
    try:
        if backup:
            if os.path.exists(dirname):
                bck_name = dirname + '_%s' % datetime.now().strftime('%Y%m%d_%H%M')
                os.rename(dirname, bck_name)
                print_g('Renamed %s to %s' % (dirname, bck_name), term=False)
        os.makedirs(dirname)
        _logger.debug('Created %s', dirname)
    except OSError as e:
        if e.errno != errno.EEXIST:
            print_g('Failed to create %s' % dirname, term=False)
            return False
        _logger.warning('%s already exists, might cause problems.', dirname)
    return True


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
        dict: the config data.
    """
    sdkconfigfile = configfile
    if configfile.startswith('~/'):
        sdkconfigfile = os.path.expanduser('~') + configfile[1:]
    config = oci.config.from_file(file_location=sdkconfigfile, profile_name=profile)
    return config


class autotesttfvars:
    """
    Manipulate the tfvar.json file.
    """
    def __init__(self, tfvars_file):
        """
        Initialise.

        Parameters
        ----------
        tfvars_file: str
            Full path of the tfvar.json file.
        # sdkconfig: dict
        #     Contents of the sdk config file.
        """
        self.json_file = tfvars_file
        # self.sdkconfig = sdkconfig
        try:
            with open(self.json_file, 'rb') as tfvj:
                self.jsondata = json.load(tfvj)
                print_g40('Parameters', 'read %s' % self.json_file)
        except Exception as e:
            #
            # Failed to read variable def file, falling back to idle defaults.
            # print_g('Failed to read %s, Creating default' % self.json_file)
            print_g40('Parameters', 'created %s from default' % self.json_file)
            self.jsondata = default_values

    def __enter__(self):
        return self

    def __exit__(self, xtype, value, traceback):
        try:
            with open(self.json_file, 'w') as tfvj:
                json.dump(self.jsondata, tfvj, indent=4)
            return True
        except Exception as e:
            raise Exception('Failed to write %s:' % self.json_file) from e

    def update_json_with_config(self, sdk_config):
        """
        Update tf.json file with .oci/config data.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        print_g('')
        print_g40('Collecting data from sdk config file:', '')
        self.jsondata['user_ocid'] = sdk_config['user']
        print_g40('user ocid', sdk_config['user'])
        self.jsondata['fingerprint'] = sdk_config['fingerprint']
        print_g40('fingerprint', sdk_config['fingerprint'])
        self.jsondata['oci_private_key'] = sdk_config['key_file']
        print_g40('oci_private_key', sdk_config['key_file'])
        self.jsondata['tenancy_ocid'] = sdk_config['tenancy']
        print_g40('tenancy_ocid', sdk_config['tenancy'])
        self.jsondata['region'] = sdk_config['region']
        print_g40('region', sdk_config['region'])
        if _read_yn('Agree?', default_yn=True):
            return True
        return False

    def update_user(self):
        """
        Update tf.json file with user related data.

        Returns
        -------
           bool: True on success, False otherwise.
        """
        #
        # os user data
        current_user = _get_current_user()
        if bool(self.jsondata['os_user']):
            if _read_yn('\nReplace %s by %s' % (self.jsondata['os_user'], current_user), default_yn=True):
                self.jsondata['os_user'] = current_user
        else:
            self.jsondata['os_user'] = _from_stdin('os user', default=current_user)

        current_user_home = _get_current_user_home()
        if bool(self.jsondata['os_user_home']):
            if _read_yn('Replace %s by %s' % (self.jsondata['os_user_home'], current_user_home), default_yn=True):
                self.jsondata['os_user_home'] = current_user_home
        else:
            self.jsondata['os_user_home'] = _from_stdin('os user home', default=current_user_home)
        #
        # ssh keys
        pub_key = current_user_home + '/.ssh/id_rsa.pub'
        if bool(self.jsondata['ssh_public_key']):
            if _read_yn('Replace %s by %s' % (self.jsondata['ssh_public_key'], pub_key), default_yn=True):
                self.jsondata["ssh_public_key"] = pub_key
        else:
            self.jsondata['ssh_public_key'] = _from_stdin('ssh public key', default=pub_key)
        priv_key = current_user_home + '/.ssh/id_rsa'
        if bool(self.jsondata['ssh_private_key']):
            if _read_yn('Replace %s by %s' % (self.jsondata['ssh_private_key'], priv_key), default_yn=True):
                self.jsondata["ssh_private_key"] = priv_key
        else:
            self.jsondata['ssh_private_key'] = _from_stdin('ssh private key', default=priv_key)
        #
        # ip V4 address
        thisipv4 = socket.gethostbyname(socket.gethostname())
        if bool(self.jsondata['server_ip']):
            if _read_yn('Replace %s by %s' % (self.jsondata['server_ip'], thisipv4), default_yn=True):
                self.jsondata['server_ip'] = thisipv4
        else:
            self.jsondata['server_ip'] = _from_stdin('server ip address', default=thisipv4)
        return True

    def update_image(self, image_data):
        """
        Update tf.json file with image related data.

        Parameters
        ----------
        image_data: dict
            The image data

        Returns
        -------
            bool: True on success, False otherwise.
        """
        print_g(image_data)
        for k, v in image_data.items():
            print_g('%30s %s' % (k, v))
            self.jsondata[k] = v

        return True

    def update_varia(self, variadata):
        """
        Update various data.

        Parameters
        ----------
        variadata: dict
            The various data.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        for var_key, var_val in variadata.items():
            print_g40(var_key, var_val)
            self.jsondata[var_key] = _get_string('%s' % var_key)
        return True

    def update_gen_data(self, gendata):
        """
        Update tf.json with generic data.

        Parameters
        ----------
        gendata: dict
            The generic data.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        for var_key, var_val in gendata.items():
            self.jsondata[var_key] = var_val
        return True


def _read_nb(prompt, min_val=1, max_val=64, default_val=1):
    """
    Read an integer number from stdin.

    Parameters
    ----------
    prompt: str
        prompt
    min_val: int
        the smallest possible value.
    max_val: int
        the largest possible value.
    default_val: int
        default value if no input.

    Returns
    -------
        int: the number.
    """
    while 1 == 1:
        read_nb = input("%s ==> " % prompt)
        if not bool(read_nb):
            read_nb = int(default_val)
        if _is_int(read_nb):
            rread_nb = int(read_nb)
            if min_val <= rread_nb <= max_val:
                break
            print_g('Value %d out of range.' % rread_nb)
        else:
            print_g('Invalid input: %s' % read_nb)
    _logger.debug('Value read from stdin: %d' % rread_nb)
    return rread_nb


def select_compartment(config_dict, prompt):
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
        dict: the data of the compartment.
    """
    try:
        oci_identity = oci.identity.IdentityClient(config_dict)
        oci_compartments = oci_identity.list_compartments(config_dict['tenancy'])
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for comp in oci_compartments.data:
        print_g('%4d %-30s %s' % (oci_compartments.data.index(comp), comp.name, comp.id))
    return _select_from(oci_compartments.data, prompt)


def get_compartment(config_dict, prompt):
    """
    Get compartment ocid in a loop.

    Parameters
    ----------
    config_dict dict
        The oci configuration file data.

    prompt: str
        The prompt

    Returns
    -------
        str: the ocid of the compartment.
    """
    yn = False
    _clear()
    while not yn:
        compartment = select_compartment(config_dict, prompt)
        print_g(compartment, term=False)
        print_g('Selected compartment: %s\n' % compartment.name)
        yn = _read_yn('Continue?', default_yn=True)
    return compartment.id


def select_vcn(config_dict, compartment_id):
    """
    Select a VCN.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    compartment_id: str
        The compartment ocid

    Returns
    -------
        dict: the VCN
    """
    try:
        oci_vncclient = oci.core.VirtualNetworkClient(config_dict)
        oci_vcns = oci_vncclient.list_vcns(compartment_id)
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
    return _select_from(oci_vcns.data, 'Select VCN for instance.')


def get_vcn(config_dict, comp_id):
    """
    Get the vcn id in a loop.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    comp_id: str
        The network compartment ocid

    Returns
    -------
        str: the vcn id
    """
    yn = False
    _clear()
    while not yn:
        vcn = select_vcn(config_dict, comp_id)
        print_g(vcn, term=False)
        print_g('Selected VCN: %s\n' % vcn.display_name)
        yn = _read_yn('Continue?', default_yn=True)
    return vcn.id


def select_subnet(config_dict, compartment_id, vcn_id):
    """
    Select a subnet.

    Parameters¶
    ----------
    config_dict: dict
        The oci configuration file data.
    compartment_id: str
        The network compartment ocid

    Returns
    -------
        dict: the subnet
    """
    try:
        oci_subnetclient = oci.core.VirtualNetworkClient(config_dict)
        oci_subnets = oci_subnetclient.list_subnets(compartment_id, vcn_id=vcn_id)
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
    return _select_from(oci_subnets.data, 'Select subnet instance.')


def get_subnet(config_dict, comp_id, vcn_id):
    """
    Get the subnet id in a loop.
    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    comp_id: str
        The network compartment ocid.
    vcn_id: str
        The vcn ocid.

    Returns
    -------
        str: the subnet id.
    """
    yn = False
    _clear()
    while not yn:
        subnet = select_subnet(config_dict, comp_id, vcn_id)
        print_g(subnet, term=False)
        print_g('Selected subnet: %s\n' % subnet.display_name)
        yn = _read_yn('Continue?', default_yn=True)
    return subnet.id


def select_image(config_dict, compartment_id):
    """
    Select an image.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    compartment_id: str
        The compartment ocid

    Returns
    -------
        dict: the image
    """
    try:
        oci_imageclient = oci.core.ComputeClient(config_dict)
        # oci_images_data = oci.pagination.list_call_get_all_results(oci_imageclient.list_images,
        #                                                            compartment_id).data

        oci_images_data = oci.pagination.list_call_get_all_results(oci_imageclient.list_images,
                                                                   compartment_id,
                                                                   operating_system='Zero').data
        oci_images_data += oci.pagination.list_call_get_all_results(oci_imageclient.list_images,
                                                                    compartment_id,
                                                                    operating_system='Custom').data
        oci_images_data += oci.pagination.list_call_get_all_results(oci_imageclient.list_images,
                                                                    compartment_id,
                                                                    operating_system='Oracle Linux').data
        oci_images_data += oci.pagination.list_call_get_all_results(oci_imageclient.list_images,
                                                                    compartment_id,
                                                                    operating_system='Oracle Autonomous Linux').data
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        _logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for image in oci_images_data:
        # print_g('%4d %-40s %s' % (oci_images_data.index(image), image.display_name, image.id))
        print_g('%4d %-40s %s' % (oci_images_data.index(image), image.display_name, image.operating_system))
    image_data = _select_from(oci_images_data, 'Select Image')
    print_g(image_data, term=False)
    return image_data


def get_public_ip():
    """
    Request for public ip.

    Returns
    -------
    bool: true or false.
    """
    yn = False
    _ = _clear()
    while not yn:
        pubip = _read_yn('Assign a public IPv4 address?')
        print_g('Public IP: %s' % 'True' if pubip else "False")
        yn = _read_yn('Continue?', default_yn=True)
    return pubip


def get_image(cfg_dict, comp_id):
    """
    Get the source image ocid.

    Parameters
    ----------
    cfg_dict: dict
        The oci configuration file data.
    comp_id: str
        The compartment ocid

    Returns
    -------
        str: the source image ocid.
    """
    yn = False
    _clear()
    while not yn:
        image = select_image(cfg_dict, comp_id)
        print_g(image, term=False)
        print_g('Selected image: %s\n' % image.display_name)
        yn = _read_yn('Continue?', default_yn=True)
    return image.id


def select_availability_domain(config_dict, compartment_id):
    """
    Select an availability domain.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    compartment_id: str
        The compartment ocid

    Returns
    -------
        dict: the availability domain.
    """
    try:
        oci_identity = oci.identity.IdentityClient(config_dict)
        oci_availability_domains = oci_identity.list_availability_domains(compartment_id)
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        _logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for domain in oci_availability_domains.data:
        print_g('%4d %-30s %s' % (oci_availability_domains.data.index(domain), domain.name, domain.id))
    return _select_from(oci_availability_domains.data, 'Select availability domain.')


def get_availability_domain(config_dict, compart_id):
    """
    Get compartment ocid in a loop.

    Parameters
    ----------
    config_dict dict
        The oci configuration file data.

    compart_id: str
        The ocid of the compartment.

    Returns
    -------
        str: the name of the availability domain.
    """
    yn = False
    _clear()
    while not yn:
        domain = select_availability_domain(config_dict, compart_id)
        print_g(domain, term=False)
        print_g('Selected availability domain: %s\n' % domain.name)
        yn = _read_yn('Continue?', default_yn=True)
    return domain.name


def select_shape(config_dict, image_ocid):
    """
    Select a compatible shape for the image.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    image_ocid: str
        The ocid pf the image.

    Returns
    -------
        The shape.
    """
    try:
        oci_imageclient = oci.core.ComputeClient(config_dict)
        oci_shapes = oci_imageclient.list_image_shape_compatibility_entries(image_ocid)
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        _logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for shape_dict in oci_shapes.data:
        print_g('%4d %-30s' % (oci_shapes.data.index(shape_dict), shape_dict.shape))
    return _select_from(oci_shapes.data, 'Select shape.')


def get_shape(cfg_dict, img_ocid):
    """
    Get the ocid of the shape to use.

    Parameters
    ----------
    cfg_dict: dict
        The oci configuration file data.
    img_ocid:str
        The ocid pf the image.

    Returns
    -------
        The shape to use.
    """
    yn = False
    _clear()
    while not yn:
        shape = select_shape(cfg_dict, img_ocid)
        print_g(shape, term=False)
        print_g('Selected shape: %s\n' % shape.shape)
        yn = _read_yn('Continue?', default_yn=True)
    return shape.shape


def get_flex_memory(shape):
    """
    Get the memory size for a flex shape.

    Parameters
    ----------
    shape: str
        The shape name.

    Returns
    -------
        int: the memory size in GB
    """
    yn = False
    _clear()
    while not yn:
        mem_size = _read_nb('Memory for %s in GB' % shape, default_val=4, max_val=256)
        print_g(mem_size, term=False)
        print_g('Memory for %s: %dGB' % (shape, mem_size))
        yn = _read_yn('Continue?', default_yn=True)
    return mem_size


def get_flex_cpus(shape):
    """
    Get the number of cpus for a flex shape.

    Parameters
    ----------
    shape: str
        The shape name.

    Returns
    -------
        int: the number of cpus.
    """
    yn = False
    _clear()
    while not yn:
        nb_cpus = _read_nb('The number of ocpus for %s' % shape, default_val=2, max_val=18)
        print_g(nb_cpus, term=False)
        print_g('The number of ocpus for %s: %s' % (shape,nb_cpus))
        yn = _read_yn('Continue?', default_yn=True)
    return nb_cpus


def _get_display_name():
    """
    Read instance display name from stdin.

    Returns
    -------
        str: the display name.
    """
    return input('Instance Display Name: ')


def _get_authentication_method():
    """
    Determine the authentication method.

    Returns
    -------
        str: the authentication method.
    """
    _ = _clear()
    print_g('Authentication method.\n', term=True)
    auth_methods = ['ApiKey', 'InstancePrincipal']
    yn = False
    while not yn:
        for authm in auth_methods:
            print_g('%4d: %s' % (auth_methods.index(authm), authm))
        method = _select_from(auth_methods, 'Authentication method:')
        print_g('Selected authentication method: %s\n' % method)
        yn = _read_yn('Continue?', default_yn=True)
    return method


def _get_remote_user():
    """
    Get the remote username.

    Returns
    -------
        str: the username.
    """
    yn = False
    _clear()
    while not yn:
        rem_user = input('Remote User Name: ')
        print_g(rem_user, term=False)
        print_g('Remote User Name: %s' % rem_user)
        yn = _read_yn('Continue?', default_yn=True)
    return rem_user


def _get_proxy(default_proxy, prompt):
    """
    Get the http proxy url.

    Parameters
    ----------
    default_proxy: str
        The default value.

    Returns
    -------
        The http proxy url.
    """
    _clear()
    new_url = default_proxy
    yn = False
    while not yn:
        new_urlx = input('%s\n [%s] (ENTER to accept default):' % (prompt,new_url))
        if not bool(new_urlx):
            return(new_url)
        new_url = new_urlx
        print_g(new_url, term=False)
        print_g('%s: %s' % (prompt,new_url))
        yn = _read_yn('Continue?', default_yn=True)
    return new_url


def _get_log_file(default_log_file):
    """
    Get the log file path.

    Parameters
    ----------
    default_log_file: str
        The default path.

    Returns
    -------
        The path tot the log file.
    """
    _clear()
    new_log = default_log_file
    yn = False
    while not yn:
        new_logx = input('log file path\n [%s] (ENTER to accept default):' % default_log_file)
        if not bool(new_logx):
            return(new_log)
        new_log = new_logx
        print_g(new_log, term=False)
        print_g('new log file: %s' % new_log)
        yn = _read_yn('Continue?', default_yn=True)
    return new_log


def _get_string(default_name, prompt):
    _clear()
    new_string = default_name
    yn = False
    while not yn:
        new_stringx = input('%s\n [%s] (ENTER to accept default):' % (prompt,default_name))
        if not bool(new_stringx):
            return(new_string)
        new_display_name = new_stringx
        print_g(new_string, term=False)
        print_g('new value: %s' % new_string)
        yn = _read_yn('Continue?', default_yn=True)
    return new_string


def _get_dns_search_domain():
    """
    Get the dns search domain.

    Returns
    -------
        str: The dns search domain, default is retrieved from /etc/resolv.conf.
    """
    # _clear()
    resolv_file = '/etc/resolv.conf'
    search_domain = 'whocares'
    with open(resolv_file, 'r') as rf:
        for rf_line in rf:
            if 'search' in rf_line:
                search_domain = rf_line.split()[1]
                break
    return search_domain


def _get_dns_server_ip():
    """
    Get the dns server ipv4

    Returns
    -------
        str: The dns server ipv4 address., default is retrieved from /etc/resolv.conf.
    """
    # _clear()
    resolv_file = '/etc/resolv.conf'
    nameserver = '8.8.8.8'
    with open(resolv_file, 'r') as rf:
        for rf_line in rf:
            if 'nameserver' in rf_line:
                nameserver = rf_line.split()[1]
                break
    return nameserver


def get_generic_data(data):
    """
    Get generic variables.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the generic variables.
    """
    gen_data = {
        # 'instance_display_name': _get_display_name(),
        'instance_display_name': data['instance_display_name'],
        'vnic_display_name': data['instance_display_name'],
        'auth': _get_authentication_method(),
        'remote_user': _get_remote_user(),
        # 'http_proxy_url': _get_proxy(default_values['http_proxy_url'], 'http proxy url'),
        # 'https_proxy_url': _get_proxy(default_values['https_proxy_url'], 'https proxy url'),
        # 'http_no_proxy': _get_no_proxy(default_values['http_no_proxy']),
        # 'http_no_proxy': _get_proxy(default_values['http_no_proxy'], 'no proxy'),
        'log_file_path': _get_log_file(default_values['log_file_path']),
        # 'dns_search_domains': _get_dns_search_domain(),
        # 'dns_server_ip': _get_dns_server_ip(),
        'script_path': data['script_path']
    }
    return gen_data


def init_struct(instance_name):
    """
    Initialise config struct.

    Parameters
    ----------
    instance_name: str
        The instance display name.

    Returns
    -------
        dict: the config structure.
    """
    #
    # exec dir
    data = dict()
    exec_dir = inspect.getfile(inspect.currentframe())
    data['instance_display_name'] = instance_name
    print_g40('Instance', data['instance_display_name'])
    data['exec_dir'] = os.path.dirname(exec_dir)
    print_g40('Bin Directory', data['exec_dir'])
    return data


def get_user_data(data):
    """
    Collect operator data.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the configuration data.
    """
    data['operator'] = _get_current_user()
    data['operator_home'] = _get_current_user_home()
    return data


def get_test_instance(data):
    """
    Define the directories involved.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the configuration data.
    """
    #
    # test instance root
    data['test_instance_dir'] = os.path.join(data['operator_home'], autotestdir, data['instance_display_name'])
    print_g40('Tests Instance Location', data['test_instance_dir'])
    #
    # base instance destination
    data['base_instance_dir'] = os.path.join(data['operator_home'], autotestdir, data['instance_display_name'], 'base_instance')
    print_g40('Base_Instance', data['base_instance_dir'])
    #
    # scripts source
    data['script_location'] = os.path.join(data['operator_home'], software_tree, 'tests', 'automation', 'data', 'scripts')
    print_g40('Scripts Location', data['script_location'])
    #
    # scripts destination
    data['script_path'] = os.path.join(data['operator_home'], autotestdir, data['instance_display_name'], 'sh_scripts')
    print_g40('Scripts Directory', data['script_path'])
    #
    # data - instance variables destination
    data['data_dir'] = os.path.join(data['operator_home'], autotestdir, data['instance_display_name'], 'data')
    data['tfvarsfile'] = os.path.join(data['data_dir'], tfvars_file)
    return data


def create_directories(data, args):
    """
    Create directories for scripts.

    Parameters
    ----------
    data: dict
        The configuration data.
    args: namespace
        The command line namespace.

    Returns
    -------
        dict: the configuration data.
    """
    if args.datadir != '_DDDD_':
        data['def_data_dir'] = args.datadir + '/data'
    if not _create_dir(data['test_instance_dir']):
        sys.exit(1)
    print_g40('Created', data['test_instance_dir'])
    if not _create_dir(data['script_path']):
        sys.exit(1)
    print_g40('Created', data['script_path'])
    if not _create_dir(data['data_dir']):
        sys.exit(1)
    print_g40('Created', data['data_dir'])
    if not _create_dir(data['base_instance_dir']):
        sys.exit(1)
    print_g40('Created', data['base_instance_dir'])
    return data


def create_sh_scripts(data):
    """
    Copy script to test instance environment.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    try:
        for script in os.listdir(data['script_location']):
            print_g40('Copy', os.path.join(data['script_location'],script))
            shutil.copy(os.path.join(data['script_location'], script), data['script_path'])
        return True
    except Exception as e:
        print_g('%s' % str(e))
        return False


def main():
    """
    Configure an instance for auto tests.

    Returns
    -------
       int: 0 on success, raises exception on failure.
    """
    #
    # locale
    os.environ['LC_ALL'] = "%s" % lc_all
    #
    # parse the commandline
    args = parse_args()
    #
    # clear
    _ = _clear()
    #
    # user data
    current_user = _get_current_user()
    current_user_home = _get_current_user_home()
    #
    # instance name to create
    instance_display_name = args.display_name if args.display_name is not None else _get_display_name()
    #
    # create log directory
    global config_log
    config_log = initialise_log(current_user_home, logdir, instance_display_name)
    debug_log = initialise_log(current_user_home, logdir, instance_display_name)
    #
    # user data
    print_g40('Current User', current_user)
    print_g40('Current user home', current_user_home)
    #
    # initialise logging
    logging.basicConfig(filename=debug_log,
                        level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s (%(module)s:%(lineno)s) - %(message)s')
    #
    # exec dir
    config_data = init_struct(instance_display_name)
    #
    # current user
    config_data = get_user_data(config_data)
    #
    # check directory with unittests.
    if not _test_softwaretree_defined(config_data['operator_home']):
        sys.exit('Software tree %s not present.' % software_tree)
    #
    # initialise data structure
    image_data = dict()
    #
    # test environment
    config_data = get_test_instance(config_data)
    #
    # create directories
    config_data = create_directories(config_data, args)
    #
    # scripts
    if not create_sh_scripts(config_data):
        sys.exit('Failed to copy scripts')
    #
    # init tfvars file
    tfvarsfile = os.path.join(config_data['data_dir'], args.varfilename + '.tfvars.json')
    cfg_dict = get_configdata(args.profile, args.configfile)
    #
    #
    with autotesttfvars(tfvarsfile) as atfv:
        if not atfv.update_json_with_config(cfg_dict):
            sys.exit("Failed to update json.")
        print_g40('Updated variables with config data', 'ok')
        res = atfv.update_user()
        print_g40('Updated variables with operator data', 'ok')
    #
    # Instance compartment
    image_data['compartment_ocid'] = get_compartment(cfg_dict, 'Select compartment for the instance:')
    #
    # Availability domain
    image_data['availability_domain'] = get_availability_domain(cfg_dict, image_data['compartment_ocid'])
    #
    # Network compartment
    # image_data['network_compartment_ocid'] = get_compartment(cfg_dict, 'Select compartment for the network:')
    network_compartment_ocid = get_compartment(cfg_dict, 'Select compartment for the network:')
    #
    # Virtual Cloud Network
    # image_data['vcn_ocid'] = get_vcn(cfg_dict, image_data['network_compartment_ocid'])
    # image_data['vcn_ocid'] = get_vcn(cfg_dict, network_compartment_ocid)
    image_data_vcn_ocid = get_vcn(cfg_dict, network_compartment_ocid)
    #
    # Subnets
    # image_data['subnet_ocid'] = get_subnet(cfg_dict, image_data['network_compartment_ocid'], image_data['vcn_ocid'])
    image_data['subnet_ocid'] = get_subnet(cfg_dict, network_compartment_ocid, image_data_vcn_ocid)
    #
    # Public ip
    image_data['assign_public_ip'] = get_public_ip()
    #
    # Type
    image_data['source_type'] = 'image'
    #
    # Images
    image_data['source_ocid'] = get_image(cfg_dict, image_data['compartment_ocid'])
    #
    # Shape
    image_data['shape'] = get_shape(cfg_dict, image_data['source_ocid'])
    #
    # Flex shape: get memory size and number of cpus
    if bool(re.search('Flex', image_data['shape'])):
        image_data['instance_flex_memory_in_gbs'] = get_flex_memory(image_data['shape'])
        image_data['instance_flex_ocpus'] = get_flex_cpus(image_data['shape'])
    #
    # various data
    # varia_data = {
    #     'vnic_display_name': default_values['vnic_display_name']
    # }

    # with autotesttfvars(tfvarsfile) as atfv:
    #     res = atfv.update_varia(varia_data)
    #     print_g('Updated various data.')
    #
    # get generic variables
    gen_data = get_generic_data(config_data)
    #
    # update tfvars file
    with autotesttfvars(tfvarsfile) as atfv:
        res = atfv.update_image(image_data)
        print_g('Updated variables with image data.')
        res = atfv.update_gen_data(gen_data)
        print_g('Updated variables with generic data.')
    #
    #
    print_g('Wrote configuration to %s' % tfvarsfile)


if __name__ == "__main__":
    sys.exit(main())
