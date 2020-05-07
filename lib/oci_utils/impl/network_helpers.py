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
import signal
import logging
from socket import inet_ntoa
from struct import pack
from . import sudo_utils
import re
from netaddr import IPNetwork
import json

from io import StringIO

__all__ = ['get_interfaces', 'is_ip_reachable', 'add_route_table', 'delete_route_table',
           'network_prefix_to_mask',
           'add_static_ip_route',
           'add_static_ip_rule',
           'add_firewall_rule',
           'remove_firewall_rule',
           'remove_static_ip_routes',
           'remove_static_ip_rules',
           'get_network_namespace_infos']

_CLASS_NET_DIR = '/sys/class/net'
_NM_CONF_DIR = "/etc/NetworkManager/conf.d/"
_logger = logging.getLogger('oci-utils.net-helper')


def create_network_namespace(name):
    """
    Creates network namespace
    parameter:
      name : namespace name as str
    raise:
      exception :in case of error
    retur none
    """
    ret = sudo_utils.call(['/usr/sbin/ip', 'netns', 'add', name])
    if ret != 0:
        raise Exception('Cannot create network namespace')


def destroy_network_namespace(name):
    """
    Destroy network namespace
    parameter:
      name : namespace name as str
    raise:
      exception :in case of error
    retur none
    """
    ret = sudo_utils.call(['/usr/sbin/ip', 'netns', 'delete', name])
    if ret != 0:
        raise Exception('Cannot delete network namespace')


def _get_namespaces():
    """
    Gets list of network namespace
    Returns:
       list of names as string
    """
    return [name.split(b' ')[0] for name in subprocess.check_output(['/usr/sbin/ip', 'netns', 'list']).splitlines()]


def _get_link_infos(namespace):
    """
    Gets all namespace links information
    parameters:
    -----------
        namespace : the network namespace as str ('' means default)
    returns:
    --------
        list of
        {
            link : underlying link of thie interface (may be None)
            link_idx: underlying link index of thie interface (may be None)
            mac : mac address
            index : interface system index
            device : device name
            opstate : interface operational state : up, down, unknown
            addresses : [     # IP addresses (if any)
                 {
                        vlanid : VLAN ID (can be None)
                        address : IP address (if any)
                        address_prefix_l : IP address prefix length (if any)
                        address_subnet : IP address subnet (if any)
                        broadcast : IP address broadcast (if any),
                 }
            ]
            type: link type (as returned by kernel)
            flags: link flags
            is_vf: is this a vf ?
        }
    """
    _cmd = ['/usr/sbin/ip']
    if namespace and len(namespace) > 0:
        _cmd.extend(['-netns', namespace])

    _cmd.extend(['-details', '-json', 'address', 'show'])

    link_infos = sudo_utils.call_output(_cmd)
    if link_infos is None or not link_infos.strip():
        return []
    _vfs_mac = []
    # the ip command return a json array
    link_info_j = json.loads(link_infos.strip())
    _infos = []
    for obj in link_info_j:
        _addr_info = {'addresses': []}
        if 'addr_info'in obj:
            for a_info in obj['addr_info']:
                if a_info['family'] != 'inet':
                    continue
                if a_info.get('linkinfo') and a_info.get('linkinfo')['info_kind'] == 'vlan':
                    _vlanid = a_info.get('linkinfo')['info_data']['id']
                else:
                    _vlanid = None
                _addr_info['addresses'].append({
                    'vlanid': _vlanid,
                    'broadcast': a_info.get('broadcast'),
                    'address_prefix_l': a_info.get('prefixlen'),
                    'address': a_info.get('local'),
                    'address_subnet': str(IPNetwork('%s/%s' % (
                        a_info['local'],
                        a_info['prefixlen'])).network)
                })

        # grab VF mac if any
        if 'vfinfo_list' in obj:
            for _v in obj['vfinfo_list']:
                _vfs_mac.append(_v['mac'])

        if 'linkinfo' in obj:
            _addr_info['subtype'] = obj['linkinfo']['info_kind']

        _addr_info.update({
            'link': obj.get('link'),
            'link_idx': obj.get('link_index'),
            'device': obj.get('ifname'),
            'index': obj.get('ifindex'),
            'mac': obj.get('address').upper(),
            'opstate': obj.get('operstate'),
            'type': obj.get('link_type'),
            'flags': obj.get('flags')
        })
        _logger.debug('new system interface found : %s' % _addr_info)
        _infos.append(_addr_info)

    # now loop again to set the 'is_vf' flag
    for _info in _infos:
        if _info['mac'] in _vfs_mac:
            _info['is_vf'] = True
        else:
            _info['is_vf'] = False

    return _infos


