#!/bin/python3
# Copyright (c) 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Modify scripts used to create an instance using terraform.
"""
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
from pprint import pformat

import oci

#
# locale
lc_all = 'en_US.UTF8'

tfvars_file = 'instance_variables'
default_log = '/var/tmp/instance_config_'
default_instance_dir = 'oci_instances'
create_instance_source = 'create_instance'


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
    # "vcn_ocid": "whocares",
    # "network_compartment_ocid": "whocares",
    "vnic_display_name": "whocares",
    "availability_domain": "whocares",
    "instance_display_name": "whocares",
    "shape": "whocares",
    # "authentication": "whocares",
    "source_type": "whocares",
    "boot_volume_size_in_gbs": 51,
    "remote_user": "whocares",
    # "autotest_root": "whocares",
    "log_file_path": "/logs",
    "initial_script_path": "whocares",
    # "dns_search_domains" : ".oracle.com",
    # "dns_server_ip" : "100.110.7.250",
    # "http_proxy_url": "http://www-proxy-hqdc.us.oracle.com:80",
    # "https_proxy_url": "http://www-proxy-hqdc.us.oracle.com:80",
    # "http_no_proxy": "169.254.169.254,.oraclecloud.com,.oraclecorp.com,.us.oracle.com"
}

updatable_parameters = {'availability domain': 'availability_domain',
                        'boot volume size': 'boot_volume_size_in_gbs',
                        'memory': 'instance_flex_memory_in_gbs',
                        'nb cpus': 'instance_flex_ocpus',
                        'subnet': 'subnet_ocid',
                        'shape': 'shape',
                        'image': 'source_ocid'}


_logger = logging.getLogger(__name__)


def print_g(msg, term=True):
    """
    Write msg to stdout and to file.

    Parameters
    ----------
    msg: str
        The text.
    term: bool
        If true, write to stdout.

    Returns
    -------
        No return value.
    """
    if term:
        print('%s' % msg)
    _logger.debug(msg)


def print_g_left(head, headlen, msg, term=True):
    """
    Write message with header of a defined size.

    Parameters
    ----------
    head: str
        The header
    headlen: int
        The length of the header.
    msg: str
        The message.
    term: bool
        If True, write to stdout.

    Returns
    -------
        No return value.
    """
    print_g(f'{head:{headlen}s}: {msg}', term=term)


def parse_args():
    """
    Parse the command line arguments.
    -p | --profile <profile in the cli/sdk config fild>

    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(prog='modify_instance',
                                     description='Configure oci utils auto test.')
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
        dict: the config data.
    """
    sdkconfigfile = configfile
    if configfile.startswith('~/'):
        sdkconfigfile = os.path.expanduser('~') + configfile[1:]
    config = oci.config.from_file(file_location=sdkconfigfile, profile_name=profile)
    return config


class SubnetsData:
    def __init__(self, config):
        self.config = config
        self.compartment_list = list()
        self.vcns = list()
        self.subnets = list()

    def get_compartemnts(self, tenancy_id):
        """
        Collect the data for all compartments in a tenancy.

        Parameters
        ----------
        tenancy_id: str
            ocid of a tenancy.

        Returns
        -------
            list: list of compartment objercts.
        """
        oci_identity = oci.identity.IdentityClient(self.config)
        try:
            oci_compartments = oci_identity.list_compartments(self.config['tenancy']).data
        except oci.exceptions.ServiceError as e:
            print_g('*** AUTHORISATION ERROR ***')
            sys.exit(1)
        except Exception as e:
            print_g('*** ERROR *** %s' % str(e))
            _logger.error('ERROR %s', str(e), exc_info=True)
            sys.exit(1)
        return oci_compartments

    def get_vcns(self, compartment_id):
        """
        Collect the data of all vcns in a tenancy.

        Parameters
        ----------
        compartment_id: str
            ocid of a compartment

        Returns
        -------
        list: list of vcn objects.
        """
        oci_vcn_client = oci.core.VirtualNetworkClient(self.config)
        try:
            oci_vcns = oci_vcn_client.list_vcns(compartment_id).data
        except oci.exceptions.ServiceError as e:
            if e.status == 404:
                #
                # we skip an authorisation error here, as one cannot expect to have access to all compartments.
                return None
            else:
                print_g('*** ERROR *** %s' % str(e))
                _logger.error('ERROR %s', str(e), exc_info=True)
                sys.exit(1)
        return oci_vcns

    def get_subnets_in_vcn(self, compartment_id, vcn_id):
        """
        Collect the data of all subnets in a tenancy.

        Parameters
        ----------
        compartment_id: str
            ocid of a compartment
        vcn_id: str
            ocid of a vcn.

        Returns
        -------
            list: list of subnet objects.
        """
        oci_subnet_client = oci.core.VirtualNetworkClient(self.config)
        try:
            oci_subnets = oci_subnet_client.list_subnets(compartment_id, vcn_id)
        except oci.exceptions.ServiceError as e:
            if e.status == 404:
                #
                # we skip an authorisation error here, as one cannot expect to have access to all compartments.
                return None
            else:
                print_g('*** ERROR *** %s' % str(e))
                _logger.error('ERROR %s', str(e), exc_info=True)
                sys.exit(1)
        return  oci_subnets


class InstanceData:
    def __init__(self, instance_name, args):
        self.instance_name = instance_name
        self.args = args
        #
        # initialise config structure
        self.data = self.init_config()
        self.compartments = self.get_compartments()
        self.subnets = self.get_subnet_details()
        self.availability_domains = list()
        self.image_list = list()
        self.shape_list = list()

    def init_config(self):
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
        data = dict()
        exec_dir = inspect.getfile(inspect.currentframe())
        data['instance_display_name'] = self.instance_name
        data['exec_dir'] = os.path.dirname(exec_dir)
        data['base_exec_dir'] = os.path.dirname(exec_dir)
        data['operator'] = _get_current_user()
        data['operator_home'] = _get_current_user_home()
        def_base_dir = data['operator_home'] + '/' + default_instance_dir
        instance_display_name = data['instance_display_name']
        data['def_instance_dir'] = def_base_dir + '/' + instance_display_name
        data['def_data_dir'] = def_base_dir + '/' + instance_display_name + '/data'
        data['base_instance_dir'] = def_base_dir + '/' + instance_display_name + '/base_instance'
        data['def_tf_scripts_dir'] = def_base_dir + '/' + instance_display_name + '/tf_scripts'
        data['def_sh_scripts_dir'] = def_base_dir + '/' + instance_display_name + '/sh_scripts'
        data['tfvarsfile'] = data['def_data_dir'] + '/' + self.args.varfilename + '.tfvars.json'
        if self.args.datadir != '_DDDD_':
            data['def_data_dir'] = self.args.datadir + '/data'
            data['def_tf_scripts_dir'] = self.args.datadir + '/tf_scripts'
            data['def_sh_scripts_dir'] = self.args.datadir + '/sh_scripts'
            data['base_instance_dir'] = self.args.datadir + '/base_instance'
        data['oci_config'] = self.get_configdata()
        return data

    def get_configdata(self):
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
        sdkconfigfile = self.args.configfile
        if self.args.configfile.startswith('~/'):
            sdkconfigfile = os.path.expanduser('~') + self.args.configfile[1:]
        return oci.config.from_file(file_location=sdkconfigfile, profile_name=self.args.profile)

    def get_compartments(self):
        """
        Get the list of compartments in this tenancy.

        Parameters
        ----------
        config_dict: dict
            The oci configuration file data.

        Returns
        -------
            list: list of compartment objects.
        """
        try:
            oci_identity = oci.identity.IdentityClient(self.data['oci_config'])
            print(self.data['oci_config']['tenancy'])
            oci_compartments = oci_identity.list_compartments(self.data['oci_config']['tenancy'])
        except oci.exceptions.ServiceError as e:
            print_g('*** AUTHORISATION ERROR ***')
            sys.exit(1)
        except Exception as e:
            print_g('*** ERROR *** %s' % str(e))
            _logger.error('ERROR %s', str(e), exc_info=True)
            sys.exit(1)
        return oci_compartments.data

    def set_compartment_name(self):
        """
        Get the compartment name based on the ocid

        Parameters
        ----------
        compartments: list
            List of compartment objects.
        compartment_id: str
            The compartment ocid.

        Returns
        -------
            str: the compartment name.
        """
        for compartment in self.compartments:
            if compartment.id == self.data['compartment_ocid']:
                return compartment.name
        return None

    def set_compartment_id(self, ocid):
        """
        Set the current compartment id and name.

        Parameters
        ----------
        ocid: str
            The compartment ocid.

        Returns
        -------
            No return value.
        """
        self.data['compartment_ocid'] = ocid
        self.data['compartment_name'] = self.set_compartment_name()

    def get_compartment_name(self):
        """
        Return the compartent name.

        Returns
        -------
            str: the compartment name.
        """
        return self.data['compartment_name']

    def get_subnet_details(self):
        """
        Get all subnets in all accessible compartments.

        Parameters
        ----------
        compartments: list
            list of compartment objects.
        config_dict: dict
            The oci configuration file data.

        Returns
        -------
            list: the list of subnets.
        """
        oci_subnet_list = list()
        oci_subnetclient = oci.core.VirtualNetworkClient(self.data['oci_config'])
        oci_vcn_client = oci.core.VirtualNetworkClient(self.data['oci_config'])
        for compartment in self.compartments:
            try:
                oci_vcns = oci_vcn_client.list_vcns(compartment.id).data
                for vcn in oci_vcns:
                    oci_subnet_list.extend(oci_subnetclient.list_subnets(compartment.id, vcn_id=vcn.id).data)
            except oci.exceptions.ServiceError as e:
                #
                # we skip an authorisation error here, as one cannot expect to have access to all compartments.
                if e.status == 404:
                    pass
                else:
                    print_g('*** ERROR *** %s' % str(e))
                    _logger.error('ERROR %s', str(e), exc_info=True)
                    sys.exit(1)
        return oci_subnet_list

    def get_subnet_name(self, ocid):
        for subn in self.subnets:
            if subn.id == ocid:
                return subn.display_name()
        return None

    def set_availability_domains(self, compartment_id):
        """
        Set the list of availability domains.

        Parameters
        ----------
        compartment_id: str
            The compartment ocid.

        Returns
        -------
            No return value.
        """
        try:
            oci_identity = oci.identity.IdentityClient(self.data['oci_config'])
            oci_availability_domains = oci_identity.list_availability_domains(compartment_id)
        except oci.exceptions.ServiceError as e:
            print_g('*** AUTHORISATION ERROR ***')
            _logger.error('Authorisation error', exc_info=True)
            sys.exit(1)
        except Exception as e:
            print_g('*** ERROR *** %s' % str(e))
            _logger.error('ERROR %s', str(e), exc_info=True)
            sys.exit(1)
        self.availability_domains = oci_availability_domains.data

    def set_image_list(self, compartment_id):
        """
        Get a list of availabel images in this compartment.

        Parameters
        ----------
        config_dict: dict
            The oci configuration file data.
        compartment_id: str
            The compartment ocid.

        Returns
        -------
            list: the list of the image objects.
        """
        try:
            oci_imageclient = oci.core.ComputeClient(self.data['oci_config'])
            oci_images_data_all = oci.pagination.list_call_get_all_results(oci_imageclient.list_images, compartment_id)
        except oci.exceptions.ServiceError as e:
            print_g('*** AUTHORISATION ERROR ***')
            _logger.error('Authorisation error', exc_info=True)
            sys.exit(1)
        except Exception as e:
            print_g('*** ERROR *** %s' % str(e))
            _logger.error('ERROR %s', str(e), exc_info=True)
            sys.exit(1)
        #
        # remove windows from the list.
        oci_images_list = list()
        for image in oci_images_data_all.data:
            if 'Windows' not in image.operating_system:
                oci_images_list.append(image)
        self.image_list = oci_images_list

    def get_image_name(self, image_id):
        for img in self.image_list:
            if img.id == image_id:
                return img.display_name
        return None

    def set_shape_list(self, image_ocid):
        try:
            oci_imageclient = oci.core.ComputeClient(self.data['oci_config'])
            oci_shapes = oci_imageclient.list_image_shape_compatibility_entries(image_ocid)
        except oci.exceptions.ServiceError as e:
            print_g('*** AUTHORISATION ERROR ***')
            _logger.error('Authorisation error', exc_info=True)
            sys.exit(1)
        except Exception as e:
            print_g('*** ERROR *** %s' % str(e))
            _logger.error('ERROR %s', str(e), exc_info=True)
            sys.exit(1)
        self.shape_list = oci_shapes.data


class TerraformData:
    """
    Manipulate the tfvar.json file.
    """
    def __init__(self, tfvars_file):
        """
        Initialise, read the terraform variables values if they exist.

        Parameters
        ----------
        tfvars_file: str
            Full path of the tfvar.json file.
        """
        self.json_file = tfvars_file
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
        """
        Write the terraform variables values.

        Returns
        -------
            No return value.
        """
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

    def update_user(self, display_name):
        """
        Update tf.json file with user related data.

        Parameters
        ----------
        display_name: str
            The instance display name

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
        # initial script
        # self.jsondata['initial_script_path'] = self.jsondata['os_user_home'] \
        #                                        + '/' \
        #                                        + default_instance_dir \
        #                                        + '/' \
        #                                        + display_name \
        #                                       + '/sh_scripts/initial_config.sh'
        self.jsondata['initial_script_path'] = os.path.join(self.jsondata['os_user_home'],
                                                            default_instance_dir,
                                                            display_name,
                                                            'sh_scripts',
                                                            'initial_config.sh')
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
            print_g('%30s %s' % (var_key, var_val))
            self.jsondata[var_key] = var_val
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


