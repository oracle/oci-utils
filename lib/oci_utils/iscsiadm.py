#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2017, 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

"""
Python wrapper around iscsiadm
"""

import os
import socket
import subprocess
import logging
import re
from oci_utils.cache import GLOBAL_CACHE_DIR

__iscsi_logger = logging.getLogger('iscsi')
__iscsi_logger.setLevel(logging.INFO)
__handler = logging.StreamHandler()
__iscsi_logger.addHandler(__handler)
ISCSIADM_CACHE = GLOBAL_CACHE_DIR + "/iscsiadm-cache"

def error_message_from_code(errorcode):
    """
    return the error message corresponding to the return iscsiadm error code
    """
    # error codes and messages taken from the iscsiadm manual page
    ERROR_CODES={
        0:'command executed successfully',
        1:'generic error code',
        2:'session could not be found',
        3:'could not allocate resource for operation',
        4:'connect problem caused operation to fail',
        5:'generic iSCSI login failure',
        6:'error accessing/managing iSCSI DB',
        7:'invalid argument',
        8:'connection timer exired  while  trying to connect',
        9:'generic internal iscsid/kernel failure',
        10:'iSCSI logout failed',
        11:'iSCSI PDU timedout',
        12:'iSCSI transport module not loaded in kernel or iscsid',
        13:'did not have proper OS permissions to  access iscsid or execute iscsiadm command',
        14:'transport module did not support operation',
        15:'session is logged in',
        16:'invalid IPC MGMT request',
        17:'iSNS service is not supported',
        18:'a read/write to iscsid failed',
        19:'fatal iSCSI login error',
        20:'could not connect to iscsid',
        21:'no records/targets/sessions/portals found to execute operation on',
        22:'could not lookup object in sysfs',
        23:'could not lookup host',
        24:'login failed due to authorization failure',
        25:'iSNS query failure',
        26:'iSNS registration/deregistration failed',
        403:'attempt to detach the boot volume',
        404:'could not execute /usr/bin/iscsiadm',
    }

    if errorcode in ERROR_CODES:
        return ERROR_CODES[errorcode]

    return "Unknown error (%s)" % errorcode

def set_logger(logger):
    global __iscsi_logger
    __iscsi_logger = logger

def __can_connect(ipaddr, port=3260):
    """
    try to open a TCP connection to a given IP address and port,
    return True for success, False for failure
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(1)
        s.connect((ipaddr, port))
        s.close()
        return True
    except Exception as e:
        s.close()
        return False
    
def discovery(ipaddr):
    """
    run iscsiadm in discovery mode for the given IP address,
    return a list of IQNs discovered.
    """
    if not __can_connect(ipaddr):
        return []
    try:
        DEVNULL = open(os.devnull, 'w')
        output = subprocess.check_output(['/usr/sbin/iscsiadm',
                                          '-m', 'discovery',
                                          '-t', 'st',
                                          '-p', ipaddr + ':3260'],
                                         stderr=DEVNULL)
        iqns = []
        pattern = re.compile(r'^.*:3260,[0-9]+ (.*)')
        for line in output.split('\n'):
            if not 'iqn' in line:
                continue
            match = pattern.match(line.strip())
            if (match):
                iqns.append(match.group(1))
        return iqns
    except subprocess.CalledProcessError as e:
        return []

def session():
    """
    run iscsiadm in session mode, return a dict of targets attached, using
    the IQNs as keys
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
        DEVNULL = open(os.devnull, 'w')
        output = subprocess.check_output(['/usr/sbin/iscsiadm',
                                          '-m', 'session',
                                          '-P', '3'],
                                         stderr=DEVNULL)
        devices = {}
        target_pattern = re.compile(r'^Target: (\S+)')
        portal_pattern = re.compile(r'(Current|Persistent) Portal: ([0-9.]+):([0-9]+),')
        disk_pattern = re.compile(r'Attached scsi disk (\S+)\s+State: (\S+)')
        sess_state_pattern = re.compile(r'iSCSI Session State: (\S+)')
        device_info = {}
        target = None
        for line in output.split('\n'):
            # new section describing a different Target is starting
            # save any data collected about the previous Target
            if 'Target:' in line:
                if target is not None and device_info != {}:
                    devices[target] = device_info
                    device_info = {}
                match = target_pattern.search(line.strip())
                if match:
                    target = match.group(1)
                else:
                    target = None
                continue
            if 'Current Portal:' in line:
                match = portal_pattern.search(line.strip())
                if match:
                    device_info['current_portal_ip'] = match.group(2)
                    device_info['current_portal_port'] = match.group(3)
            if 'Persistent Portal:' in line:
                match = portal_pattern.search(line.strip())
                if match:
                    device_info['persistent_portal_ip'] = match.group(2)
                    device_info['persistent_portal_port'] = match.group(3)
            if 'iSCSI Session State:' in line:
                match = sess_state_pattern.search(line.strip())
                if match:
                    device_info['session_state'] = match.group(1)
            if 'Attached scsi disk' in line:
                match = disk_pattern.search(line.strip())
                if match:
                    device_info['device'] = match.group(1)
                    device_info['state'] = match.group(2)
        if target is not None and device_info != {}:
            devices[target] = device_info
        
        return devices
    except OSError as e:
        __iscsi_logger.error('failed to execute /usr/sbin/iscsiadm')
        return {}
    except subprocess.CalledProcessError as e:
        return {}