def get_network_namespace_infos():
    """
    Retrieve par namespace network link info
    Returns:
    --------
      dict: namespace name indexed dict (can be empty) with per namespadce all link info  as dict
           {
              'ns name' : {
                  mac : mac address
                  index : interface system index
                  device : device name
                  opstate : interface operational state : up, down, unknown
                  addresses : [     IP addresses (if any)
                        {
                         vlanid : VLAN ID (can be None)
                         address : IP address (if any)
                         address_prefix_l : IP address prefix length (if any)
                         address_subnet : IP address subnet (if any)
                         broadcast : IP address broadcast (if any),
                        }
                     ]
                  type: link type
                  flags: link flags
              }
           }

    """
    _result = {}
    _ns_list = _get_namespaces()
    # also gather info from default namespace
    _ns_list.append('')
    for _ns in _ns_list:
        _result[_ns] = _get_link_infos(_ns)

    return _result


def get_interfaces():
    """
    Collect the information on all network interfaces.

    Returns
    -------
        dict
            The information on the interfaces.
            keys:
              physical : boolean, true if physical interface
              mac : mac address
              pci : PCI device
              virtfns : dict of virtual function
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
    If a table of that name already exists, silently aboret the operation
    Parameters
    ----------
    table_name : str
        name of the new table
    Returns
    -------
        bool
            True for success or table already exists, False for failure.
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
                # check if table already exits
                if line.split()[1] == table_name:
                    _logger.debug('routing table with name %s already exists' % table_name)
                    return True
    _new_table_num_to_use = -1
    for n in range(10, 255):
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
    except subprocess.CalledProcessError:
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
            namespace : network namespace in which to create the rule

        *args : argument list as passed to the ip-route(8) command
    Return:
        (code,message): command code , on failure a message is sent back
    """
    routing_cmd = ['/usr/sbin/ip']
    if kwargs and 'namespace' in kwargs:
        routing_cmd.extend(['-netns', kwargs['namespace']])
    routing_cmd.extend(['route', 'add'])
    routing_cmd.extend(args)
    _logger.debug('adding route : [%s]' % ' '.join(routing_cmd))
    _ret = sudo_utils.call(routing_cmd)
    if _ret != 0:
        _logger.warning('add of ip route failed')
        return (1, 'add of ip route failed')

    return (0, '')


def _compute_nm_conf_filename(mac):
    """
    Compute a filename from a mac address
      - capitalized it
      - replace ':' by '_'
      - add .conf at the end
    """
    return "%s.conf" % mac.replace(':', '_').upper()


def remove_mac_from_nm(mac):
    """
    Removes given MAC addres from the one managed by NetworkManager

    Parameters:
        mac : the mac address as string
    Return:
        None
    """
    if not mac:
        raise Exception('Invalid MAC address')

    if not os.path.exists(_NM_CONF_DIR):
        if sudo_utils.create_dir(_NM_CONF_DIR) != 0:
            raise Exception('Cannot create directory %s' % _NM_CONF_DIR)
        _logger.debug('%s created' % _NM_CONF_DIR)

    _cf = os.path.join(_NM_CONF_DIR, _compute_nm_conf_filename(mac))
    if sudo_utils.create_file(_cf) != 0:
        raise Exception('Cannot create file %s' % _cf)
    else:
        _logger.debug('%s created' % _cf)

    nm_conf = StringIO()
    nm_conf.write('[keyfile]\n')
    nm_conf.write('unmanaged-devices+=mac:%s\n' % mac)

    sudo_utils.write_to_file(_cf, nm_conf.getvalue())

    nm_conf.close()