def get_compartments(config_dict):
    """
    Get the list of compartments in this tenancy.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.

    Returns
    -------
        list: list of compartment objects.
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
    return oci_compartments.data


def get_compartment_name(compartments, compartment_id):
    """
    Get the compartment name based on the ocid

    Parameters
    ----------
    compartments: list
        List of compartment objects.
    compartment_id: str
        The compartment ocid.

    Returns
    -------
        str: the compartment name.
    """
    for compartment in compartments:
        if compartment.id == compartment_id:
            return compartment.name
    return None


def get_subnet_name(subnets, subnet_id):
    """
    Get the subnet name based on the ocid.

    Parameters
    ----------
    subnets: list
        List of subnet objects.
    subnet_id: str
        The subnet ocid.

    Returns
    -------
        str: the subnet name.
    """
    for subnet in subnets:
        if subnet.id == subnet_id:
            return subnet.display_name
    return None


def get_image_name(images, image_id):
    """
    Get the image name based on the ocid.

    Parameters
    ----------
    images: list
        List of image objects.
    image_id: str
        The image ocid.

    Returns
    -------
        str: the image name.
    """
    print(dir(images[0]))
    for image in images:
        if image.id == image_id:
            return image.display_name
    return None


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
    oci_compartments = get_compartments(config_dict['tenancy'])

    for comp in oci_compartments:
        print_g('%4d %-30s %s' % (oci_compartments.index(comp), comp.name, comp.id))
    return _select_from(oci_compartments.data, prompt)


def get_vcns(config_dict, compartment_id):
    """
    Get the list of vcns in this compartment.

    Parameters
    ----------
    config_dict: dict
        The oci configuration data.
    compartment_id: str
        The compartment ocid.

    Returns
    -------
        list: the list of vcn objects.
    """
    try:
        oci_vcnclient = oci.core.VirtualNetworkClient(config_dict)
        oci_vcns = oci_vcnclient.list_vcns(compartment_id).data
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        _logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    return oci_vcns


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
    oci_vcns = get_vcns(config_dict['tenancy'], compartment_id)

    for vcn in oci_vcns :
        print_g('%4d %-30s %s' % (oci_vcns.index(vcn), vcn.display_name, vcn.id))
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
        _logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    for subnet in oci_subnets.data:
        print_g('%4d %-30s %s' % (oci_subnets.data.index(subnet), subnet.display_name, subnet.id))
    return _select_from(oci_subnets.data, 'Select subnet instance.')


def get_subnet_details(compartments,config_dict):
    """
    Get all subnets in all accessible compartments.

    Parameters
    ----------
    compartments: list
        list of compartment objects.
    config_dict: dict
        The oci configuration file data.

    Returns
    -------
        list: the list of subnets.
    """
    oci_subnet_list = list()
    oci_subnetclient = oci.core.VirtualNetworkClient(config_dict)
    oci_vcn_client = oci.core.VirtualNetworkClient(config_dict)
    for compartment in compartments:
        try:
            oci_vcns = oci_vcn_client.list_vcns(compartment.id).data
            for vcn in oci_vcns:
                oci_subnet_list.extend(oci_subnetclient.list_subnets(compartment.id, vcn_id=vcn.id).data)
        except oci.exceptions.ServiceError as e:
            #
            # we skip an authorisation error here, as one cannot expect to have access to all compartments.
            if e.status == 404:
                pass
            else:
                print_g('*** ERROR *** %s' % str(e))
                _logger.error('ERROR %s', str(e), exc_info=True)
                sys.exit(1)
    return oci_subnet_list


def get_images(config_dict, compartment_id):
    """
    Get a list of availabel images in this compartment.

    Parameters
    ----------
    config_dict: dict
        The oci configuration file data.
    compartment_id: str
        The compartment ocid.

    Returns
    -------
        list: the list of the image objects.
    """
    try:
        oci_imageclient = oci.core.ComputeClient(config_dict)
        oci_images_data_all = oci.pagination.list_call_get_all_results(oci_imageclient.list_images, compartment_id).data
    except oci.exceptions.ServiceError as e:
        print_g('*** AUTHORISATION ERROR ***')
        _logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
        sys.exit(1)
    #
    # remove windows from the list.
    oci_images_list = list()
    for image in oci_images_data_all:
        if 'Windows' not in image.operating_system:
            oci_images_list.append(image)
    return oci_images_list


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
    oci_images_data = get_images(config_dict, compartment_id)
    for image in oci_images_data:
        # print_g('%4d %-40s %s' % (oci_images_data.index(image), image.display_name, image.id))
        print_g('%4d %-40s %s' % (oci_images_data.index(image), image.display_name, image.operating_system))
    image_data = _select_from(oci_images_data, 'Select Image')
    print_g(image_data, term=False)
    return image_data


def get_availability_domain(data):
    """
    Get the availablility domain data.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the configuration data.
    """
    _ = _clear()
    print_g('Availability domain.\n', term=True)
    availability_domain = select_availability_domain(data['oci_config'], data['compartment'].id)
    print_g(availability_domain, term=False)
    print_g('Selected availability domain: %s\n' % availability_domain.name)
    data['availability_domain'] = availability_domain.name
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    return data


def get_availability_domains(config_dict, compartment_id):
    """
    Get the list of availbility domains.

    Parameters
    ----------
    config_dict: dict
        The oci configuration data.
    compartment_id: str
        The compartment ocid.

    Returns
    -------
        list of availability domains.
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
    return oci_availability_domains.data


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
    oci_availability_domains = get_availability_domains(config_dict, compartment_id)
    for domain in oci_availability_domains:
        print_g('%4d %-30s %s' % (oci_availability_domains.data.index(domain), domain.name, domain.id))
    return _select_from(oci_availability_domains.data, 'Select availability domain.')


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
        _logger.error('Authorisation error', exc_info=True)
        sys.exit(1)
    except Exception as e:
        print_g('*** ERROR *** %s' % str(e))
        _logger.error('ERROR %s', str(e), exc_info=True)
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
    _ = _clear()
    print_g('Authentication method.\n', term=True)
    auth_methods = ['ApiKey', 'InstancePrincipal']
    for authm in auth_methods:
        print_g('%4d: %s' % (auth_methods.index(authm), authm))
    method = _select_from(auth_methods, 'Authentication method:')
    print_g('Selected authentication method: %s\n' % method)
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    return method


