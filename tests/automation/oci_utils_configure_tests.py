#!/bin/python3
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""Build the tf file for running one, multiple or all tests.
"""
import argparse
import errno
import getpass
import inspect
import json
import logging
import os
import shutil
import sys
import re
import tty
import termios
from datetime import datetime
from subprocess import call

#
# locale
lc_all = 'en_US.UTF8'

software_tree = 'git_repo'
logdir = 'logs'
autotestdir = 'autotests'
tfvars_file = 'instance_variables.tfvars.json'
default_log = 'test_config.log'
config_log = ''

inline_code = "cd /opt/oci-utils/ && /bin/sudo --preserve-env /bin/python3 /opt/oci-utils/setup.py oci_tests " \
              "--tests-base=/opt/oci-utils/tests/data --test-suite=tests.{} > /logs/run_{}.log 2>&1"

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
    parser = argparse.ArgumentParser(description='Configure oci utils auto tests.')
    parser.add_argument('-n', '--name',
                        action='store',
                        dest='test_name',
                        default=None,
                        help="The name of the test suite.")
    parser.add_argument('-i', '--instance',
                        action='store',
                        dest='instance_display_name',
                        default=None,
                        help='The test instance.')
    parser.add_argument('-d', '--data-directory',
                        action='store',
                        dest='datadir',
                        default='_DDDD_',
                        help='Root directory with data for auto test run, default is ~/<instance_display_name>/data.')
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
        else:
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
    return some_list[select_index]


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


def _get_display_name():
    """
    Read instance display name from stdin.

    Returns
    -------
        str: the display name.
    """
    return _from_stdin('Instance Display Name: ')


def _get_test_name():
    """
    Read instance display name from stdin.

    Returns
    -------
        str: the display name.
    """
    return _from_stdin('Test Suite Name: ')


def _test_instance_defined(instance_name, root_dir):
    """
    Verify if instance_name is defined.

    Parameters
    ----------
    instance_name: str
        name of instance to test.
    root_dir: str
        user home directory

    Returns
    -------
        bool: True on success, False otherwise.
    """
    return os.path.isdir(os.path.join(root_dir, autotestdir, instance_name))


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


def get_test_list(location):
    """
    Get the list of available tests in directory location.

    Parameters
    ----------
    location: str
        (relative) path of the directory containing the tests.

    Returns
    -------
        list: of tests.
    """
    test_list = list()
    if os.path.exists(location):
        if os.path.isdir(location):
            for fn in os.listdir(location):
                if fn.startswith('test_'):
                    test_list.append(os.path.splitext(fn)[0])
    return test_list


def compose_tests(testlist):
    """
    Compose a list of tests to execute.

    Parameters
    ----------
    testlist: list
        List of available tests.

    Returns
    -------
        list: list of tests to execute.
    """
    list_of_tests = list()
    if not bool(testlist):
        print_g('No tests found')
        return None
    testlist_s = ['quit']
    testlist_s.extend(testlist)
    for tst in testlist_s:
        print_g('%4d %-30s' % (testlist_s.index(tst), tst))
    while 1 == 1:
        this_test = _select_from(testlist_s, 'Select test (<enter> or 0 to quit).')
        if this_test == 'quit':
            return list_of_tests
        list_of_tests.append(this_test)


def initialise_test(test_base, template_dir):
    """
    initialise test.

    Parameters
    ----------
    test_base: str
        Directory where test to be created.
    template_dir: str
        Directory with the templates.

    Returns
    -------
        bool: True on success, False otherwise
    """
    try:
        #
        # create dir
        os.makedirs(test_base, exist_ok=True)
        #
        # copy version
        shutil.copy(os.path.join(template_dir, 'tf_version'), os.path.join(test_base, 'terraform_version.tf'))
        #
        # copy data
        shutil.copy(os.path.join(template_dir, 'tf_data'), os.path.join(test_base, 'data.tf'))
        #
        # copy main heading
        shutil.copy(os.path.join(template_dir, 'tf_main'), os.path.join(test_base, 'main.tf'))
        #
        # copy output
        shutil.copy(os.path.join(template_dir, 'tf_output'), os.path.join(test_base, 'output.tf'))
        return True
    except Exception as e:
        print_g('%s' % str(e))
        return False


def copy_base_scripts(data):
    """
    Copy base instance to test env.

    Parameters
    ----------
    data: dict
        The configuration data

    Returns
    -------
        bool: True on success, False otherwise.
    """
    base_scripts = ['main.tf', 'data.tf', 'output.tf']
    try:
        #
        # create dir
        os.makedirs(data['base_instance_dir'], exist_ok=True)
        #
        # copy scripts
        for scr in base_scripts:
            shutil.copy(os.path.join(data['base_instance_location'], scr), os.path.join(data['base_instance_dir'], scr))
        return True
    except Exception as e:
        print_g('%s' % str(e))
        return False


def create_test(test_base, template_dir, name, test_codeline, authentication):
    """
    Add the specific test.

    Parameters
    ----------
    test_base: str
        Directory where test to be created.
    template_dir: str
        Directory with the templates.
    name: str
        Name of the test.
    test_codeline: str
        The unittest code line.
    authentication: str
        ip or apikey

    Returns
    -------
        bool: True on success, False otherwise.
    """
    main_f = os.path.join(test_base, 'main.tf')
    print_g40('main tf', main_f)
    test_f = os.path.join(template_dir, 'tf_test')
    print_g40('test tf', test_f)
    try:
        main_fd = open(main_f, "a")
        with open(test_f, "r") as test_fd:
            main_fd.write(os.linesep)
            for test_line in test_fd:
                if authentication == 'apikey':
                    res_line = test_line.replace('_TTTT_', name).replace('_SSSS_', test_codeline).replace('_BBBB_', 'null_resource.oci_sdk_config')
                else:
                    res_line = test_line.replace('_TTTT_', name).replace('_SSSS_', test_codeline).replace('_BBBB_', 'module.base_instance')
                if not res_line.startswith('//'):
                    main_fd.write(res_line)
                # print_g(res_line)
        return True
    except Exception as e:
        print_g('Failed to create test %s: %s' % (name, str(e)))
        return False
    finally:
        main_fd.close()


def add_apikey(test_base, template_dir):
    """
    Add the oci-sdk config.

    Parameters
    ----------
    test_base: str
        Directory where test to be created.
    template_dir: str
        Directory with the templates.

    Returns
    -------
        bool: True on success, False otherwise
    """
    main_f = os.path.join(test_base, 'main.tf')
    # print_g40('main tf', main_f)
    apikey_f = os.path.join(template_dir, 'tf_apikey')
    # print_g40('apikey tf', apikey_f)
    try:
        main_fd = open(main_f, "a")
        with open(apikey_f, "r") as apikey_fd:
            main_fd.write(os.linesep)
            for apikey_line in apikey_fd:
                if not apikey_line.startswith('//'):
                    main_fd.write(apikey_line)
                # print_g(res_line)
        return True
    except Exception as e:
        print_g('Failed to add apikey: %s' % str(e))
        return False
    finally:
        main_fd.close()


def init_struct(test_name, instance_name):
    """
    Initialise config struct.

    Parameters
    ----------
    test_name: str
        The test suite name
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
    data['test_name'] = test_name
    print_g40('Test', data['test_name'])
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