def add_mac_to_nm(mac):
    """
    Adds given MAC addres from the one managed by NetworkManager

    Parameters:
        mac : the mac address as string
    Return:
        None
    """
    # if there is as nm conf file for this mac just remove it.
    _cf = os.path.join(_NM_CONF_DIR, _compute_nm_conf_filename(mac))
    if os.path.exists(_cf):
        sudo_utils.delete_file(_cf)
    else:
        _logger.debug('no NetworkManager file for %s' % mac)


def remove_ip_addr(device, ip_addr, namespace=None):
    """
    Removes an IP address on a given device
    Parameter:
        device : network device  as string
        ip_addr : the ip address as string
        [namespace]: network namespace as string
    Return:
        None
    raise Exception : renmoval has failed
    """
    _cmd = ['/usr/sbin/ip']
    if namespace and len(namespace) > 0:
        _cmd.extend(['-netns', namespace])
    _cmd.extend(['address', 'delete', ip_addr, 'dev', device])

    ret = sudo_utils.call(_cmd)
    if ret != 0:
        raise Exception('Cannot remove ip address')


def remove_ip_addr_rules(ip_addr):
    """
    Remove all ip rules set for an  ip address
    Parameter:
        ip_addr : the ip address as string
    Return:
        None
    """
    _lines = ''
    try:
        _lines = subprocess.check_output(['/sbin/ip', 'rule', 'list']).splitlines()
    except subprocess.CalledProcessError:
        pass
    # for any line (i.e rules) if the ip is involved , grab the priority number
    _matches = [_line for _line in _lines if ip_addr in _line.split()]
    # now grab the priority numbers
    # lines are like ''0:\tfrom all lookup local '' : take first item and remove trailing ':'
    prio_nums = [_l.split()[0][:-1] for _l in _matches]

    # now del all rules by priority number
    for prio_num in prio_nums:
        _ret = sudo_utils.call(['/sbin/ip', 'rule', 'del', 'pref', prio_num])
        if _ret != 0:
            _logger.warning('cannot delete rule [%s]' % prio_num)


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
    except subprocess.CalledProcessError:

        pass
    _logger.debug('rules found [%s]' % _lines)
    for _line in _lines:

        _command = ['/sbin/ip', 'rule', 'del']
        # all line listed are like '<rule number>:\t<rule as string> '
        # when underlying device is down (i.e virtual network is down) the command append '[detached]' we have to remove this
        _command.extend(re.compile("\d:\t").split(_line.strip())[1].replace('[detached] ', '').split(' '))
        _ret = sudo_utils.call(_command)
        if _ret != 0:
            _logger.warning('cannot delete rule [%s]' % ' '.join(_command))


def add_static_ip_rule(*args, **kwargs):
    """
    add a static rule
    Parameters:
        kwargs:
            device : network device on which assign the rule
        *args : argument list as passed to the ip-rule(8) command
    Return:
        (code,message): command code , on failure a message is sent back
    """
    ip_rule_cmd = ['/usr/sbin/ip', 'rule', 'add']
    ip_rule_cmd.extend(args)
    _logger.debug('adding rule : [%s]' % ' '.join(args))
    _ret = sudo_utils.call(ip_rule_cmd)
    if _ret != 0:
        _logger.warning('add of ip rule failed')
        return (1, 'add of ip rule failed')

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
    _ret = sudo_utils.call(fw_rule_cmd)
    if _ret != 0:
        _logger.warning('add of firewall rule failed')
        return (1, 'add of firewall rule failed')

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
    _ret = sudo_utils.call(fw_rule_cmd)
    if _ret != 0:
        _logger.warning('removal of firewall rule failed')
        return (1, 'removal of firewall rule failed')

    return (0, '')


def kill_processes_in_namespace(namespace):
    """
    Kills remaining process within a network namespace

    parameters:
    -----------
        namespace : the namespace name as str
    Returns:
    --------
        None
    """
    _logger.debug('killing process for namespace [%s]' % namespace)
    _out = sudo_utils.call_output(['/usr/sbin/ip', 'netns', 'pids', namespace])
    # one pid per line
    if _out:
        for pid in _out.splitlines():
            try:
                os.kill(int(pid), signal.SIGKILL)
            except (ValueError, OSError) as e:
                _logger.warning('Cannot terminate [%s]: %s ' % (pid, str(e)))