def _get_remote_user():
    """
    Get the remote username.

    Returns
    -------
        str: the username.
    """
    _ = _clear()
    print_g('Remote user.\n', term=True)
    rem_user = input('\nRemote User Name: ')
    print_g('Selected remote user name: %s\n' % rem_user)
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    return rem_user


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
    _ = _clear()
    print_g('Log file path.\n', term=True)
    new_log_file = input('log file path\n [%s] (ENTER to accept default):' % default_log_file)
    print_g('Selected log file path: %s\n' % new_log_file)
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
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
        # 'instance_display_name': _get_display_name(),
        'auth': _get_authentication_method(),
        'remote_user': _get_remote_user(),
        # 'http_proxy_url': _get_http_proxy(default_values['http_proxy_url']),
        # 'https_proxy_url': _get_https_proxy(default_values['https_proxy_url']),
        # 'http_no_proxy': _get_no_proxy(default_values['http_no_proxy']),
        'log_file_path': _get_log_file(default_values['log_file_path']),
        # 'dns_search_domains': _get_dns_search_domain(),
        # 'dns_server_ip': _get_dns_server_ip()
    }
    return gen_data


def create_dir(dirname):
    """
    Create a directory, make a backup copy if already exists.

    Parameters
    ----------
    dirname: str
        Full path

    Returns
    -------
        bool: True on success, false otherwise.
    """
    try:
        if os.path.exists(dirname):
            bck_name = dirname + '_%s' % datetime.now().strftime('%Y%m%d_%H%M')
            os.rename(dirname, bck_name)
            print_g('Renamed %s to %s' % (dirname, bck_name), term=False)
        os.makedirs(dirname)
        print_g('Created %s' % dirname)
    except OSError as e:
        if e.errno != errno.EEXIST:
            print_g('Failed to create %s' % dirname, term=False)
            return False
        print_g('%s already exists, might cause problems.' % dirname, term=False)
    return True


