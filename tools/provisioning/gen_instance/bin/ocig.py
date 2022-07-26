#!/bin/python3
# Copyright (c) 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import argparse
import configparser
import logging
import oci as sdk
import os
from subprocess import call
import sys
import termios
import tty
from io import StringIO

lc_all='en_US.UTF8'
compartment_prefix = 'ocid1.compartment.'
_logger = logging.getLogger(__name__)


def def_list_profiles_parser(p_parser):
    """
    Define the list profiles subparser.

    Parameters
    ----------
    p_parser: subparsers.

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    list_profiles_parser = p_parser.add_parser('list-profiles',
                                               description = 'Lists profiles.')
    list_profiles_parser.add_argument('-c', '--config',
                                      action='store',
                                      dest='configfile',
                                      default='~/.oci/config',
                                      help='The cli/sdk config file, default is ~/.oci/config.')
    return  list_profiles_parser


def def_list_instances_parser(l_parser):
    """
    Define the list instances subparser.

    Parameters
    ----------
    l_parser: subparsers.

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    list_instances_parser = l_parser.add_parser('list-instances',
                                                description='Lists instances.')
    list_instances_parser.add_argument('-c', '--compartment',
                                       action='store',
                                       dest='compartment',
                                       required=True,
                                       help='The compartment name or ocid to list the instances.')
    list_instances_parser.add_argument('-p', '--profile',
                                       action='store',
                                       dest='profile',
                                       default='DEFAULT',
                                       help='The profile id from the config file')
    list_instances_parser.add_argument('--config',
                                       action='store',
                                       dest='configfile',
                                       default='~/.oci/config',
                                       help='The cli/sdk config file, default is ~/.oci/config.')
    list_instances_parser.add_argument('-f', '--fields',
                                       action='store',
                                       dest='fields',
                                       help='Comma separated list of desired fields; display_name and lifecycle '
                                            'state are always included; other valid fields are: ocid, '
                                            'availability_domain, shape, memory, cpus, bandwidth, cpu_type, created_by, '
                                            'created_on, image_id; this parameters overrules the details flag.',
                                       type=instancecsv2list)
    list_instances_parser.add_argument('-d', '--details',
                                       action='store_true',
                                       default=False,
                                       help='Display detailed data, all possible fields defined in the --fields option.')
    return list_instances_parser


def def_list_volumes_parser(v_parser):
    """
    Define the list volumes subparser

    Parameters
    ----------
    v_parser: subparsers

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    list_volumes_parser = v_parser.add_parser('list-volumes',
                                              description='List volumes.')
    list_volumes_parser.add_argument('-c', '--compartment',
                                       action='store',
                                       dest='compartment',
                                       required=True,
                                       help='The compartment name or ocid to list the volumes.')
    list_volumes_parser.add_argument('-p', '--profile',
                                       action='store',
                                       dest='profile',
                                       default='DEFAULT',
                                       help='The profile id from the config file')
    list_volumes_parser.add_argument('--config',
                                       action='store',
                                       dest='configfile',
                                       default='~/.oci/config',
                                       help='The cli/sdk config file, default is ~/.oci/config.')
    list_volumes_parser.add_argument('-f', '--fields',
                                       action='store',
                                       dest='fields',
                                     # __GT__ update
                                       help='Comma separated list of desired fields; display_name and lifecycle '
                                            'state are always included; other valid fields are: ocid, '
                                            'availability_domain, size_gbs, size_mbs, volume_group_id, created_by, '
                                            'created_on; this parameters overrules the details flag.',
                                       type=volumescsv2list)
    list_volumes_parser.add_argument('-d', '--details',
                                       action='store_true',
                                       default=False,
                                       help='Display detailed data, all possible fields defined in the --fields option.')
    return list_volumes_parser

def instancecsv2list(csv):
    """
    Convert csv to list and validate.

    Parameters
    ----------
    csv: str
        The csv.

    Returns
    -------
        list: the converted csv.
    """
    choices = ['ocid', 'availability_domain', 'shape', 'memory', 'cpus', 'bandwidth', 'cpu_type', 'created_by', 'created_on', 'image_id']
    fields = csv.split(',')
    for f in fields:
        if f not in choices:
            sys.exit('Invalid field %s' % f)
    return csv


def volumescsv2list(csv):
    """
    Convert csv to list and validate.

    Parameters
    ----------
    csv: str
        The csv.

    Returns
    -------
        list: the converted csv.
    """
    choices = ['ocid', 'availability_domain', 'size_gbs', 'size_mbs', 'volume_group_id', 'created_by', 'created_on']
    fields = csv.split(',')
    for f in fields:
        if f not in choices:
            sys.exit('Invalid field %s' % f)
    return csv

def get_arg_parser():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args()).

    Returns
    -------
        The argparse namespace.
    """
    parser = argparse.ArgumentParser(prog='ocig',
                                     description='oci-sdk shortcuts.')

    subparser = parser.add_subparsers(dest='command')
    #
    # usage
    subparser.add_parser('usage', description='Displays usage')
    #
    # profiles
    list_profiles__parser = def_list_profiles_parser(subparser)
    #
    # instances
    list_instances_parser = def_list_instances_parser(subparser)
    #
    # volumes
    list_volumes_parser = def_list_volumes_parser(subparser)
    return parser