def get_test_env(data):
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
    # software tree root
    data['test_base'] = os.path.join(data['operator_home'], software_tree)
    print_g40('Software Tree', data['test_base'])
    #
    # tests root
    data['test_location'] = os.path.join(data['test_base'], 'tests')
    print_g40('Tests Source Location', data['test_location'])
    #
    # terraform template root
    data['template_dir'] = os.path.join(data['test_base'], 'tests', 'automation', 'templates')
    print_g40('Template Location', data['template_dir'])
    #
    # base instance destination
    data['base_instance_location'] = os.path.join(data['test_base'], 'tests', 'automation', 'data', 'base_instance')
    print_g40('Base_Instance Location', data['base_instance_location'])
    #
    # test instance root
    data['test_instance_dir'] = os.path.join(data['operator_home'], autotestdir, data['instance_display_name'])
    print_g40('Tests Instance Location', data['test_instance_dir'])
    #
    # test root
    data['test_dir'] = os.path.join(data['operator_home'], autotestdir, data['instance_display_name'], data['test_name'])
    print_g40('Tests Location', data['test_dir'])
    #
    # base instance destination
    data['base_instance_dir'] = os.path.join(data['operator_home'], autotestdir, data['instance_display_name'], 'base_instance')
    print_g40('Base_Instance', data['base_instance_dir'])
    #
    # scritps destination
    data['script_path'] = os.path.join(data['operator_home'], autotestdir, data['instance_display_name'], 'sh_scripts')
    print_g40('Scripts Location', data['script_path'])
    #
    # data - instance variables destination
    data['data_dir'] = os.path.join(data['operator_home'], autotestdir, data['instance_display_name'], 'data')
    data['tfvarsfile'] = os.path.join(data['data_dir'], tfvars_file)
    #
    # data - instance test variables destination
    data['data_test_dir'] = os.path.join(data['operator_home'], autotestdir, data['instance_display_name'], 'data')
    data['test_tfvarsfile'] = os.path.join(data['data_test_dir'], data['test_name'] + '_' + tfvars_file)
    print_g40('Test parameter file', data['test_tfvarsfile'])
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
    instance_display_name = data['instance_display_name']

    if args.datadir != '_DDDD_':
        data['data_dir'] = args.datadir + '/data'
    print_g40('Data Location', data['data_dir'])
    print_g40('Instance Variables', data['tfvarsfile'])
    if not _create_dir(data['test_instance_dir']):
        sys.exit(1)
    if not _create_dir(data['script_path']):
        sys.exit(1)
    if not _create_dir(data['data_dir']):
        sys.exit(1)
    if not _create_dir(data['data_test_dir']):
        sys.exit(1)
    if not _create_dir(data['base_instance_dir']):
        sys.exit(1)
    if not _create_dir(data['test_dir']):
        sys.exit(1)
    return data