def attach(ipaddr, port, iqn, username=None, password=None, auto_startup=True):
    """
    Attach an iscsi device at the given IP address, port and IQN.
    If auto_startup is True, set a flag to attach the device automatically
    at system boot.
    Return True on success, False otherwise

    """
    try:
        subprocess.check_output(['/usr/sbin/iscsiadm',
                                 '-m', 'node',
                                 '-o', 'new',
                                 '-T', iqn,
                                 '-p', "%s:%s" % (ipaddr, port)],
                                stderr=subprocess.STDOUT)
    except OSError as e:
        __iscsi_logger.error('failed to execute /usr/sbin/iscsiadm')
        return 404
    except subprocess.CalledProcessError as e:
        __iscsi_logger.error('failed to register new iscsi volume')
        __iscsi_logger.info(e.output)
        return e.returncode

    if auto_startup:
        try:
            subprocess.check_output(['/usr/sbin/iscsiadm',
                                     '-m', 'node',
                                     '-o', 'update',
                                     '-T', iqn,
                                     '-n', 'node.startup',
                                     '-v', 'automatic'],
                                    stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            logging.warn('failed to set automatic startup set for '
                         'iscsi volume %s' % iqn)
            logging.warn('iscsiadm output: %s' % e.output)
            return e.returncode

    if username is not None and password is not None:
        try:
            subprocess.check_output(['/usr/sbin/iscsiadm',
                                     '-m', 'node',
                                     '-o', 'update',
                                     '-T', iqn,
                                     '-p', "%s:%s" % (ipaddr, port),
                                     '-n', 'node.session.auth.authmethod',
                                     '-v', 'CHAP'],
                                    stderr=subprocess.STDOUT)
            subprocess.check_output(['/usr/sbin/iscsiadm',
                                     '-m', 'node',
                                     '-o', 'update',
                                     '-T', iqn,
                                     '-p', "%s:%s" % (ipaddr, port),
                                     '-n', 'node.session.auth.username',
                                     '-v', username],
                                    stderr=subprocess.STDOUT)
            subprocess.check_output(['/usr/sbin/iscsiadm',
                                     '-m', 'node',
                                     '-o', 'update',
                                     '-T', iqn,
                                     '-p', "%s:%s" % (ipaddr, port),
                                     '-n', 'node.session.auth.password',
                                     '-v', password],
                                    stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            __iscsi_logger.error('failed to update authentication settings')
            __iscsi_logger.info(e.output)
            return e.returncode

    try:
        subprocess.check_output(['/usr/sbin/iscsiadm',
                                 '-m', 'node',
                                 '-T', iqn,
                                 '-p', "%s:%s" % (ipaddr, port),
                                 '-l'],
                                stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        __iscsi_logger.error('failed to log in to iscsi volume: %s' %
                             error_message_from_code(e.returncode))
        __iscsi_logger.error('iscsiadm output: %s' % e.output)
        return e.returncode

    return 0

def detach(ipaddr, port, iqn):
    """
    Detach the iSCSI device with the given IP address, port and IQN
    """
    if iqn.endswith('boot:uefi'):
        # refuse to detach the boot volume
        __iscsi_logger.error('Stubbornly refusing to detach the boot volume: ' \
                             '%s' % iqn)
        return 403
    DEVNULL = open(os.devnull, 'w')
    try:
        retval = subprocess.check_call(['/usr/sbin/iscsiadm',
                                        '-m', 'node',
                                        '-T', iqn,
                                        '-p', "%s:%s" % (ipaddr, port),
                                        '-u'],
                                       stderr=DEVNULL,
                                       stdout=DEVNULL)
        retval = subprocess.check_call(['/usr/sbin/iscsiadm',
                                        '-m', 'node',
                                        '-o', 'delete',
                                        '-T', iqn,
                                        '-p', "%s:%s" % (ipaddr, port)],
                                       stderr=DEVNULL,
                                       stdout=DEVNULL)
    except subprocess.CalledProcessError as e:
        return False

    return True