def copy_dir(src, dest):
    """
    Copy a directory recursively.

    Parameters
    ----------
    src:str
        Source dir
    dest: str
        Destination dir

    Returns
    -------
        bool: True on success, False otherwise
    """
    try:
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(src, dest, symlinks=False)
        print_g('Copied %s to %s' % (src, dest))
    except Exception as e:
        _logger.error('Failed to copy %s to %s: %s', src, dest, str(e))
        return False
    return True


def backup_file(tfvars):
    """
    Backup a file.

    Parameters
    ----------
    tfvars: str
        File name.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    try:
        if os.path.exists(tfvars):
            tfvars_bck = tfvars + '_%s' % datetime.now().strftime('%Y%m%d_%H%M')
            shutil.copy(tfvars, tfvars_bck)
            print_g('Copied %s to %s' % (tfvars, tfvars_bck))
        else:
            print_g('File %s does not exist.', tfvars)
    except ValueError as e:
        _logger.error('Failed to backup %s to %s: %s', tfvars, tfvars_bck, str(e))
        return False
    return True


def write_bash(fn, cmd):
    """
    Write a command to the script file fn.

    Parameters
    ----------
    fn: str
        Full path of the script file.
    cmd: str
        The string.

    Returns
    -------
    bool: True or False
    """
    try:
        if not os.path.exists(fn):
            with open(fn, 'w') as fd:
                fd.write('#!/bin/bash\n')
                fd.flush()
            os.chmod(fn, 0o755)
        with open(fn, 'a') as fd:
            fd.write('%s\n' % cmd)
            fd.flush()
            fd.write('RETVAL=${?}\n')
            fd.flush()
            fd.write('if [ $RETVAL -ne 0 ]; then\n')
            fd.flush()
            fd.write('  echo "%s failed"\n' % cmd)
            fd.flush()
            fd.write('  exit $RETVAL\n')
            fd.flush()
            fd.write('  echo "%s succeeded"\n' % cmd)
            fd.write('fi\n')
            fd.flush()
        return True
    except Exception as e:
        print_g('***ERROR*** %s' % str(e))
        return False


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
    data['exec_dir'] = os.path.dirname(exec_dir)
    data['base_exec_dir'] = os.path.dirname(exec_dir)
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
    print_g_left('Username', 30, data['operator'])
    print_g_left('Home', 30, data['operator_home'])
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
    def_base_dir = data['operator_home'] + '/' + default_instance_dir
    instance_display_name = data['instance_display_name']
    data['def_instance_dir'] = def_base_dir + '/' + instance_display_name
    data['def_data_dir'] = def_base_dir + '/' + instance_display_name + '/data'
    data['base_instance_dir'] = def_base_dir + '/' + instance_display_name + '/base_instance'
    data['def_tf_scripts_dir'] = def_base_dir + '/' + instance_display_name + '/tf_scripts'
    data['def_sh_scripts_dir'] = def_base_dir + '/' + instance_display_name + '/sh_scripts'
    if args.datadir != '_DDDD_':
        data['def_data_dir'] = args.datadir + '/data'
        data['def_tf_scripts_dir'] = args.datadir + '/tf_scripts'
        data['def_sh_scripts_dir'] = args.datadir + '/sh_scripts'
        data['base_instance_dir'] = args.datadir + '/base_instance'
    print_g_left('Default instance dir', 30, data['def_instance_dir'])
    print_g_left('Default data dir', 30,data['def_data_dir'])
    print_g_left('Base instance dir', 30, data['base_instance_dir'])
    print_g_left('Default tf_scripts dir', 30, data['def_tf_scripts_dir'])
    print_g_left('Default sh_scripts dir', 30, data['def_sh_scripts_dir'])
    return data

    if not create_dir(data['def_instance_dir']):
        sys.exit(1)
    if not create_dir(data['def_tf_scripts_dir']):
        sys.exit(1)
    if not create_dir(data['def_sh_scripts_dir']):
        sys.exit(1)
    if not create_dir(data['def_data_dir']):
        sys.exit(1)
    if not create_dir(data['base_instance_dir']):
        sys.exit(1)
    return data


def copy_scripts(data):
    """
    Copy the tf scripts in place.

    Parameters
    ----------
    data: dict
        The configuration data.
    args: namespace
        The command line namespace.

    Returns
    -------
        bool: True
    """
    operator_home = data['operator_home']
    base_instance_dir = data['base_instance_dir']
    # if not copy_dir(operator_home + '/create_instance/base_instance', base_instance_dir):
    if not copy_dir(os.path.join(operator_home, create_instance_source, 'base_instance'), base_instance_dir):
        print_g('Failed to copy %s' % base_instance_dir)
        sys.exit(1)
    def_tf_scripts_dir = data['def_tf_scripts_dir']
    # if not copy_dir(operator_home + '/create_instance/tf_scripts', def_tf_scripts_dir):
    if not copy_dir(os.path.join(operator_home, create_instance_source, 'tf_scripts'), def_tf_scripts_dir):
        print_g('Failed to copy %s' % def_tf_scripts_dir)
        sys.exit(1)
    def_sh_scripts_dir = data['def_sh_scripts_dir']
    # if not copy_dir(operator_home + '/create_instance/sh_scripts', def_sh_scripts_dir):
    if not copy_dir(os.path.join(operator_home, create_instance_source, 'sh_scripts'), def_sh_scripts_dir):
        print_g('Failed to copy %s' % def_sh_scripts_dir)
        sys.exit(1)
    return True


def update_public_ip(data, public_ip):
    """
    Update the script for public or private ip.

    Parameters
    ----------
    data: dict
        The configuration data.
    public_ip: bool
        If True set for public ip.

    Returns
    -------
        bool: True
    """
    operator_home = data['operator_home']
    base_instance_dir = data['base_instance_dir']
    tf_scripts_dir = data['def_tf_scripts_dir']
    api_key = tf_scripts_dir + '/api_key.tf'
    rsa_key = tf_scripts_dir + '/rsa_key.tf'
    rsa_pub_key = tf_scripts_dir + '/rsa_pub_key.tf'
    output_b = base_instance_dir + '/output.tf'
    output_t = tf_scripts_dir + '/output.tf'
    main_b = base_instance_dir + '/main.tf'
    iptype = 'public' if public_ip else 'private'
    print_g('operator home     %s' % operator_home, term=False)
    print_g('base instance dir %s' % base_instance_dir, term=False)
    print_g('api key           %s' % api_key, term=False)
    print_g('rsa key           %s' % rsa_key, term=False)
    print_g('rsa_pub key       %s' % rsa_pub_key, term=False)
    print_g('output b          %s' % output_b, term=False)
    print_g('main b            %s' % main_b, term=False)
    print_g('iptype            %s' % iptype, term=False)

    #
    # tf_scripts/api_key
    with open(api_key, 'r+') as fx:
        api_text = fx.read()
        api_text = re.sub('XXXX', iptype, api_text)
        fx.seek(0)
        fx.write(api_text)
        print_g('api text: %s' % api_text, term=False)
        fx.truncate()
    #
    # tf_scripts/rsa_key
    with open(rsa_key, 'r+') as fx:
        rsa_text = fx.read()
        rsa_text = re.sub('XXXX', iptype, rsa_text)
        fx.seek(0)
        fx.write(rsa_text)
        print_g('api text: %s' % rsa_text, term=False)
        fx.truncate()
    #
    # tf_scripts/rsa_pub_key
    with open(rsa_pub_key, 'r+') as fx:
        rsa_pub_text = fx.read()
        rsa_pub_text = re.sub('XXXX', iptype, rsa_pub_text)
        fx.seek(0)
        fx.write(rsa_pub_text)
        print_g('api text: %s' % rsa_pub_text, term=False)
        fx.truncate()
    #
    # base_instance/main
    with open(main_b, 'r+') as fx:
        main_text = fx.read()
        main_text = re.sub('XXXX', iptype, main_text)
        fx.seek(0)
        fx.write(main_text)
        print_g('main text: %s' % main_text, term=False)
        fx.truncate()
    #
    # output public ip if one available
    if public_ip:
        #
        # base_instance/output
        with open(output_b, 'r+') as fx:
            output_text = fx.read()
            output_text = re.sub('//XXXX', '', output_text)
            fx.seek(0)
            fx.write(output_text)
            print_g('output text: %s' % output_text, term=False)
            fx.truncate()
        #
        # tf_scripts/output
        with open(output_t, 'r+') as fx:
            output_text = fx.read()
            output_text = re.sub('//XXXX', '', output_text)
            fx.seek(0)
            fx.write(output_text)
            print_g('output text: %s' % output_text, term=False)
            fx.truncate()
    return True


def update_flex(data):
    """
    Update the terraform scripts for usage with Flex shapes.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        bool: True
    """
    #
    # tf_scripts/main.tf
    base_instance_dir = data['base_instance_dir']
    tf_scripts_dir = data['def_tf_scripts_dir']
    main_t = tf_scripts_dir + '/main.tf'
    main_b = base_instance_dir + '/main.tf'
    with open(main_t, 'r+') as fx:
        output_text = fx.read()
        output_text = re.sub('//YYYY', '', output_text)
        fx.seek(0)
        fx.write(output_text)
        print_g('output text: %s' % output_text, term=False)
        fx.truncate()
    #
    # base_instance/main.tf
    with open(main_b, 'r+') as fx:
        output_text = fx.read()
        output_text = re.sub('//YYYY', '', output_text)
        fx.seek(0)
        fx.write(output_text)
        print_g('output text: %s' % output_text, term=False)
        fx.truncate()
    return True


def get_oci_config(data, args):
    """
    Get the oci configuration.

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
    cfg_dict = get_configdata(args.profile, args.configfile)
    print_g('\nConfiguration:\n-------------')
    for k, v in cfg_dict.items():
        print_g_left(k, 30, v)
    data['oci_config'] = cfg_dict
    return data


