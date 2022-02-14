#
# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.
#

import os
import os.path
import sys
from configparser import ConfigParser
import logging
import logging.handlers


__all__ = ['read_config',
           'SUDO_CMD',
           'CAT_CMD',
           'SH_CMD',
           'CP_CMD',
           'TOUCH_CMD',
           'CHMOD_CMD',
           'LSBLK_CMD',
           'MKDIR_CMD']


CAT_CMD = '/usr/bin/cat'
TOUCH_CMD = '/usr/bin/touch'
CHMOD_CMD = '/usr/bin/chmod'
RM_CMD = '/bin/rm'
MKDIR_CMD = '/bin/mkdir'
CP_CMD = '/bin/cp'
SH_CMD = '/bin/sh'
SUDO_CMD = '/bin/sudo'
VIRSH_CMD = '/usr/bin/virsh'
IP_CMD = '/usr/sbin/ip'
BRIDGE_CMD = '/sbin/bridge'
PARTED_CMD = '/sbin/parted'
MK_XFS_CMD = '/sbin/mkfs.xfs'
SYSTEMCTL_CMD = '/bin/systemctl'
LSBLK_CMD = '/bin/lsblk'


def print_choices(header, choices, sep="\n  "):
    """
    Display a list of options.

    Parameters
    ----------
    header: str
        The header.
    choices: list
        The list of options.
    sep: str
        The optinal separator.

    Returns
    -------
        No return value.
    """
    sys.stderr.write("{}{}{}", header, sep, sep.join(choices))
    sys.stderr.write('\n')


def _oci_utils_exception_hook(exctype, value, tb):
    logging.getLogger('oci-utils').critical('An unexpected error occurred: %s', str(value), stack_info=True)
    logging.getLogger('oci-utils').debug('An unexpected error occurred', exc_info=value, stack_info=True)


sys.excepthook = _oci_utils_exception_hook

# oci-utils config file
__oci_utils_conf_d = "/etc/oci-utils.conf.d"


def read_config():
    """
    Read the oci-utils config files; read all files present in
    /etc/oci-utils.conf.d in order and populate a configParser instance.
    If no configuration file is found the default values are used. See
    __oci_utils_defaults.

    Returns
    -------
        [ConfigParser]
            The oci_utils configuration.
    """
    _config = getattr(read_config, "oci_utils_config", None)
    if _config is not None:
        return _config

    oci_utils_config = ConfigParser()
    # assign default
    oci_utils_config.add_section('auth')
    oci_utils_config.set('auth', 'auth_method', 'auto')
    oci_utils_config.set('auth', 'oci_sdk_user', 'opc')
    oci_utils_config.add_section('iscsi')
    oci_utils_config.set('iscsi', 'enabled', 'true')
    oci_utils_config.set('iscsi', 'scan_interval', '60')
    oci_utils_config.set('iscsi', 'max_volumes', '8')
    oci_utils_config.set('iscsi', 'auto_resize', 'true')
    oci_utils_config.set('iscsi', 'auto_detach', 'true')
    oci_utils_config.set('iscsi', 'detach_retry', '5')
    oci_utils_config.add_section('vnic')
    oci_utils_config.set('vnic', 'enabled', 'true')
    oci_utils_config.set('vnic', 'scan_interval', '60')
    oci_utils_config.set('vnic', 'vf_net', 'false')
    oci_utils_config.add_section('public_ip')
    oci_utils_config.set('public_ip', 'enabled', 'true')
    oci_utils_config.set('public_ip', 'refresh_interval', '600')
    oci_utils_config.add_section('ocid')
    oci_utils_config.set('ocid', 'sdk_lock_timeout', '60') # not used anymore
    oci_utils_config.set('ocid', 'debug', 'False')

    setattr(read_config,"oci_utils_config", oci_utils_config)

    if not os.path.exists(__oci_utils_conf_d):
        return oci_utils_config

    conffiles = [os.path.join(__oci_utils_conf_d, f)
                 for f in os.listdir(__oci_utils_conf_d) if os.path.isfile(os.path.join(__oci_utils_conf_d, f))]
    oci_utils_config.read(conffiles)
    return oci_utils_config


class levelsFilter(logging.Filter):
    """
    By logging level filter.
    the filter will discard any record that do not have the right level
    """

    def __init__(self, levels, name=''):
        """
        Constructs a new filter
        levels : list of level (as int) that are accepted and will lead to
          the actual handling of the record
        """
        logging.Filter.__init__(self, name)
        self.levels = levels

    def filter(self, record):
        if record.levelno in self.levels:
            return True
        return False


def setup_logging(forceDebug=False):
    """
    General function to setup the logger.
    Everything from debug to stdout message is handled by loggers.
    stdout logger handles info and warning message to STDOUT
    stderr logger handles error and critical message to stderr
    Everything else is for debug logger which logs everything to /var/tmp/oci-utils.log
    """

    flatFormatter = logging.Formatter('%(message)s')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s(%(module)s:%(lineno)s) - %(message)s')
    handler = None
    if os.environ.get('_OCI_UTILS_SYSLOG'):
        handler = logging.handlers.SysLogHandler(address='/dev/log', facility=logging.handlers.SysLogHandler.LOG_DAEMON)
    else:
        if forceDebug:
            try:
                handler = logging.handlers.RotatingFileHandler('/var/tmp/oci-utils.log',
                                                               mode='a',
                                                               maxBytes=1024*1024,
                                                               backupCount=3)
                handler.setFormatter(formatter)
                handler.setLevel(logging.NOTSET)
            except Exception as _:
                # keep it silent
                pass

    logger = logging.getLogger('oci-utils')
    logger.setLevel(logging.INFO)

    stdoutHandler = logging.StreamHandler(stream=sys.stdout)
    stdoutHandler.setFormatter(flatFormatter)
    stdoutHandler.addFilter(levelsFilter([logging.INFO, logging.WARNING]))

    stderrHandler = logging.StreamHandler(stream=sys.stderr)
    stderrHandler.setFormatter(flatFormatter)
    stderrHandler.addFilter(levelsFilter([logging.ERROR, logging.CRITICAL]))
    if handler is not None:
        logger.addHandler(handler)
    logger.addHandler(stdoutHandler)
    logger.addHandler(stderrHandler)

    if forceDebug:
        logger.setLevel(logging.DEBUG)
        if handler is not None:
            handler.setLevel(logging.DEBUG)
