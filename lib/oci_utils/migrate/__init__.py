# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import sys
import termios
import tty

import yaml
from oci_utils.migrate.exception import OciMigrateException

# try:
#    import yaml
# except ImportError as e:
#    sys.stderr.write('\n  oci-image-migrate needs yaml module in order to '
#                     'load configuration\n  data and to analyse certain '
#                     'network configuration files. Install\n  it using the '
#                     'package manager (python-yaml) or via pip (pip3 install '
#                     'yaml.)\n')
#    sys.exit(1)

_oci_migrate_conf_file = '/etc/oci-utils/oci-migrate-conf.yaml'


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


def read_yn(prompt, yn=True):
    """
    Read yes or no form stdin, No being the default.

    Parameters
    ----------
        prompt: str
            The message.
        yn: bool
            Add (y/N) to the prompt if True.
    Returns
    -------
        bool: True on yes, False otherwise.
    """
    yn_prompt = prompt + ' '
    if yn:
        yn_prompt += ' (y/N) '
    sys.stdout.write(yn_prompt)
    yn = _getch()
    sys.stdout.write('\n')
    if yn.upper() == 'Y':
        return True
    else:
        return False


def exit_with_msg(msg, exit_code=1):
    """
    Post a message on stdout and exit.

    Parameters
    ----------
    msg: str
        The exit message.
    exit_code: int
        The exit code, default is 1.

    Returns
    -------
        No return value.
    """
    sys.stderr.write('\n  %s\n' % msg)
    exit(exit_code)


def pause_msg(msg=None):
    """
    Pause function.

    Parameters:
    ----------
    msg: str
        Eventual pause message.

    Returns
    -------
        No return value.
    """
    if os.environ.get('OCIPAUSE'):
        ban0 = '\n  Press a key to continue'
        if msg is not None:
            ban0 = '\n  %s' % msg + ban0
        _ = read_yn(ban0, False)


def console_msg(msg=None):
    """
    Writes a message to the console.

    Parameters:
    ----------
        msg: str
            The message
    Returns:
    -------
         No return value.
    """
    if msg is None:
        msg = 'Notification.'
    sys.stdout.write('\n  %s\n' % msg)


def bytes_to_hex(bs):
    return ''.join('%02x' % i for i in bs)


class OciMigrateConfParam(object):
    """
    Retrieve oci-image-migrate configuration data from the
    oci-image-migrate configuration file, in yaml format.
    """

    def __init__(self, yamlconf, tag):
        """
        Initialisation of the oci image migrate configuration retrieval.

        Parameters:
        ----------
            yamlconf: str
                The full path of the oci-image-migrate configuration file.
            tag: str
                The configuration structure to collect.
        """
        self._yc = yamlconf
        self._tg = tag

    def __enter__(self):
        """
        OciMigrateConfParam entry.
        """
        with open(self._yc, 'r') as f:
            self.confdata = yaml.load(f, Loader=yaml.SafeLoader)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        OciMigrateConfParam cleanup and exit.
        """
        pass

    def values(self):
        """
        Retrieve the configuration data.
        """
        return self.confdata[self._tg]


def get_config_data(key):
    """
    Get configuration data.

    Parameters:
    ----------
    key: str
        Key from the configuration data.

    Return:
       The configuration data, type varies.
    """
    try:
        with OciMigrateConfParam(_oci_migrate_conf_file, key) as config:
            return config.values()
    except Exception as e:
        raise OciMigrateException(
            'Failed to get data for %s: %s' % (key, str(e)))