def get_instance_compartment(data):
    """
    Get the compartment data.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the configuration data.
    """
    _ = _clear()
    print_g('Compartment.\n', term=True)
    instance_compartment = select_compartment(data['oci_config'], "Select compartment for the instance.")
    print_g(instance_compartment, term=False)
    print_g('Selected compartment: %s\n' % instance_compartment.name)
    data['compartment'] = instance_compartment
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    return data


def get_availability_domain(data):
    """
    Get the availablility domain data.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the configuration data.
    """
    _ = _clear()
    print_g('Availability domain.\n', term=True)
    availability_domain = select_availability_domain(data['oci_config'], data['compartment'].id)
    print_g(availability_domain, term=False)
    print_g('Selected availability domain: %s\n' % availability_domain.name)
    data['availability_domain'] = availability_domain.name
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    return data


def get_network_compartment(data):
    """
    Get the network compartment.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the configuration data.
    """
    _ = _clear()
    print_g('Network compartment.\n', term=True)
    network_compartment = select_compartment(data['oci_config'], "Select compartment for the network.")
    print_g(network_compartment, term=False)
    print_g('Selected network compartment: %s\n' % network_compartment.name)
    data['network_compartment'] = network_compartment
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    return data


def get_vcn(data):
    """
    Get the VCN data.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the configuration data.
    """
    _ = _clear()
    print_g('Virtual cloud network.\n', term=True)
    vcn = select_vcn(data['oci_config'], data['network_compartment'].id)
    data['vcn'] = vcn
    print_g(vcn, term=False)
    print_g('Selected VCN: %s\n' % vcn.display_name)
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    return data


