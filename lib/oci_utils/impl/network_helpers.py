# oci-utils
#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Helper module around network information.
"""

import os
import socket
import subprocess
import logging
import shutil
from socket import inet_ntoa
from struct import pack
from . import sudo_utils
import re

__all__ = ['get_interfaces', 'is_ip_reachable', 'add_route_table', 'delete_route_table',
           'network_prefix_to_mask',
           'add_static_ip_route',
           'add_static_ip_rule',
           'add_firewall_rule',
           'remove_firewall_rule',
           'remove_static_ip_routes',
           'remove_static_ip_rules']

_CLASS_NET_DIR = '/sys/class/net'

_logger = logging.getLogger('oci-utils.net-helper')


def get_interfaces():
    """
    Collect the information on all network interfaces.

    Returns
    -------
        dict
            The information on the interfaces.
    """
    ret = {}

    pci_id_to_iface = {}

    for n in os.listdir(_CLASS_NET_DIR):
        physical = True
        iface = "{}/{}".format(_CLASS_NET_DIR, n)
        try:
            link = os.readlink(iface)
            if link.startswith('../../devices/virtual'):
                physical = False
        except OSError:
            continue

        mac = open('{}/address'.format(iface)).read().strip().lower()

        iface_info = {'physical': physical, 'mac': mac}

        if physical:
            # Check to see if this is a physical or virtual
            # function
            dev = '{}/device'.format(iface)

            pci_id = os.readlink(dev)
            pci_id = pci_id[pci_id.rfind('/') + 1:]

            pci_id_to_iface[pci_id] = n
            iface_info['pci'] = pci_id

            try:
                phys_id = os.readlink('{}/physfn'.format(dev))[3:]
                iface_info['physfn'] = phys_id
            except OSError:
                # If there is no physical function backing this
                # interface, then it must itself be one
                virt_ifaces = {}
                dirs = os.listdir(dev)
                for d in dirs:
                    if not d.startswith('virtfn'):
                        continue

                    virt_pci_id = os.readlink('{}/{}'.format(dev, d))[3:]
                    virt_ifaces[int(d[6:])] = {'pci_id': virt_pci_id}

                # TODO: find a better way to get mac addresses for
                # TODO: virtual functions
                for line in subprocess.check_output(
                        ['/usr/sbin/ip', 'link', 'show', n]).splitlines():
                    line = line.strip()
                    if not str(line).startswith('vf '):
                        continue

                    ents = line.split(' ')
                    vf_num = int(ents[1])
                    vf_mac = ents[3][:-1]

                    virt_ifaces[vf_num]['mac'] = vf_mac

                iface_info['virtfns'] = virt_ifaces

        ret[n] = iface_info

    # Populate any potentially invalid mac addresses with
    # the correct data
    for n, info in ret.items():
        if not info['physical']:
            continue

        virt_fns = info.get('virtfns')
        if virt_fns is None:
            continue

        for k, v in virt_fns.items():
            try:
                v['mac'] = ret[pci_id_to_iface[v['pci_id']]]['mac']
            except Exception:
                pass

    return ret


def is_ip_reachable(ipaddr, port=3260):
    """
    Try to open a TCP connection. to a given IP address and port.

    Parameters
    ----------
    ipaddr : str
        IP address to connect to.
    port : int, optional
        Port number to connect.

    Returns
    -------
        bool
            True for success, False for failure
    """
    assert isinstance(ipaddr, str), \
        'ipaddr must be a valid string [%s]' % str(ipaddr)
    assert (isinstance(port, int) and port > 0), \
        'port must be positive value [%s]' % str(port)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(1)
        s.connect((ipaddr, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def add_route_table(table_name):
    """
    Adds a new routing table by name
    Add a new entry in /etc/iproute2/rt_tables
    Parameters
    ----------
    table_name : str
        name of the new table
    Returns
    -------
        bool
            True for success, False for failure
    """

    # first , find a free number for the table
    tables_num = []
    _all_new_lines = []
    with open('/etc/iproute2/rt_tables') as f:
        for line in f.readlines():
            _all_new_lines.append(line)
            if len(line.strip()) > 0 and not line.startswith('#'):
                # trust the format of that file
                tables_num.append(int(line.split()[0]))
    _new_table_num_to_use = -1
    for n in range(255):
        if n not in tables_num:
            _new_table_num_to_use = n
            break
    _logger.debug('new table index : %d' % _new_table_num_to_use)
    _all_new_lines.append('%d\t%s\n' % (_new_table_num_to_use, table_name))

    if sudo_utils.copy_file('/etc/iproute2/rt_tables', '/etc/iproute2/rt_tables.bck') != 0:
        _logger.debug('cannot backup file [%s] to %s' % ('/etc/iproute2/rt_tables', '/etc/iproute2/rt_tables.bck'))
        return False
    if sudo_utils.write_to_file('/etc/iproute2/rt_tables', ''.join(_all_new_lines)) != 0:
        _logger.debug('cannot write new content to  file [%s]' '/etc/iproute2/rt_tables')
        sudo_utils.copy_file('/etc/iproute2/rt_tables.bck', '/etc/iproute2/rt_tables')
        return False
    else:
        sudo_utils.delete_file('/etc/iproute2/rt_tables.bck')

    return True


def delete_route_table(table_name):
    """
    Deletes a routing table by name
    remove a  entry in /etc/iproute2/rt_tables
    Parameters
    ----------
    table_name : str
        name of the new table
    Returns
    -------
        bool
            True for success, False for failure
    """
    _all_new_lines = []
    with open('/etc/iproute2/rt_tables') as f:
        _all_lines = f.readlines()
        for line in _all_lines:
            # format is '<index>\t<table name>'
            _s_l = line.split()
            if len(_s_l) > 1 and _s_l[1] == table_name:
                # foudn the table name , skip this line
                continue
            _all_new_lines.append(line)

    if sudo_utils.copy_file('/etc/iproute2/rt_tables', '/etc/iproute2/rt_tables.bck') != 0:
        _logger.debug('cannot backup file [%s] to %s' % ('/etc/iproute2/rt_tables', '/etc/iproute2/rt_tables.bck'))
        return False
    if sudo_utils.write_to_file('/etc/iproute2/rt_tables', ''.join(_all_new_lines)) != 0:
        _logger.debug('cannot write new content to  file [%s]' '/etc/iproute2/rt_tables')
        sudo_utils.copy_file('/etc/iproute2/rt_tables.bck', '/etc/iproute2/rt_tables')
        return False
    else:
        sudo_utils.delete_file('/etc/iproute2/rt_tables.bck')

    return True


def network_prefix_to_mask(prefix):
    """
    converts a prefix to a netmask address
    Parameters:
       prefix : the prefix as int
    Returns:
        the netmask address
    Exemple:
       network_prefix_to_mask(22) -> '255.255.252.0'
    """
    bits = 0xffffffff ^ (1 << 32 - prefix) - 1
    return inet_ntoa(pack('>I', bits))


def remove_static_ip_routes(link_name):
    """
    Deletes all routes related to a network device
    Parameters:
       link_name : str
          the ip link name
    Return:
        None
    """
    _logger.debug('looking for ip routes for dev=%s' % link_name)
    _lines = []
    try:
        _lines = subprocess.check_output(['/sbin/ip', 'route', 'show', 'dev', link_name]).splitlines()
    except subprocess.CalledProcessError as ignored:
        pass
    _logger.debug('routes found [%s]' % _lines)
    for _line in _lines:
        _command = ['/sbin/ip', 'route', 'del']
        _command.extend(_line.strip().split(' '))
        _out = sudo_utils.call_output(_command)
        if _out is not None and len(_out) > 0:
            _logger.warning('removal of ip route (%s) failed' % _line)


def add_static_ip_route(*args, **kwargs):
    """
    add a static route
    Parameters:
        kwargs:
            device : network device on which assign the route
            script : a reference to StringIO object to write the command for future use in script
        *args : argument list as passed to the ip-route(8) command
    Return:
        (code,message): command code , on failure a message is sent back
    """
    routing_cmd = ['/usr/sbin/ip', 'route', 'add']
    routing_cmd.extend(args)
    _logger.debug('adding route : [%s]' % ' '.join(args))
    _out = sudo_utils.call_output(routing_cmd)
    if _out is not None and len(_out) > 0:
        _logger.warning('add of ip route failed')
        return (1, _out)

    if kwargs.get('script'):
        kwargs.get('script').write(' '.join(routing_cmd))
        kwargs.get('script').write('\n')

    return (0, '')


def remove_static_ip_rules(link_name):
    """
    Deletes all rules related to a network device
    Parameters:
       link_name : str
          the ip link name
    Return:
        None
    """
    _logger.debug('looking for ip rules for dev=%s' % link_name)
    _lines = []
    try:
        _lines = subprocess.check_output(['/sbin/ip', 'rule', 'show', 'lookup', link_name]).splitlines()
    except subprocess.CalledProcessError as ignored:
        pass
    _logger.debug('rules found [%s]' % _lines)
    for _line in _lines:

        _command = ['/sbin/ip', 'rule', 'del']
        # all line listed are like '<rule number>:\t<rule as string> '
        # when underlying device is down (i.e virtual network is down) the command append '[detached]' we have to remove this
        _command.extend(re.compile("\d:\t").split(_line.strip())[1].replace('[detached] ', '').split(' '))
        _out = sudo_utils.call_output(_command)
        if _out is not None and len(_out) > 0:
            _logger.warning('cannot delete rule [%s]: %s' % (' '.join(_command), str(_out)))


def add_static_ip_rule(*args, **kwargs):
    """
    add a static rule
    Parameters:
        kwargs:
            device : network device on which assign the rule
            script : a reference to StringIO object to write the command for future use in script
        *args : argument list as passed to the ip-rule(8) command
    Return:
        (code,message): command code , on failure a message is sent back
    """
    ip_rule_cmd = ['/usr/sbin/ip', 'rule', 'add']
    ip_rule_cmd.extend(args)
    _logger.debug('adding rule : [%s]' % ' '.join(args))
    _out = sudo_utils.call_output(ip_rule_cmd)
    if _out is not None and len(_out) > 0:
        _logger.warning('add of ip rule failed')
        return (1, _out)

    if kwargs.get('script'):
        kwargs.get('script').write(' '.join(ip_rule_cmd))
        kwargs.get('script').write('\n')

    return (0, '')


def add_firewall_rule(*args, **kwargs):
    """
    add a static firewall rule
    Parameters:
        kwargs:
            script : a reference to StringIO object to write the command for future use in script
        *args : argument list as passed to the iptables(8) command
    Return:
        (code,message): command code , on failure a message is sent back
    """
    fw_rule_cmd = ['/usr/sbin/iptables']
    fw_rule_cmd.extend(args)
    _logger.debug('adding fw rule : [%s]' % ' '.join(args))
    _out = sudo_utils.call_output(fw_rule_cmd)
    if _out is not None and len(_out) > 0:
        _logger.warning('add of firewall rule failed')
        return (1, _out)

    if kwargs.get('script'):
        kwargs.get('script').write(' '.join(fw_rule_cmd))
        kwargs.get('script').write('\n')

    return (0, '')


def remove_firewall_rule(*args):
    """
    remove a static firewall rule
    Parameters:
        *args : argument list as passed to the iptables(8) command
    Return:
        (code,message): command code , on failure a message is sent back
    """
    fw_rule_cmd = ['/usr/sbin/iptables']
    fw_rule_cmd.extend(args)
    _logger.debug('removing fw rule : [%s]' % ' '.join(args))
    _out = sudo_utils.call_output(fw_rule_cmd)
    if _out is not None and len(_out) > 0:
        _logger.warning('removal of firewall rule failed')
        return (1, _out)

    return (0, '')
