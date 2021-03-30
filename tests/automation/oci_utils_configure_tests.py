#!/bin/python3
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""Build the tf file for running one, multiple or all tests.
"""
import os
import shutil
import sys
import re
import tty
import termios


test_location = '../../'
default_log = 'list_of_tests.log'
inline_code = "cd /opt/oci-utils/ && /bin/sudo --preserve-env /bin/python3 /opt/oci-utils/setup.py oci_tests " \
              "--tests-base=/opt/oci-utils/tests/data --test-suite=tests.{} > /logs/run_{}.log 2>&1"


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
    # print_g('main f: %s' % main_f)
    test_f = os.path.join(template_dir, 'tf_test')
    # print_g('test f: %s' % test_f)
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
    apikey_f = os.path.join(template_dir, 'tf_apikey')
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


def main():
    #
    # name for the test.
    test_name = _from_stdin('provide a name for test suite: ')
    #
    # check directory with unittests.
    test_base = os.path.dirname(os.path.abspath(__file__))
    # print_g('test base: %s' % test_base)
    test_dir = os.path.join(test_base,'data/%s' % test_name)
    # print_g('test dir: %s' % test_dir)
    template_dir = os.path.join(test_base,'templates')
    # print_g('template dir: %s' % template_dir)
    test_location = os.path.join(test_base, '..')
    # print_g('directory with tests: %s' % test_location)
    #
    # compose the list of unittest files.
    test_list = get_test_list(test_location)
    #
    # select tests from the list.
    list_of_tests = compose_tests(test_list)
    #
    # need oci-sdk config?
    authentication = 'ip'
    auth_requirement = 'ip'
    if not _read_yn('Instance Principal Auth'):
        authentication = 'apikey'
        auth_requirement = 'apikey'
    if bool(list_of_tests):
        #
        # initialise test
        it = initialise_test(test_dir, template_dir)
        if it:
            for tst in list_of_tests:
                ct = create_test(test_dir, template_dir, tst, inline_code.format(tst, tst), authentication)
                if not ct:
                    return 1
            if auth_requirement == 'apikey':
                _ = add_apikey(test_dir, template_dir)
        else:
            print_g('Failed to create test.')
            return 1
    print_g('Created test %s' % test_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