def get_subnet(data):
    """
    Get the subnet data.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the configuration data.
    """
    _ = _clear()
    print_g('Subnet.\n', term=True)
    subnet = select_subnet(data['oci_config'], data['network_compartment'].id, vcn_id=data['vcn'].id)
    data['subnet'] = subnet
    print_g(subnet, term=False)
    print_g('Selected subnet: %s\n' % subnet.display_name)
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    return data


def get_public_ip():
    """
    Request for public ip.

    Returns
    -------
    bool: true or false.
    """
    _ = _clear()
    return True if _read_yn('Assign a public IPv4 address?') else False


def get_image(data):
    """
    Get the image data.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the configuration data.
    """
    _ = _clear()
    print_g('Image.\n', term=True)
    data['image'] = select_image(data['oci_config'], data['compartment'].id)
    print_g(data['image'].id, term=False)
    print_g('Selected image: %s\n' % data['image'].display_name)
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    return data


def get_shape(data):
    """
    Get the instance shape.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the configuration data.
    """
    _ = _clear()
    print_g('Shape.\n', term=True)
    data['shape'] = select_shape(data['oci_config'], data['image'].id)
    print_g(data['shape'], term=False)
    print_g('Selected shape: %s\n' % data['shape'].shape)
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    return data


def get_flex_data(data):
    """
    Get the Flex shape data.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the configuration data.
    """
    _ = _clear()
    print_g('Flex shape data.\n', term=True)
    #
    # memory
    data['instance_flex_memory_in_gbs'] = _read_nb('Memory in GB', default_val=4, max_val=256)
    print_g(data['instance_flex_memory_in_gbs'], term=False)
    print_g('Selected memory size: %dGB' % data['instance_flex_memory_in_gbs'])
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    #
    # cpus
    data['instance_flex_ocpus'] = _read_nb('Number of OCPUs', default_val=2, max_val=64)
    print_g(data['instance_flex_ocpus'], term=False)
    print_g('Selected number of OCPUs: %d' % data['instance_flex_ocpus'])
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    #
    return data