def copy_tfvars(data):
    """
    Copy the variables file to the test environment.

    Parameters
    ----------
    data: dict
        The configuration data.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    try:
        shutil.copy(data['tfvarsfile'], data['test_tfvarsfile'])
        return True
    except Exception as e:
        print_g('%s' % str(e))
        return False


def is_flex_shape(data):
    """
    Verify if the instance is to be build from a flex shape.

    Parameters
    ----------
    data: dict
        The config data.

    Returns
    -------
        bool: True if flex shape, False if not
    """
    #
    # verify tfvars file for flex parameters
    try:
        with open(data['test_tfvarsfile'], 'rb') as tfvj:
            tfvars_data = json.load(tfvj)
        if 'instance_flex_memory_in_gbs' in tfvars_data and 'instance_flex_ocpus' in tfvars_data:
            #
            # is a flex shape
            return True
        else:
            #
            # is not a flex shape
            return False
    except Exception as e:
        print_g('Failed to read %s' % data['tfvarsfile'])
        raise 'tfvars file missing'


def is_public_ip(data):
    """
    Verify if a public ip is to be assigned.
    Parameters
    ----------
    data: dict
        The config data.

    Returns
    -------
        bool: True if public ip, False otherwise
    """
    #
    # verify tfvars file for public parameters
    try:
        with open(data['test_tfvarsfile'], 'rb') as tfvj:
            tfvars_data = json.load(tfvj)
        if 'assign_public_ip' in tfvars_data:
            if tfvars_data['assign_public_ip']:
                return True
        return False
    except Exception as e:
        print_g('Failed to read %s' % data['tfvarsfile'])
        raise 'tfvars file missing'


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
    tf_scripts_dir = data['template_dir']
    api_key = tf_scripts_dir + '/tf_apikey'
    output_b = base_instance_dir + '/output.tf'
    output_t = tf_scripts_dir + '/tf_output'
    main_b = base_instance_dir + '/main.tf'
    iptype = 'public' if public_ip else 'private'
    print_g('operator home     %s' % operator_home, term=False)
    print_g('base instance dir %s' % base_instance_dir, term=False)
    print_g('api key           %s' % api_key, term=False)
    print_g('output b          %s' % output_b, term=False)
    print_g('main b            %s' % main_b, term=False)
    print_g('iptype            %s' % iptype, term=False)

    #
    # tf_scripts/api_key
    with open(api_key, 'r+') as fx:
        api_text = fx.read()
        api_text = re.sub('PUBIP', iptype, api_text)
        fx.seek(0)
        fx.write(api_text)
        print_g('api text: %s' % api_text, term=False)
        fx.truncate()
    #
    # base_instance/main
    with open(main_b, 'r+') as fx:
        main_text = fx.read()
        main_text = re.sub('PUBIP', iptype, main_text)
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
            output_text = re.sub('//PUBIP', '', output_text)
            fx.seek(0)
            fx.write(output_text)
            print_g('output text: %s' % output_text, term=False)
            fx.truncate()
        #
        # tf_scripts/output
        with open(output_t, 'r+') as fx:
            output_text = fx.read()
            output_text = re.sub('//PUBIP', '', output_text)
            fx.seek(0)
            fx.write(output_text)
            print_g('output text: %s' % output_text, term=False)
            fx.truncate()
    return True


def update_for_flex(data):
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
    tf_scripts_dir = data['template_dir']
    main_t = tf_scripts_dir + '/tf_main'
    main_b = base_instance_dir + '/main.tf'
    with open(main_t, 'r+') as fx:
        output_text = fx.read()
        output_text = re.sub('//FLEX', '', output_text)
        fx.seek(0)
        fx.write(output_text)
        print_g('output text: %s' % output_text, term=False)
        fx.truncate()
    #
    # base_instance/main.tf
    with open(main_b, 'r+') as fx:
        output_text = fx.read()
        output_text = re.sub('//FLEX', '', output_text)
        fx.seek(0)
        fx.write(output_text)
        print_g('output text: %s' % output_text, term=False)
        fx.truncate()
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


def init_file(fn):
    """
    Initialise a flat file, i.e. erase and recreate if already exists.

    Parameters
    ----------
    fn: str
        The full path of the file.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    try:
        with open(fn, 'w') as f:
            pass
    except Exception as e:
        print_g('%s' % str(e))
        return False
    return True


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
    def_log_dir = data['operator_home']
    print_g('Run\n'
            'terraform -chdir=%s init\n'
            'terraform -chdir=%s validate\n'
            'terraform -chdir=%s plan -var-file=%s\n'
            'terraform -chdir=%s apply -var-file=%s -auto-approve | tee %s/creation.log\n'
            'terraform -chdir=%s destroy -var-file=%s -auto-approve'
            % (data['test_dir'],
               data['test_dir'],
               data['test_dir'], data['test_tfvarsfile'],
               data['test_dir'], data['test_tfvarsfile'], def_log_dir,
               data['test_dir'], data['test_tfvarsfile']))
    create_script = data['operator_home'] \
                    + '/' \
                    + autotestdir \
                    + '/%s_%s_create' % (data['instance_display_name'], data['test_name'])
    if not init_file(create_script):
        sys.exit(1)
    if not write_bash(create_script, 'terraform -chdir=%s init'
                                     % data['test_dir']):
        sys.exit(1)
    if not write_bash(create_script, 'terraform -chdir=%s validate'
                                     % data['test_dir']):
        sys.exit(1)
    if not write_bash(create_script, 'terraform -chdir=%s plan --var-file=%s'
                                     % (data['test_dir'], data['test_tfvarsfile'])):
        sys.exit(1)
    if not write_bash(create_script, 'terraform -chdir=%s apply --var-file=%s -auto-approve | tee %s/creation.log'
                                     % (data['test_dir'], data['test_tfvarsfile'], def_log_dir)):
        sys.exit(1)
    try:
        os.chmod(create_script, 0o755)
    except Exception as e:
        print_g('Failed to chmod 755 %s: %s' % (create_script, str(e)))
    #
    destroy_script = data['operator_home'] \
                     + '/'\
                     + autotestdir\
                     + '/%s_%s_destroy' % (data['instance_display_name'], data['test_name'])
    if not init_file(destroy_script):
        sys.exit(1)
    if not write_bash(destroy_script, 'terraform -chdir=%s destroy --var-file=%s -auto-approve | tee %s/destruction.log'
                                      % (data['test_dir'], data['test_tfvarsfile'], def_log_dir)):
        sys.exit(1)
    try:
        os.chmod(destroy_script, 0o755)
    except Exception as e:
        print_g('Failed to chmod 755 %s: %s' % (destroy_script, str(e)))
    print_g('\nor\n%s\n%s' % (create_script, destroy_script))


