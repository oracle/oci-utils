# oci-utils
#
# Copyright (c) 2017, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Python wrapper around iscsiadm.
"""

import logging
import os
import re
import subprocess

from .cache import get_cache_file_path
from .impl.network_helpers import is_ip_reachable

_iscsi_logger = logging.getLogger('oci-utils.iscsi')


ISCSIADM_CACHE = get_cache_file_path('iscsiadm-cache')
CHAPSECRETS_CACHE = get_cache_file_path('chapsecrets-cache')
IGNOREIQNS_CACHE = get_cache_file_path('ignoreiqns-cache')


def error_message_from_code(errorcode):
    """
    Convert iscsiadm return code to errror message.

    Parameters
    ----------
    errorcode: int
        The iscsiadm return code.

    Returns
    -------
        The error message.
    """
    assert isinstance(errorcode, int), 'invalid error code type'

    if not hasattr(error_message_from_code, "ERROR_CODES"):
        error_message_from_code.ERROR_CODES = {
                    0: 'command executed successfully',
                    1: 'generic error code',
                    2: 'session could not be found',
                    3: 'could not allocate resource for operation',
                    4: 'connect problem caused operation to fail',
                    5: 'generic iSCSI login failure',
                    6: 'error accessing/managing iSCSI DB',
                    7: 'invalid argument',
                    8: 'connection timer expired  while  trying to connect',
                    9: 'generic internal iscsid/kernel failure',
                    10: 'iSCSI logout failed',
                    11: 'iSCSI PDU timedout',
                    12: 'iSCSI transport module not loaded in kernel or iscsid',
                    13: 'did not have proper OS permissions to  access iscsid '
                        'or execute iscsiadm command',
                    14: 'transport module did not support operation',
                    15: 'session is logged in',
                    16: 'invalid IPC MGMT request',
                    17: 'iSNS service is not supported',
                    18: 'a read/write to iscsid failed',
                    19: 'fatal iSCSI login error',
                    20: 'could not connect to iscsid',
                    21: 'no records/targets/sessions/portals found to execute operation on',
                    22: 'could not lookup object in sysfs',
                    23: 'could not lookup host',
                    24: 'login failed due to authorization failure',
                    25: 'iSNS query failure',
                    26: 'iSNS registration/deregistration failed',
                    403: 'attempt to detach the boot volume',
                    404: 'could not execute /usr/bin/iscsiadm'
        }

    if errorcode in error_message_from_code.ERROR_CODES:
        return error_message_from_code.ERROR_CODES[errorcode]

    return "Unknown error (%s)" % errorcode


_DISCOVERY_PATTERN = re.compile(r'^.*:3260,[0-9]+ (.*)')


def discovery(ipaddr):
    """
    Run iscsiadm in discovery mode for the given IP address.

    Parameters
    ----------
    ipaddr : str
        The IP address.

    Returns
    -------
        list
            The list of iSCSI qualified names discovered.
    """
    if not is_ip_reachable(ipaddr):
        _iscsi_logger.debug('Given IP %s is not reachable.', ipaddr)
        return []
    try:
        with open(os.devnull, 'w') as dev_null:
            _cmd = ['/usr/sbin/iscsiadm',
                    '-m', 'discovery',
                    '-t', 'st',
                    '-p', ipaddr + ':3260']
            _iscsi_logger.debug('Executing %s', _cmd)
            output = subprocess.check_output(_cmd, stderr=dev_null).decode('utf-8')
            # _iscsi_logger.debug('%s output: %s', _cmd, output)
        iqns = []
        for line in output.splitlines():
            if 'iqn' not in line:
                continue
            match = _DISCOVERY_PATTERN.match(line.strip())
            if match:
                iqns.append(match.group(1))
        return iqns
    except subprocess.CalledProcessError as e:
        # TODO : why this is not an error ?
        _iscsi_logger.warning('Error running /usr/sbin/iscsiadm [%s]', str(e))
        return []


_TARGET_PATTERN = re.compile(r'^Target: (\S+)')
_PORTAL_PATTERN = re.compile(r'(Current|Persistent) Portal: ([0-9.]+):([0-9]+),')
_DISK_PATTERN = re.compile(r'Attached scsi disk (\S+)\s+State: (\S+)')
_SESS_STATE_PATTERN = re.compile(r'iSCSI Session State: (\S+)')


def session():
    """
    Run iscsiadm in session mode.

    Returns
    -------
        dict
            dict of targets attached, using the IQNs as keys
           { iqn1: { 'current_portal_ip': ip_address,
                     'current_portal_port': port,
                     'persistent_portal_ip': ip_address,
                     'persistent_portal_port': port,
                     'state': state,
                     'device': sdX,
                    },
             iqn2: {....}
           }
    """
    try:
        with open(os.devnull, 'w') as dev_null:
            _cmd = ['/usr/sbin/iscsiadm', '-m', 'session', '-P', '3']
            _iscsi_logger.debug('Executing %s', _cmd)
            output = subprocess.check_output(_cmd, stderr=dev_null).decode('utf-8')
            # _iscsi_logger.debug('%s output: %s', _cmd, output)
        devices = {}

        device_info = {}
        target = None
        for line in output.splitlines():
            # new section describing a different Target is starting
            # save any data collected about the previous Target
            if 'Target:' in line:
                if target is not None and device_info != {}:
                    devices[target] = device_info
                    device_info = {}
                match = _TARGET_PATTERN.search(line.strip())
                if match:
                    target = match.group(1)
                else:
                    target = None
                continue
            if 'Current Portal:' in line:
                match = _PORTAL_PATTERN.search(line.strip())
                if match:
                    device_info['current_portal_ip'] = match.group(2)
                    device_info['current_portal_port'] = match.group(3)
            if 'Persistent Portal:' in line:
                match = _PORTAL_PATTERN.search(line.strip())
                if match:
                    device_info['persistent_portal_ip'] = match.group(2)
                    device_info['persistent_portal_port'] = match.group(3)
            if 'iSCSI Session State:' in line:
                match = _SESS_STATE_PATTERN.search(line.strip())
                if match:
                    device_info['session_state'] = match.group(1)
            if 'Attached scsi disk' in line:
                match = _DISK_PATTERN.search(line.strip())
                if match:
                    device_info['device'] = match.group(1)
                    device_info['state'] = match.group(2)
        if target is not None and device_info != {}:
            devices[target] = device_info

        return devices
    except OSError:
        _iscsi_logger.error('Failed to execute /usr/sbin/iscsiadm')
        return {}
    except subprocess.CalledProcessError as e:
        if e.returncode in (15, 21):
            # non-fatal error that we should not warn the user about
            # see ISCSIADM(8)
            _iscsi_logger.debug('Error running /usr/sbin/iscsiadm [%s]', str(e))
        else:
            _iscsi_logger.warning('Error running /usr/sbin/iscsiadm [%s]', str(e))
        return {}


def attach(ipaddr, port, iqn, username=None, password=None, auto_startup=True):
    """
    Attach an iscsi device at the given IP address, port and IQN. If
    auto_startup is True, set a flag to attach the device automatically
    at system boot.

    Parameters
    ----------
    ipaddr : str
        The ip address of the iSCSI server.
    port : int
        The ip port used by the iSCSI server.
    iqn : str
        The iSCSI qualified name.
    username : str
        The iSCSI username.
    password : str
        The iSCSI user password.
    auto_startup : bool
        If set, attach on system boot.

    Returns
    -------
        bool
            True on success, False otherwise
    """
    try:
        _cmd = ['/usr/sbin/iscsiadm',
                '-m', 'node',
                '-o', 'new',
                '-T', iqn,
                '-p', "%s:%s" % (ipaddr, port)]
        _iscsi_logger.debug('Executing %s', _cmd)
        output = subprocess.check_output(_cmd, stderr=subprocess.STDOUT)
        # _iscsi_logger.debug('%s output: %s', _cmd, output)
    except OSError as e:
        _iscsi_logger.error('Failed to execute /usr/sbin/iscsiadm: %s', str(e))
        return 404
    except subprocess.CalledProcessError as e:
        _iscsi_logger.error('Failed to register new iscsi volume')
        _iscsi_logger.info(e.output)
        return e.returncode
    #
    # if enabled, set automatic attach after reboot.
    if auto_startup:
        try:
            _cmd = ['/usr/sbin/iscsiadm',
                    '-m', 'node',
                    '-o', 'update',
                    '-T', iqn,
                    '-n', 'node.startup',
                    '-v', 'automatic']
            _iscsi_logger.debug('Executing %s', _cmd)
            output = subprocess.check_output(_cmd, stderr=subprocess.STDOUT)
            # _iscsi_logger.debug('%s output: %s', _cmd, output)
        except subprocess.CalledProcessError as e:
            logging.warning('Failed to set automatic startup set for iscsi volume %s', iqn)
            logging.warning('iscsiadm output: %s', e.output)
            return e.returncode
    #
    # if a username/password is provided, use CHAP authentication
    if username is not None and password is not None:
        try:
            _cmd = ['/usr/sbin/iscsiadm',
                    '-m', 'node',
                    '-o', 'update',
                    '-T', iqn,
                    '-p', "%s:%s" % (ipaddr, port),
                    '-n', 'node.session.auth.authmethod',
                    '-v', 'CHAP']
            _iscsi_logger.debug('Executing %s', _cmd)
            output = subprocess.check_output(_cmd, stderr=subprocess.STDOUT)
            # _iscsi_logger.debug('%s output: %s', _cmd, output)

            _cmd = ['/usr/sbin/iscsiadm',
                    '-m', 'node',
                    '-o', 'update',
                    '-T', iqn,
                    '-p', "%s:%s" % (ipaddr, port),
                    '-n', 'node.session.auth.username',
                    '-v', username]
            _iscsi_logger.debug('Executing %s', _cmd)
            output = subprocess.check_output(_cmd, stderr=subprocess.STDOUT)
            # _iscsi_logger.debug('%s output: %s', _cmd, output)

            _cmd = ['/usr/sbin/iscsiadm',
                    '-m', 'node',
                    '-o', 'update',
                    '-T', iqn,
                    '-p', "%s:%s" % (ipaddr, port),
                    '-n', 'node.session.auth.password',
                    '-v', password]
            _iscsi_logger.debug('Executing %s', _cmd)
            output = subprocess.check_output(_cmd, stderr=subprocess.STDOUT)
            # _iscsi_logger.debug('%s output: %s', _cmd, output)
        except subprocess.CalledProcessError as e:
            _iscsi_logger.error('Failed to update authentication settings')
            _iscsi_logger.info(e.output.decode('utf-8'))
            return e.returncode
    #
    # login
    try:
        _cmd = ['/usr/sbin/iscsiadm',
                '-m', 'node',
                '-T', iqn,
                '-p', "%s:%s" % (ipaddr, port),
                '-l']
        _iscsi_logger.debug('Executing %s', _cmd)
        output = subprocess.check_output(_cmd, stderr=subprocess.STDOUT)
        # _iscsi_logger.debug('%s output: %s', _cmd, output)
    except subprocess.CalledProcessError as e:
        _iscsi_logger.error('Failed to log in to iscsi volume: %s', error_message_from_code(e.returncode))
        _iscsi_logger.error('iscsiadm output: %s', e.output.decode('utf-8'))
        return e.returncode

    return 0


def detach(ipaddr, port, iqn):
    """
    Detach the iSCSI device with the given IP address, port and IQN.

    Parameters
    ----------
    ipaddr : str
        The ip address.
    port : int
        The ip port.
    iqn : str
        The iSCSI qualified name.

    Returns
    -------
        bool
            True on success, False otherwise.
    """
    if iqn.endswith('boot:uefi'):
        # refuse to detach the boot volume
        _iscsi_logger.error('Stubbornly refusing to detach the boot volume: %s', iqn)
        return 403
    dev_null = open(os.devnull, 'w')
    try:
        _cmd = ['/usr/sbin/iscsiadm',
                '-m', 'node',
                '-T', iqn,
                '-p', "%s:%s" % (ipaddr, port),
                '-u']
        _iscsi_logger.debug('Executing %s', _cmd)
        output = subprocess.check_call(_cmd, stderr=dev_null, stdout=dev_null)
        # _iscsi_logger.debug('%s output: %s', _cmd, output)

        _cmd = ['/usr/sbin/iscsiadm',
                '-m', 'node',
                '-o', 'delete',
                '-T', iqn,
                '-p', "%s:%s" % (ipaddr, port)]
        _iscsi_logger.debug('Executing %s', _cmd)
        output = subprocess.check_call(_cmd, stderr=dev_null, stdout=dev_null)
    except subprocess.CalledProcessError as e:
        _iscsi_logger.error('Error running iscsiadm command [%s]', str(e))
        return False
    finally:
        dev_null.close()

    return True
