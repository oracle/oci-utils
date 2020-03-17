#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.
#

import io
import logging
import os
import os.path
import sys
import threading
from configparser import ConfigParser
from datetime import datetime, timedelta
import logging
import logging.handlers

from time import sleep

from ..exceptions import OCISDKError

__all__ = ['lock_thread', 'release_thread', 'read_config', 'SUDO_CMD',
           'CAT_CMD', 'SH_CMD', 'CP_CMD', 'TOUCH_CMD', 'CHMOD_CMD']

CAT_CMD = '/usr/bin/cat'
TOUCH_CMD = '/usr/bin/touch'
CHMOD_CMD = '/usr/bin/chmod'
RM_CMD = '/bin/rm'
CP_CMD = '/bin/cp'
SH_CMD = '/bin/sh'
SUDO_CMD = '/bin/sudo'
VIRSH_CMD = '/usr/bin/virsh'
IP_CMD = '/usr/sbin/ip'
BRIDGE_CMD = '/sbin/bridge'
PARTED_CMD = '/sbin/parted'
MK_XFS_CMD = '/sbin/mkfs.xfs'
SYSTEMCTL_CMD = '/bin/systemctl'


def print_error(msg, *args):
    """
    Write a message to the standard error.

    Parameters
    ----------
    msg: str
        The message.
    args: list
        The format string.

    Returns
    -------
        No return value.
    """
    sys.stderr.write(msg.format(*args))
    sys.stderr.write('\n')


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
    print_error("{}{}{}", header, sep, sep.join(choices))


_oci_utils_thread_lock = threading.Lock()
_oci_utils_thread_lock_owner = None
_oci_utils_thread_lock_owner_l = threading.Lock()


def lock_thread(timeout=30):
    """
    Timed locking; set a threading lock with timeout.

    Parameters
    ----------
    timeout: int
        Timeout in second to acquire the lock, default is 30sec.

    Returns
    -------
        No return valiue.

    Raises
    ------
        OCISDKError
            If timeout occured

    """
    global _oci_utils_thread_lock
    global _oci_utils_thread_lock_owner, _oci_utils_thread_lock_owner_l

    # RE-ENTRANT not supported. check that the lock is free
    # or not already acquired
    _re_entrance_detected = False
    _oci_utils_thread_lock_owner_l.acquire(True)
    if _oci_utils_thread_lock_owner == threading.currentThread():
        _re_entrance_detected = True
    _oci_utils_thread_lock_owner_l.release()

    assert (not _re_entrance_detected), 'trying to acquire a lock twice !'

    if timeout > 0:
        max_time = datetime.now() + timedelta(seconds=timeout)
        while True:
            # non-blocking
            if _oci_utils_thread_lock.acquire(False):
                _oci_utils_thread_lock_owner_l.acquire(True)
                _oci_utils_thread_lock_owner = threading.currentThread()
                _oci_utils_thread_lock_owner_l.release()
                break
            if max_time < datetime.now():
                raise OCISDKError("Timed out waiting for API thread lock")
            else:
                sleep(0.1)
    else:
        # blocking
        _oci_utils_thread_lock.acquire(True)
        _oci_utils_thread_lock_owner_l.acquire(True)
        _oci_utils_thread_lock_owner = threading.currentThread()
        _oci_utils_thread_lock_owner_l.release()


def release_thread():
    """
    Release the thread lock.

    Returns
    -------
        No return value.

    Raises
    ------
       ThreadError
           If lock not currently locked.
    """

    global _oci_utils_thread_lock
    global _oci_utils_thread_lock_owner_l
    global _oci_utils_thread_lock_owner

    _safe_unlock = True

    _oci_utils_thread_lock_owner_l.acquire(True)
    if _oci_utils_thread_lock_owner != threading.currentThread():
        _safe_unlock = False
    _oci_utils_thread_lock_owner = None
    _oci_utils_thread_lock_owner_l.release()

    assert _safe_unlock, 'trying to relase a unlocked lock'

    _oci_utils_thread_lock.release()


# oci-utils configuration defaults


# oci-utils config file
__oci_utils_conf_d = "/etc/oci-utils.conf.d"
oci_utils_config = None


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
    global oci_utils_config
    if oci_utils_config is not None:
        return oci_utils_config

    oci_utils_config = ConfigParser()
    # assign default
    oci_utils_config.add_section('auth')
    oci_utils_config.set('auth','auth_method','auto')
    oci_utils_config.set('auth','oci_sdk_user','opc')
    oci_utils_config.add_section('iscsi')
    oci_utils_config.set('iscsi','enabled','true')
    oci_utils_config.set('iscsi','scan_interval','60')
    oci_utils_config.set('iscsi','max_volumes','8')
    oci_utils_config.set('iscsi','auto_resize','true')
    oci_utils_config.set('iscsi','auto_detach','true')
    oci_utils_config.set('iscsi','detach_retry','5')
    oci_utils_config.add_section('vnic')
    oci_utils_config.set('vnic','enabled','true')
    oci_utils_config.set('vnic','scan_interval','60')
    oci_utils_config.set('vnic','vf_net','false')
    oci_utils_config.add_section('public_ip')
    oci_utils_config.set('public_ip','enabled','true')
    oci_utils_config.set('public_ip','refresh_interval','600')
    
    if not os.path.exists(__oci_utils_conf_d):
        return oci_utils_config

    conffiles = [os.path.join(__oci_utils_conf_d, f)
                 for f in os.listdir(__oci_utils_conf_d)
                 if os.path.isfile(os.path.join(__oci_utils_conf_d, f))]
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
    General function to setup logger.
    Everything from debug to stdout message is handle by loggers.
    stdout logger handle info and warning message to STDOUT
    stderr logger handle error and critical message to stderr
    anything else is for debug logger which log everything to /var/tmp/oci-utils.log
    """

    flatFormatter = logging.Formatter('%(message)s')
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s(%(module)s:%(lineno)s) - %(message)s')
    handler = None
    if os.environ.get('_OCI_UTILS_SYSLOG'):
        handler = logging.handlers.SysLogHandler(address='/dev/log',
                                                 facility=logging.handlers.SysLogHandler.LOG_DAEMON)
    else:
        if forceDebug:
            try:
                handler = logging.handlers.RotatingFileHandler(
                    '/var/tmp/oci-utils.log', mode='a', maxBytes=1024 * 1024, backupCount=3)
                handler.setFormatter(formatter)
                handler.setLevel(logging.NOTSET)
            except Exception as ignored:
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
