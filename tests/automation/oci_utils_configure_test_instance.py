#!/bin/python3
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import argparse
import getpass
import json
import logging
import os
import re
import socket
import sys
import termios
import tty

import oci

#
# locale
lc_all = 'en_US.UTF8'

autotest_tfvars = 'autotest'
default_log = 'autotest.conf.log'

default_values = {
    "os_user" : "whocares",
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
    "vcn_ocid": "whocares",
    "network_compartment_ocid": "whocares",
    "vnic_display_name": "whocares",
    "availability_domain": "whocares",
    "instance_display_name": "whocares",
    "shape": "whocares",
#    "authentication": "whocares",
    "source_type": "whocares",
    "remote_user": "whocares",
    "autotest_root": "whocares",
    "log_file_path": "/logs",
    "dns_search_domains" : ".oracle.com",
    "dns_server_ip" : "100.110.7.250",
    "http_proxy_url": "http://www-proxy-hqdc.us.oracle.com:80",
    "https_proxy_url": "http://www-proxy-hqdc.us.oracle.com:80",
    "http_no_proxy": "169.254.169.254,.oraclecloud.com,.oraclecorp.com,.us.oracle.com"
}

logger = logging.getLogger(__name__)


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
        f.write('%s' % msg)
        f.flush()


def parse_args():
    """
    Parse the command line arguments.
    -p | --profile <profile in the cli/sdk config fild>

    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(description='Configure oci utils auto test.')
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
                        default='./data',
                        help='Root directory with data for auto test run, default is ./data.')
    parser.add_argument('-f', '--var-file',
                        action='store',
                        dest='varfilename',
                        default='autotest',
                        help='filename to store the variables; the extension .tfvars.json is added automatically.')
    parser._optionals.title = 'Arguments'
    args = parser.parse_args()
    return args


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
        else:
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
        except Exception as e:
            #
            # Failed to read variable def file, falling back to idle defaults.
            print_g('Failed to read %s, creating default' % self.json_file)
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
        print_g('\nCollecting data from sdk config file:')
        self.jsondata['user_ocid'] = sdk_config['user']
        print_g('user ocid:          %s' % sdk_config['user'])
        self.jsondata['fingerprint'] = sdk_config['fingerprint']
        print_g('fingerprint         %s' % sdk_config['fingerprint'])
        self.jsondata['oci_private_key'] = sdk_config['key_file']
        print_g('oci_private_key:    %s' % sdk_config['key_file'])
        self.jsondata['tenancy_ocid'] = sdk_config['tenancy']
        print_g('tenancy_ocid:       %s' % sdk_config['tenancy'])
        self.jsondata['region'] = sdk_config['region']
        print_g('region:             %s' % sdk_config['region'])
        if _read_yn('Agree?', default_yn=True):
            return True
        return False

    def update_user(self):
        """
        Update tf.jsan file with user related data.

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
            self.jsondata['ssh_publid_key'] = _from_stdin('ssh public key', default=pub_key)
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
        #
        for var_key, var_val in variadata.items():
            print_g('%30s %s' % (var_key, var_val))
            self.jsondata[var_key] = _from_stdin('%s' % var_key)
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
    logger.debug('Selected %s', some_list[select_index])
    return some_list[select_index]


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
        logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for comp in oci_compartments.data:
        print_g('%4d %-30s %s' % (oci_compartments.data.index(comp), comp.name, comp.id))
    return _select_from(oci_compartments.data, prompt)


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
        logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for vcn in oci_vcns.data:
        print_g('%4d %-30s %s' % (oci_vcns.data.index(vcn), vcn.display_name, vcn.id))
    return _select_from(oci_vcns.data, 'Select VCN for instance.')


def select_subnet(config_dict, compartment_id, vcn_id):
    """
    Select a subnet.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    compartment_id: str
        The compartment ocid

    Returns
    -------
        dict: the subnet
    """
    try:
        oci_subnetclient = oci.core.VirtualNetworkClient(config_dict)
        oci_subnets = oci_subnetclient.list_subnets(compartment_id, vcn_id=vcn_id)
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for subnet in oci_subnets.data:
        print_g('%4d %-30s %s' % (oci_subnets.data.index(subnet), subnet.display_name, subnet.id))
    return _select_from(oci_subnets.data, 'Select subnet instance.')


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
        oci_images = oci_imageclient.list_images(compartment_id, operating_system='Oracle Linux')
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for image in oci_images.data:
        print_g('%4d %-30s %s' % (oci_images.data.index(image), image.display_name, image.id))
    return _select_from(oci_images.data, 'Select image for instance:.')


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
        oci_availabitly_domains = oci_identity.list_availability_domains(compartment_id)
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for domain in oci_availabitly_domains.data:
        print_g('%4d %-30s %s' % (oci_availabitly_domains.data.index(domain), domain.name, domain.id))
    return _select_from(oci_availabitly_domains.data, 'Select availability domain.')