def main():
    """
    Configure tests.

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
    # name for the test.
    test_name = args.test_name if args.test_name is not None else _get_test_name()
    #
    # test instance
    instance_display_name = args.instance_display_name if args.instance_display_name is not None else _get_display_name()
    #
    # create log directory
    global config_log
    config_log = initialise_log(current_user_home, logdir, test_name)
    debug_log = initialise_log(current_user_home, logdir, test_name)
    #
    # user data
    print_g40('Current User', current_user)
    print_g40('Current User Home', current_user_home)
    #
    # initialise logging
    logging.basicConfig(filename=debug_log,
                        level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s (%(module)s:%(lineno)s) - %(message)s')
    #
    # exec dir
    config_data = init_struct(test_name, instance_display_name)
    #
    # current user
    config_data = get_user_data(config_data)
    #
    # test instance definition should be present
    if not _test_instance_defined(config_data['instance_display_name'], config_data['operator_home']):
        sys.exit('Instance definition %s does not exist.' % config_data['instance_display_name'])
    #
    # check directory with unittests.
    if not _test_softwaretree_defined(config_data['operator_home']):
        sys.exit('Software tree %s not present.' % software_tree)
    #
    # test environment
    config_data = get_test_env(config_data)
    #
    # create directories
    config_data = create_directories(config_data, args)
    #
    # copy base scripts
    if not copy_base_scripts(config_data):
        print_g('Failed to copy base_instance scripts.')
        return 1
    #
    # copy tfvars file to test env
    if not copy_tfvars(config_data):
        print_g('Failed to copy tfvars file to test')
        return 1
    #
    # flex shape?
    if is_flex_shape(config_data):
        if update_for_flex(config_data):
            print_g40('Flex shape', 'updated')
    #
    # update public ip
    _ = update_public_ip(config_data, is_public_ip(config_data))
    #
    # compose the list of unittest files.
    test_list = get_test_list(config_data['test_location'])
    # print_g40('Tests', ' ')
    # t = 1
    # for tst in test_list:
    #     print_g40('%s' % t, tst)
    #     t += 1
    #
    # select tests from the list.
    list_of_tests = compose_tests(test_list)
    print_g40('Tests', ' ')
    t = 1
    for tst in list_of_tests:
        print_g40('%s' % t, tst)
        t += 1
    #
    # need oci-sdk config?
    authentication = 'ip'
    auth_requirement = 'ip'
    if not _read_yn('Instance Principal Auth'):
        authentication = 'apikey'
        auth_requirement = 'apikey'
        if not  add_apikey(config_data['test_dir'], config_data['template_dir']):
            print_g('Failed to add api key code.')
            sys.exit(1)
    print_g40('Authentication', authentication)
    #
    if bool(list_of_tests):
        #
        # initialise test
        it = initialise_test(config_data['test_dir'], config_data['template_dir'])
        if it:
            if authentication == 'apikey':
                if not  add_apikey(config_data['test_dir'], config_data['template_dir']):
                    sys.exit('Failed to add api_key config')
            for tst in list_of_tests:
                ct = create_test(config_data['test_dir'], config_data['template_dir'], tst, inline_code.format(tst, tst), authentication)
                if not ct:
                    return 1
            if auth_requirement == 'apikey':
                _ = (config_data['test_dir'], config_data['template_dir'])
        else:
            print_g('Failed to create test.')
            return 1
    print_g('Created test %s' % test_name)
    write_scripts(config_data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