def get_boot_volume_size(data):
    """
    Get the size of the boot volume in GigaBytes.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        dict: the configuration data.
    """
    _ = _clear()
    print_g('Boot Volume Size in GigaBytes', term=True)
    data['boot_volume_size_in_gbs'] = _read_nb('Boot Volume Size', default_val=51, max_val=2048)
    print_g(data['boot_volume_size_in_gbs'], term=False)
    print_g('Selected boot volume size: %dGB' % data['boot_volume_size_in_gbs'])
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    #
    return data

def print_config_data(xx):
    """
    Print dict.

    Parameters
    ----------
    xx: dict
        The data to print.

    Returns
    -------
        No return value.
    """
    for k,v in xx.items():
        print('%30s: %s' % (k,v))


def write_scripts(data):
    """
    Write the scripts.
    Parameters
    ----------
    data: the configuration data.

    Returns
    -------
        No return value.
    """
    def_log_dir = data['def_instance_dir']
    print_g('Run\n'
            'terraform -chdir=%s init\n'
            'terraform -chdir=%s validate\n'
            'terraform -chdir=%s plan -var-file=%s\n'
            'terraform -chdir=%s apply -var-file=%s -auto-approve | tee %s/creation.log\n'
            'terraform -chdir=%s destroy -var-file=%s -auto-approve'
            % (data['def_tf_scripts_dir'],
               data['def_tf_scripts_dir'],
               data['def_tf_scripts_dir'], data['tfvarsfile'],
               data['def_tf_scripts_dir'], data['tfvarsfile'], def_log_dir,
               data['def_tf_scripts_dir'], data['tfvarsfile']))
    create_script = data['def_instance_dir'] + '/create'
    if not write_bash(create_script, 'terraform -chdir=%s init'
                                     % data['def_tf_scripts_dir']):
        sys.exit(1)
    if not write_bash(create_script, 'terraform -chdir=%s validate'
                                     % data['def_tf_scripts_dir']):
        sys.exit(1)
    if not write_bash(create_script, 'terraform -chdir=%s plan --var-file=%s'
                                     % (data['def_tf_scripts_dir'], data['tfvarsfile'])):
        sys.exit(1)
    if not write_bash(create_script, 'terraform -chdir=%s apply --var-file=%s -auto-approve | tee %s/creation.log'
                                     % (data['def_tf_scripts_dir'], data['tfvarsfile'], def_log_dir)):
        sys.exit(1)
    destroy_script = data['def_instance_dir'] + '/destroy'
    if not write_bash(destroy_script, 'terraform -chdir=%s destroy --var-file=%s -auto-approve | tee %s/destruction.log'
                                      % (data['def_tf_scripts_dir'], data['tfvarsfile'], def_log_dir)):
        sys.exit(1)
    print_g('\nor\n%s\n%s' % (create_script, destroy_script))


def current_data(tfvars, instance):
    head = 'Compartment: %s' % instance.get_compartment_name()
    # print('%s\n%s' % (head, '-' * len(head)))
    selection = ['availability domain: ' + tfvars['availability_domain'],
                 'subnet:              ' + instance.get_subnet_name(tfvars['subnet_ocid']),
                 'image:               ' + instance.get_image_name(tfvars['source_ocid']),
                 'shape:               ' + tfvars['shape'],
                 'boot volume size:    ' + tfvars['boot_volume_size_in_gbs']]
    if 'instance_flex_memory_in_gbs' in tfvars:
        selection.extend(['flex number of cpus: ' + tfvars['instance_flex_ocpus'],
                          'flex memory in gbs:  ' + tfvars['instance_flex_memory_in_gbs']])
    return head, selection