def select_shape(config_dict, image_ocid):
    """
    Select a compatible shape for the image.

    Parameters
    ----------
    imageid: str
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
        logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for shape_dict in oci_shapes.data:
        print_g('%4d %-30s' % (oci_shapes.data.index(shape_dict), shape_dict.shape))
    return _select_from(oci_shapes.data, 'Select shape.')


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
    auth_methods = ['ApiKey', 'InstancePrincipal']
    for authm in auth_methods:
        print_g('%4d: %s' % (auth_methods.index(authm), authm))
    return _select_from(auth_methods, 'Authentication method:')


def _get_remote_user():
    """
    Get the remote username.

    Returns
    -------
        str: the username.
    """
    return input('\nRemote User Name: ')


def _get_http_proxy(default_proxy):
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
    new_url = input('http proxy url\n [%s] (ENTER to accept default):' % default_proxy)
    if not bool(new_url):
        new_url = default_proxy
    return new_url


def _get_https_proxy(default_proxy):
    """
    Get the http proxy url.

    Parameters
    ----------
    default_proxy: str
        The default value.

    Returns
    -------
        The https proxy url.
    """
    new_url = input('https proxy url\n [%s] (ENTER to accept default):' % default_proxy)
    if not bool(new_url):
        new_url = default_proxy
    return new_url


def _get_no_proxy(default_proxy):
    """
    Get the no proxy list.

    Parameters
    ----------
    default_proxy: str
        The default value.

    Returns
    -------
        The https proxy url.
    """
    new_url = input('no proxy\n [%s] (ENTER to accept default):' % default_proxy)
    if not bool(new_url):
        new_url = default_proxy
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
    new_log_file = input('log file path\n [%s] (ENTER to accept default):' % default_log_file)
    if not bool(new_log_file):
        new_log_file = default_log_file
    return new_log_file


def _get_dns_search_domain():
    """
    Get the dns search domain.

    Returns
    -------
        str: The dns search domain, default is retrieved from /etc/resolv.conf.
    """
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
    resolv_file = '/etc/resolv.conf'
    nameserver = '8.8.8.8'
    with open(resolv_file, 'r') as rf:
        for rf_line in rf:
            if 'nameserver' in rf_line:
                nameserver = rf_line.split()[1]
                break
    return nameserver


def get_generic_data():
    """
    Get generic variables.

    Parameters
    ----------
    gendata: str
        path to generic data directory.

    Returns
    -------
        dict: the generic variables.
    """
    gen_data = {
        'instance_display_name': _get_display_name(),
        'auth': _get_authentication_method(),
        'remote_user': _get_remote_user(),
        'http_proxy_url': _get_http_proxy(default_values['http_proxy_url']),
        'https_proxy_url': _get_https_proxy(default_values['https_proxy_url']),
        'http_no_proxy': _get_no_proxy(default_values['http_no_proxy']),
        'log_file_path': _get_log_file(default_values['log_file_path']),
        'dns_search_domains': _get_dns_search_domain(),
        'dns_server_ip': _get_dns_server_ip()
    }
    return gen_data


def main():
    """
    Configure auto tests.

    Returns
    -------
       int: 0 on success, raises exception on failure.
    """
    logging.basicConfig(filename='/tmp/oci_utils_configure_test_instance.log', level=logging.DEBUG)
    #
    # locale
    os.environ['LC_ALL'] = "%s" % lc_all
    #
    # init log
    with open(default_log, 'w') as f:
        f.write('')
        f.flush()
    #
    # current user
    operator = _get_current_user()
    operator_home = _get_current_user_home()
    print_g('\nUsername: %s\nHome:     %s' % (operator, operator_home))
    #
    # initialise data structure
    image_data = dict()
    #
    # parse the commandline
    args = parse_args()
    tfvarsfile = args.datadir + '/' + args.varfilename + '.tfvars.json'
    cfg_dict = get_configdata(args.profile, args.configfile)
    print_g('Configuration')
    for k, v in cfg_dict.items():
        print_g('%40s: %s' % (k, v))

    with autotesttfvars(tfvarsfile) as atfv:
        res = atfv.update_json_with_config(cfg_dict)
        print_g('Updated variables with config data')
        res = atfv.update_user()
        print_g('Updated variables with operator data')

    #
    # Instance compartment
    instance_compartment = select_compartment(cfg_dict, "Select compartment for the instance.")
    print_g(instance_compartment, term=False)
    print_g('Selected compartment: %s\n' % instance_compartment.name)
    compartment_ocid = instance_compartment.id
    image_data['compartment_ocid'] = compartment_ocid
    #
    # Availability domain
    availability_domain = select_availability_domain(cfg_dict, compartment_ocid)
    print_g(availability_domain, term=False)
    print_g('Selected availability domain: %s\n' % availability_domain.name)
    image_data['availability_domain'] = availability_domain.name
    #
    # Network compartment
    network_compartment = select_compartment(cfg_dict, "Select compartment for the network.")
    print_g(network_compartment, term=False)
    print_g('Selected network compartment: %s\n' % network_compartment.name)
    image_data['compartment_ocid'] = compartment_ocid
    network_compartment_ocid = network_compartment.id
    #
    # Virtual Cloud Network
    vcn = select_vcn(cfg_dict, network_compartment_ocid)
    print_g(vcn, term=False)
    print_g('Selected VCN: %s\n' % vcn.display_name)
    image_data['vcn_ocid'] = vcn.id
    #
    # Subnets
    subnet = select_subnet(cfg_dict, network_compartment_ocid, vcn_id=vcn.id)
    print_g(subnet, term=False)
    print_g('Selected subnet: %s\n' % subnet.display_name)
    image_data['subnet_ocid'] = subnet.id
    #
    # Type
    image_data['source_type'] = 'image'
    #
    # Images
    image = select_image(cfg_dict, compartment_ocid)
    print_g(image, term=False)
    print_g('Selected image: %s\n' % image.display_name)
    image_data['source_ocid'] = image.id
    #
    # Shape
    shape = select_shape(cfg_dict, image.id)
    print_g(shape, term=False)
    print_g('Selected shape: %s\n' % shape.shape)
    image_data['shape'] = shape.shape
    #
    # get generic variables
    gen_data = get_generic_data()
    #
    # various data
    varia_data = {
        'vnic_display_name': 'whocares'
    }
    with autotesttfvars(tfvarsfile) as atfv:
        res = atfv.update_varia(varia_data)
        print_g('Updated various data.')
    # print_g(gen_data)
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