def test_config_file(configfile):
    """
    Test if oci-sdk config file exists.

    Parameters
    ----------
    configfile: full path of the configfile.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    if os.path.exists(configfile):
        return True
    print_g('%s configfile not found.')
    sys.exit(1)


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


def _clear():
    """
    Clear screen.

    Returns
    -------
        bool: True
    """
    _ = call('clear' if os.name == 'posix' else 'cls')
    return True


class PrintTable():
    """
    Print a list of lists as a table on stdout.
    """

    def __init__(self, sometable, header=True):
        """
        Print table initialisation.

        Parameters
        ----------
        sometable: list
            list of lists.
        header: bool
            if True, the first line is considered the header.
        """
        self.result_table = StringIO()
        self.table = sometable
        self.use_header = header
        self.nb_columns = 0
        self.table_width = 1
        self.column_lengths = self.column_widths()

    def column_widths(self, max_len=80):
        """
        Find the column lenghs.

        Parameters:
        ----------
        max_len: int
            maximum length of a column, data is truncated if longer; default is 80.

        Returns
        -------
            list: column lenghts +2
        """
        column_length = list()
        for somefield in self.table[0]:
            column_length.append(len(somefield))
        for someline in self.table:
            for i in range(len(someline)):
                somelength = len(someline[i])
                column_length[i] = somelength if min(somelength, max_len) > column_length[i] else column_length[i]
        for i in range(len(column_length)):
            column_length[i] += 2
            self.table_width += column_length[i] + 1
        # self.table_width += 1
        return column_length

    def write_column(self, value, length):
        """
        Write a single value with length to the result table.

        Parameters
        ----------
        value: str
            The value.
        length: int
            The maximum length.

        Returns
        -------
            No return value.
        """
        # truncate if necessary.
        if len(value) > length:
            value = value[:length-5] + '...'
        self.result_table.write(value.center(length))
        self.result_table.write('|')

    def write_line(self, tableline):
        """
        Write a line to the result table.

        Parameters
        ----------
        tableline: list
            The table line.

        Returns
        -------
            No return value.
        """
        self.result_table.write('|')
        for i in range(len(tableline)):
            self.write_column(tableline[i], self.column_lengths[i])
        self.result_table.write('\n')

    def compose_table(self):
        """
        Compose the table as a string.

        Returns
        -------
            No return value.
        """
        first_line = 0
        if self.use_header:
            self.write_line(self.table[0])
            self.result_table.write('-'*self.table_width)
            self.result_table.write('\n')
            first_line = 1
        for l in range(first_line, len(self.table)):
            self.write_line(self.table[l])

    def print_table(self):
        """
        Write the table to stdout.

        Returns
        -------
            No return value.
        """
        self.compose_table()
        print_g('%s\n' % self.result_table.getvalue())


class SdkConfig():
    """
    oci-sdk configuration file.
    """
    def __init__(self, sdk_configfile, sdk_profile):
        """
        Initialise config.

        Parameters
        ----------
        sdk_configfile: str
            The path of of the sdk config file.
        sdk_profile: str
            The requested profile.
        """
        self.configfile = sdk_configfile
        self.profile = sdk_profile

    def get_sdk_config_file_path(self):
        """
        Generate the full path of the configfile if a relative one is provided.

        Returns
        -------
            The full path of the config file.
        """
        sdkconfigfile = self.configfile
        if self.configfile.startswith('~/'):
            sdkconfigfile = os.path.expanduser('~') + self.configfile[1:]
        return sdkconfigfile


    def get_configdata(self):
        """
        Read the oci sdk/cli config file.

        Returns
        -------
            dict: the config data.
        """
        sdkconfigfile = self.get_sdk_config_file_path()
        if test_config_file(sdkconfigfile):
            config = sdk.config.from_file(file_location=sdkconfigfile, profile_name=self.profile)
            return config
        sys.exit(1)

    def get_oci_config(self):
        """
        Get the oci configuration.

        Returns
        -------
            dict: the configuration data.
        """
        cfg_dict = self.get_configdata()
        return cfg_dict

    def get_sdk_config(self):
        """

        Returns
        -------

        """
        config = configparser.RawConfigParser()
        config.read(self.get_sdk_config_file_path())
        return config


class ThisCompartment():
    """
    The compartment.
    """
    def __init__(self, someargs):
        """
        Initialise the compartment.
        Parameters
        ----------
        someargs: command line arguments.
        """
        self.configfile = someargs.configfile
        self.profile = someargs.profile
        self.config = SdkConfig(self.configfile, self.profile).get_configdata()
        self.compartment = someargs.compartment
        self.compartments = self.get_compartments()
        self.compartment_id = self.compartment_validator()

    def get_compartments(self):
        """
        Get the list of compartments in the tenancy for the provided profile.

        Returns
        -------
            list: the list of compartments.
        """
        try:
            oci_identity = sdk.identity.IdentityClient(self.config)
            return oci_identity.list_compartments(self.config['tenancy']).data
        except Exception as e:
            print_g('*** ERROR *** Failed to get compartment list: %s' % str(e))
            return None

    def compartment_validator(self):
        """
        Validate the compartment based on the cammandline argument 'compartment' which can be
        an ocid or a compartment name.

        Returns
        -------
            str: the compartment ocid if found, None otherwise.
        """
        # verify if compartment is a compartement ocid
        if self.compartment.startswith(compartment_prefix):
                return self.compartment
        # verify if comportment is a compartment name
        compartments = self.get_compartments()
        if compartments is not None:
            for a_compartment in compartments:
                if a_compartment.name == self.compartment:
                    return a_compartment.id
        return None

    def get_compartment_name(self):
        """
        Find the compartment name associated with an ocid.

        Returns
        -------
            str: the compartment name.
        """
        for a_compartment in self.compartments:
            if a_compartment.id == self.compartment_id:
                return a_compartment.name
        return None


class OciInstances():
    """

    """
    def __init__(self, compartment_id, someargs):
        self.compartment_id = compartment_id
        self.configfile = someargs.configfile
        self.profile = someargs.profile
        self.config = SdkConfig(self.configfile, self.profile).get_configdata()

    def get_instances(self):
        compute_client = sdk.core.ComputeClient(self.config)

        list_instances = compute_client.list_instances(
            compartment_id = self.compartment_id,
            sort_by='DISPLAYNAME',
            sort_order='ASC')
        return list_instances.data


class OciInstance():
    """

    """
    def __init__(self, instance_data):
        """
        One instance.

        Parameters
        ----------
        instance_data: oci.core.models.instance.Instance
        """
        self.data = instance_data

    def get_id(self):
        return self.data.id

    def get_image_id(self):
        return self.data.image_id

    def get_display_name(self):
        return self.data.display_name

    def get_availability_domain(self):
        return self.data.availability_domain

    def get_lifecycle_state(self):
        return self.data.lifecycle_state

    def get_shape(self):
        return self.data.shape

    def get_memory_in_gbs(self):
        return f'{self.data.shape_config.memory_in_gbs:.2f}'

    def get_networking_bandwidth_in_gbps(self):
        return f'{self.data.shape_config.networking_bandwidth_in_gbps:.2f}'

    def get_ocpus(self):
        return f'{self.data.shape_config.ocpus:.2f}'

    def get_processor_description(self):
        return self.data.shape_config.processor_description

    def get_created_by(self):
        return self.data.defined_tags['Oracle-Tags']['CreatedBy']

    def get_created_on(self):
        return self.data.defined_tags['Oracle-Tags']['CreatedOn']


def do_list_profiles(configfile, profile):
    """
    List the profiles available in the config file.
    Parameters
    ----------
    list_profile_args: namespace
        The command line arguments.

    Returns
    -------
        No return value.
    """
    sdk_config = SdkConfig(configfile, profile)
    config = sdk_config.get_sdk_config()
    print_g('Profiles defined in the config file %s' % configfile)
    print_g('-'*60)
    print_g('%-30s: Region' % 'Profile')
    print_g('-'*60)
    print_g('%-30s: %s' % ('DEFAULT', config['DEFAULT']['region']))
    for sect in config.sections():
        region_id = '-'
        if config.has_option(sect, 'region'):
            region_id = config.get(sect, 'region')
        print_g('%-30s: %s' % (sect, region_id))
    return config


def build_instances_table(instances, fields):

    valid_fields = ['name',
                    'state',
                    'availability_domain',
                    'shape',
                    'memory',
                    'cpus',
                    'bandwidth',
                    'cpu_type',
                    'created_by',
                    'created_on',
                    'ocid',
                    'image_id']
    field_values = {'name': 'get_display_name',
                    'state': 'get_lifecycle_state',
                    'availability_domain': 'get_availability_domain',
                    'shape': 'get_shape',
                    'memory': 'get_memory_in_gbs',
                    'cpus': 'get_ocpus',
                    'bandwidth': 'get_networking_bandwidth_in_gbps',
                    'cpu_type': 'get_processor_description',
                    'created_by': 'get_created_by',
                    'created_on': 'get_created_on',
                    'ocid': 'get_id',
                    'image_id': 'get_image_id'}
    # default fields
    fields_to_use = ['name',
                     'state']
    fields_list = [field.strip() for field in fields.split(',')]
    for f in fields_list:
        if f not in fields_to_use:
            fields_to_use.append(f)
    # header: capitalized field names
    header = list()
    for field in fields_to_use:
        header.append(' '.join(word.capitalize() for word in field.replace('_', ' ').split(' ')))
    # complete the table
    instances_data = list()
    instances_data.append(header)
    for instance in instances:
        instance_data = list()
        for field in fields_to_use:
            instance_data.append(getattr(instance, field_values[field])())
        instances_data.append(instance_data)
    return instances_data


def do_list_instances(list_instance_args):
    """

    Parameters
    ----------
    list_instance_args

    Returns
    -------
        No return value.
    """
    details_list = 'availability_domain,shape,memory,cpus,bandwidth,cpu_type,created_by,created_on,ocid,image_id'
    this_compartment = ThisCompartment(list_instance_args)
    comp_id = this_compartment.compartment_id
    comp_name = this_compartment.get_compartment_name()
    if bool(not(comp_id and comp_name)):
        sys.exit('Missing valid compartment')
    instances = OciInstances(comp_id, list_instance_args).get_instances()
    oci_instances = [ OciInstance(instance) for instance in instances]

    title = 'Instances in compartment %s for profile %s.' % (comp_name, list_instance_args.profile)
    print_g(title)
    print_g('-'*len(title))
    columns = 'name,state'
    if list_instance_args.fields:
        columns+=','
        columns+=list_instance_args.fields
    elif list_instance_args.details:
        columns += ','
        columns += details_list

    instances_data = build_instances_table(oci_instances, columns)
    instances_table = PrintTable(instances_data)
    instances_table.print_table()


def do_list_volumes(list_volumes_args):
    """

    Parameters
    ----------
    list_volumes_args

    Returns
    -------
        No return value.
    """
    details_list = ['ocid,availability_domain,size_gbs,size_mbs,volume_group_id,created_by,created_on']
    this_compartment = ThisCompartment(list_volumes_args)
    comp_id = this_compartment.compartment_id
    comp_name = this_compartment.get_compartment_name()
    if bool(not(comp_id and comp_name)):
        sys.exit('Missing valid compartment')


def main():
    """
    Main

    Returns
    -------
        int
            0 on success;
            1 on failure.
    """
    #
    # locale
    os.environ['LC_ALL'] = "%s" % lc_all
    #
    # clear
    _ = _clear()
    #
    # parse the commandline
    parser = get_arg_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    if args.command == 'usage':
        parser.print_help()
        return 0

    print(args)
    #
    # _ = _clear()
    #
    if not args.command:
        parser.print_help()
        return 1

    if args.command == 'usage':
        parser.print_help()
        return 0

    if args.command == 'list-profiles':
        _ = do_list_profiles(configfile=args.configfile, profile='DEFAULT')

    if args.command == 'list-instances':
        _ = do_list_instances(list_instance_args=args)

    if args.command == 'list-volumes':
        _ = do_list_instances(list_volumes_args=args)


if __name__ == "__main__":
    sys.exit(main())