def main():
    """
    Configure auto tests.

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
    args_dict = vars(args)
    #
    # clear
    _ = _clear()
    print('%s'% args_dict)
    #
    # instance name to create
    instance_display_name = args.display_name if args.display_name is not None else _get_display_name()
    #
    # initialise logging
    logging.basicConfig(filename=default_log + instance_display_name + '.log',
                        level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s (%(module)s:%(lineno)s) - %(message)s')
    #
    # init
    print_g('Collecting instance data for %s.....\n' % instance_display_name)
    config_data = InstanceData(instance_display_name, args)
    #
    # current user data
    # config_data = get_user_data(config_data)
    #
    # show initial data
    # print_g_left('Display name', 30, config_data.data['instance_display_name'])
    print_g_left('exec dir', 30, config_data.data['exec_dir'], term=False)
    print_g_left('base exec dir', 30, config_data.data['base_exec_dir'], term=False)
    print_g_left('Username', 30, config_data.data['operator'])
    print_g_left('Home dir', 30, config_data.data['operator_home'])
    print_g_left('Default instance dir', 30, config_data.data['def_instance_dir'])
    print_g_left('Default data dir', 30,config_data.data['def_data_dir'])
    print_g_left('Base instance dir', 30, config_data.data['base_instance_dir'])
    print_g_left('Default tf_scripts dir', 30, config_data.data['def_tf_scripts_dir'])
    print_g_left('Default sh_scripts dir', 30, config_data.data['def_sh_scripts_dir'])
    print_g('\nConfiguration:\n-------------')
    for k, v in config_data.data['oci_config'].items():
        print_g_left(k, 30, v)
    print_g_left('tfvars file', 30, config_data.data['tfvarsfile'])
    #
    # Get configuration data from config file.
    # config_data = get_oci_config(config_data, args)
    if not _read_yn('Continue?', default_yn=True):
        sys.exit(1)
    #
    # Get the current instance var file data
    try:
        with TerraformData(config_data.data['tfvarsfile']) as atfv:
            tfvars_data = atfv.jsondata
    except Exception as e:
        print_g('***ERROR*** %s' % str(e), term=True)
        sys.exit(1)
    #
    # show terraform data
    for k,v in updatable_parameters.items():
        if v in tfvars_data:
            print_g_left(k, 30, tfvars_data[v])
    #
    # compartment ocid
    config_data.set_compartment_id(tfvars_data['compartment_ocid'])
    #
    # availability_domains
    config_data.set_availability_domains(config_data.data['compartment_ocid'])
    #
    # images
    config_data.set_image_list(config_data.data['compartment_ocid'])
    #
    print(pformat(config_data.data, indent=4))
    print(pformat(tfvars_data, indent=4))
    # print(pformat(config_data.compartments, indent=4))
    # print(pformat(config_data.subnets, indent=4))
    # print(pformat(config_data.availability_domains, indent=4))
    # print(pformat(config_data.image_list, indent=4))
    # print(pformat(config_data.shape_list, indent=4))
    #
    sys.exit(1)
    #
    # images
    # image_list = get_images(config_data['oci_config'], tfvars_data['compartment_ocid'])
    #
    # current data
    # compartment_name = get_compartment_name(compartment_list, tfvars_data['compartment_ocid'])
    #
    # subnet
    # subnet_name = get_subnet_name(subnet_list, tfvars_data['subnet_ocid'])
    #
    # image
    # image_name = get_image_name(image_list, tfvars_data['source_ocid'])
    #
    print_g_left('Instance name', 30, config_data.data['instance_display_name'])
    print_g_left('Compartment', 30, config_data.data)
    instance_data = {'compartment': {'name': compartment_name, 'ocid': tfvars_data['compartment_ocid']}}
    instance_data['availability_domain'] = tfvars_data['availability_domain']
    instance_data['subnet'] = {'name': subnet_name, 'ocid': tfvars_data['subnet_ocid']}
    instance_data['image'] = {'name': image_name, 'ocid': tfvars_data['source_ocid']}
    instance_data['shape'] = {'name': tfvars_data['shape']}
    instance_data['boot_volume_size_in_gbs'] = {'name': tfvars_data['boot_volume_size_in_gbs']}
    if 'instance_flex_memory_in_gbs' in tfvars_data:
        instance_data['instance_flex_memory_in_gbs'] = {'name': tfvars_data['instance_flex_memory_in_gbs']}
        instance_data['instance_flex_ocpus'] = {'name': tfvars_data['instance_flex_ocpus']}
    #
    print_g_left('compartment', 30, '%-40s %s' % (instance_data['compartment']['name'], instance_data['compartment']['ocid']))
    print_g_left('availability domain', 30, instance_data['availability_domain'])
    print_g_left('subnet', 30, '%-40s %s' % (instance_data['subnet']['name'], instance_data['subnet']['ocid']))
    print_g_left('image', 30, '%-40s %s' % (instance_data['image']['name'], instance_data['image']['ocid']))
    print_g_left('shape', 30, instance_data['shape']['name'])
    print_g_left('boot volume size', 30, instance_data['boot_volume_size_in_gbs']['name'])
    if 'instance_flex_memory_in_gbs' in instance_data:
        print_g_left('memory in gbs', 30, str(instance_data['instance_flex_memory_in_gbs']['name']))
        print_g_left('number of cpus', 30, str(instance_data['instance_flex_ocpus']['name']))

    #
    sys.exit(1)
    #
    # compose var file.
    try:
        with TerraformData(config_data['tfvarsfile']) as atfv:
            _ = atfv.update_json_with_config(config_data['oci_config'])
            print_g('Updated variables with config data', term=True)
            _ = atfv.update_user(instance_display_name)
            print_g('Updated variables with operator data', term=True)
    except Exception as e:
        print_g('***ERROR*** %s' % str(e), term=True)
    #
    # Instance compartment
    config_data = get_instance_compartment(config_data)
    image_data['compartment_ocid'] = config_data['compartment'].id
    # _ = _clear()
    #
    # Availability domain
    config_data = get_availability_domain(config_data)
    image_data['availability_domain'] = config_data['availability_domain']
    #
    # Network compartment
    config_data = get_network_compartment(config_data)
    #
    # Virtual Cloud Network
    config_data = get_vcn(config_data)
    #
    # Subnets
    config_data = get_subnet(config_data)
    image_data['subnet_ocid'] = config_data['subnet'].id
    #
    # Public ip
    # Public ip
    image_data['assign_public_ip'] = get_public_ip()
    #
    # update public ip
    _ = update_public_ip(config_data, image_data['assign_public_ip'])
    #
    # Type
    image_data['source_type'] = 'image'
    #
    # Images
    config_data = get_image(config_data)
    image_data['source_ocid'] = config_data['image'].id
    #
    # Shape
    config_data = get_shape(config_data)
    image_data['shape'] = config_data['shape'].shape
    #
    # Boot volume size
    config_data = get_boot_volume_size(config_data)
    image_data['boot_volume_size_in_gbs'] = config_data['boot_volume_size_in_gbs']
    #
    # is shape Flex?
    if bool(re.search('Flex', image_data['shape'])):
        config_data = get_flex_data(config_data)
        image_data['instance_flex_memory_in_gbs'] = config_data['instance_flex_memory_in_gbs']
        image_data['instance_flex_ocpus'] = config_data['instance_flex_ocpus']
        _ = update_flex(config_data)
    #
    # get generic variables
    gen_data = get_generic_data()
    gen_data['instance_display_name'] = instance_display_name
    #
    # various data
    varia_data = {'vnic_display_name': instance_display_name}
    try:
        with TerraformData(config_data['tfvarsfile']) as atfv:
            _ = atfv.update_varia(varia_data)
            print_g('Updated various data.')
    except Exception as e:
        print_g('***ERROR*** %s' % str(e))
    #
    # update tfvars file
    try:
        with TerraformData(config_data['tfvarsfile']) as atfv:
            _ = atfv.update_image(image_data)
            print_g('Updated variables with image data.')
            _ = atfv.update_gen_data(gen_data)
            print_g('Updated variables with generic data.')
    except Exception as e:
        print_g('***ERROR*** %s' % str(e))
    #
    print_g('Wrote configuration to %s' % config_data['tfvarsfile'])
    #
    write_scripts(config_data)
    sys.exit(0)


if __name__ == "__main__":
    sys.exit(main())
