# oci-utils
#
# Copyright (c) 2018, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Helper module around network information.
"""
import ipaddress
import os
import os.path
import socket
import subprocess
import signal
import logging
from socket import inet_ntoa
from struct import pack
import re
import json
from pprint import pformat
from io import StringIO
from netaddr import IPNetwork
from oci_utils import where_am_i
from . import IP_CMD
from . import sudo_utils


__all__ = ['is_valid_ip_address',
           'is_valid_ipv4_address',
           'is_valid_ipv6_address',
           'is_link_local_address',
           'ip_cmd_version',
           'ipv_version',
           'is_network_namespace_exists',
           'create_network_namespace',
           'destroy_network_namespace',
           'get_network_namespace_infos',
           'get_interfaces',
           'is_ip_reachable',
           'add_route_table',
           'delete_route_table',
           'network_prefix_to_mask',
           'remove_static_ip_routes',
           'add_static_ip_route4',
           'add_static_ip_route6',
           'add_static_ip_route',
           'remove_mac_from_nm',
           'add_mac_to_nm',
           'remove_ip_addr',
           'remove_ip_rules',
           'remove_static_ip_rules',
           'add_static_ip_rule',
           'add_firewall_rule',
           'remove_firewall_rule',
           'kill_processes_in_namespace']


_CLASS_NET_DIR = '/sys/class/net'
_NM_CONF_DIR = '/etc/NetworkManager/conf.d/'
_ROUTE_TABLES = '/etc/iproute2/rt_tables'
_ROUTE_TABLES_BCK = _ROUTE_TABLES + '.bck'
_logger = logging.getLogger('oci-utils.network-helpers')


def is_valid_ip_address(ip_addr):
    """
    Verify if ip_address is a valid ipv4 or ipv6 address.

    Parameters
    ----------
    ip_addr: str
        The ip address.

    Returns
    -------
        IPv[4|6]Address on success, False otherwise.
    """
    _logger.debug('%s: %s', where_am_i(), ip_addr)
    try:
        ipv_address = ipaddress.ip_address(ip_addr)
        return ipv_address
    except ValueError as e:
        return False
    except Exception as e:
        return False


def is_valid_ipv4_address(ip_addr):
    """
    Verify if the provided address is a valid ipv4 address.

    Parameters
    ----------
    ip_addr: str
        The ip address.

    Returns
    -------
        IPv4Address on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    ip_instance = is_valid_ip_address(ip_addr)
    return ip_instance if isinstance(ip_instance, ipaddress.IPv4Address) else False


def is_valid_ipv6_address(ip_addr):
    """
    Verify if the provided address is a valid ipv6 address.

    Parameters
    ----------
    ip_addr: str
        The ip address.

    Returns
    -------
        IPv6Address on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    ip_instance = is_valid_ip_address(ip_addr)
    return ip_instance if isinstance(ip_instance, ipaddress.IPv6Address) else False


def is_link_local_address(ip_addr):
    """
    Verify if the provided ip address is a link local address.

    Parameters
    ----------
    ip_addr: str
        The ip address.

    Returns
    -------
        bool: True if link_local, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    try:
        this_ipaddr = ipaddress.ip_address(ip_addr)
    except Exception as e:
        raise Exception('%s' % str(e))
    return this_ipaddr.is_link_local


def ipv_version(ip_addr):
    """
    Find ip version.

    Parameters
    ----------
    ip_addr: str
        The ip address.

    Returns
    -------
        int: the ip version [4|6]
    """
    _logger.debug('%s', where_am_i())
    ip_instance = is_valid_ip_address(ip_addr)
    if isinstance(ip_instance, ipaddress.IPv4Address):
        return 4
    if isinstance(ip_instance, ipaddress.IPv6Address):
        return 6
    return False


def ip_cmd_version(ip_addr):
    """
    Generates ip command depended on version of op address.

    Parameters
    ----------
    ip_addr: str
        The ip address

    Returns
    -------
        list: the ip command version.
    """
    _logger.debug('%s', where_am_i())
    if is_valid_ipv4_address(ip_addr):
        return [IP_CMD, '-4']
    if is_valid_ipv6_address(ip_addr):
        return [IP_CMD, '-6']
    raise Exception('Invalid ip address %s' % ip_addr)


def is_network_namespace_exists(name):
    """
    Checks that a namespace exist or not

    Parameter
    ---------
      name : namespace name as str
    Returns
    -------
       True if exists False otherwise
    """
    _logger.debug('%s', where_am_i())
    return os.path.exists('/var/run/netns/%s' % name)


def create_network_namespace(name):
    """
    Creates network namespace

    Parameter
    ---------
      name : namespace name as str

    raise
    ------
      exception :in case of error
    """
    _logger.debug('%s: %s', where_am_i(), name)
    ret = sudo_utils.call([IP_CMD, 'netns', 'add', name])
    if ret != 0:
        raise Exception('Cannot create network namespace')


def destroy_network_namespace(name):
    """
    Destroy network namespace

    Parameters
    ----------
      name : namespace name as str

    Raises
    ------
      Exception :in case of error
    """
    _logger.debug('%s: %s', where_am_i(), name)
    ret = sudo_utils.call([IP_CMD, 'netns', 'delete', name])
    if ret != 0:
        raise Exception('Cannot delete network namespace')


def _get_namespaces():
    """
    Gets list of network namespace

    Returns
    -------
       list of namespaces
    """
    _logger.debug('%s', where_am_i())
    _cmd = [IP_CMD, 'netns', 'list']
    _logger.debug('Executing %s', _cmd)
    return [name.split(b' ')[0] for name in subprocess.check_output(_cmd).splitlines()]


def _get_link_info_dict(namespace):
    """
    Get and format the namespace data, ipv4 and ipv6
    .
    Parameters
    ----------
    namespace: str
        The network namespace as str ('' means default)

    Returns
    -------
        list: link infos json formatted.
    """
    _logger.debug('%s: %s', where_am_i(), namespace)
    _cmd = [IP_CMD]
    if namespace and len(namespace) > 0:
        _cmd.extend(['-netns', namespace])
    _cmd.extend(['-details', '-json', 'address', 'show'])
    _logger.debug('Executing %s', _cmd)
    link_infos_json = sudo_utils.call_output(_cmd).decode('utf-8')
    _logger.debug('Result json: %s', link_infos_json)
    if link_infos_json is None or not link_infos_json.strip():
        return []
    #
    # the ip command returns a json array, convert to list of dict
    link_info = json.loads(link_infos_json.strip())
    # _logger.debug(link_info)
    _logger.debug('Result dict:\n%s', pformat(link_info, indent=4))

    return link_info


def _get_address_info(address_info):
    """
    Get required address information.

    Parameters
    ----------
    address_info: dict, the address data.

    Returns
    -------
        dict: the addres info.
    """
    _logger.debug('%s:\n%s', where_am_i(), pformat(address_info, indent=4))
    if address_info['family'] not in ['inet', 'inet6']:
        return None
    if address_info.get('linkinfo') and address_info.get('linkinfo')['info_kind'] == 'vlan':
        _vlanid = address_info.get('linkinfo')['info_data']['id']
    else:
        _vlanid = None

    addr_info = {
        'vlanid': _vlanid,
        'broadcast': address_info.get('broadcast'),
        'address_prefix_l': address_info.get('prefixlen'),
        'address': address_info.get('local'),
        'address_subnet': str(IPNetwork('%s/%s' % (
            address_info['local'],
            address_info['prefixlen'])).network)
    }
    return addr_info


def _get_link_infos(namespace):
    """
    Get all namespace links information.

    parameters:
    -----------
        namespace : the network namespace as str ('' means default)
    returns:
    --------
        list of
        {
            link : underlying link of the interface (may be None)
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
    _logger.debug('%s: %s', where_am_i(), namespace)
    link_info_d = _get_link_info_dict(namespace)
    _vfs_mac = []
    _infos = []
    for obj in link_info_d:
        _addr_info = {'addresses': []}
        _logger.debug('Object from link info:\n %s', pformat(obj, indent=4))
        _logger.debug('Device name: %s', obj['ifname'])
        if 'addr_info' in obj:
            for a_info in obj['addr_info']:
                _one_addr_info = _get_address_info(a_info)
                if _one_addr_info:
                    _addr_info['addresses'].append(_one_addr_info)
                _logger.debug('addr_info:\n%s', pformat(_addr_info['addresses'][-1], indent=4))
        #
        # grab VF mac if any
        if 'vfinfo_list' in obj:
            _logger.debug('_vfinfo_list')
            for _v in obj['vfinfo_list']:
                if 'mac' in _v:
                    _vfs_mac.append(_v['mac'])
        #
        # grab linkinfo type if any
        if 'linkinfo' in obj:
            _addr_info['subtype'] = obj['linkinfo']['info_kind']
        #
        # complete address info
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
        _logger.debug('New system interface found:\n%s', pformat(_addr_info, indent=4))
        _infos.append(_addr_info)
    #
    # now loop again to set the 'is_vf' flag
    for _info in _infos:
        if _info['mac'] in _vfs_mac:
            _info['is_vf'] = True
        else:
            _info['is_vf'] = False

    _logger.debug('__infos:\n%s', pformat(_infos, indent=4))
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
    _logger.debug('%s', where_am_i())
    _result = {}
    _ns_list = _get_namespaces()
    #
    # also gather info from default namespace
    _ns_list.append(b'')

    for _ns in _ns_list:
        _result[_ns] = _get_link_infos(_ns)
    _logger.debug('Network namespace infos:\n%s', pformat(_result, indent=4))
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
    _logger.debug('%s', where_am_i())
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

                # TODO: find a better way to get mac addresses for virtual functions
                for line in subprocess.check_output([IP_CMD, 'link', 'show', n]).splitlines():
                    line = line.strip().decode()
                    if not line.startswith('vf '):
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

        for _, v in virt_fns.items():
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
    _logger.debug('%s: %s', where_am_i(), ipaddr)
    assert isinstance(ipaddr, str), 'IPaddr must be a valid string [%s]' % str(ipaddr)
    assert (isinstance(port, int) and port > 0), 'Port must be positive value [%s]' % str(port)

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
    If a table of that name already exists, silently abort the operation

    Parameters
    ----------
    table_name : str
        name of the new table
    Returns
    -------
        bool
            True for success or table already exists, False for failure.
    """
    _logger.debug('%s: %s', where_am_i(), table_name)
    # first , find a free number for the table
    tables_num = []
    _all_new_lines = []
    with open(_ROUTE_TABLES) as f:
        for line in f.readlines():
            _all_new_lines.append(line)
            if len(line.strip()) > 0 and not line.startswith('#'):
                # trust the format of that file
                tables_num.append(int(line.split()[0]))
                # check if table already exits
                if line.split()[1] == table_name:
                    _logger.debug('Routing table with name %s already exists', table_name)
                    return True
    _new_table_num_to_use = -1
    for n in range(10, 255):
        if n not in tables_num:
            _new_table_num_to_use = n
            break
    _logger.debug('New table index : %d', _new_table_num_to_use)
    _all_new_lines.append('%d\t%s\n' % (_new_table_num_to_use, table_name))

    if sudo_utils.copy_file(_ROUTE_TABLES, _ROUTE_TABLES_BCK) != 0:
        _logger.debug('Cannot backup file [%s] to %s', _ROUTE_TABLES, _ROUTE_TABLES_BCK)
        return False
    if sudo_utils.write_to_file(_ROUTE_TABLES, ''.join(_all_new_lines)) != 0:
        _logger.debug('Cannot write new content to  file [%s]', _ROUTE_TABLES)
        sudo_utils.copy_file(_ROUTE_TABLES_BCK, _ROUTE_TABLES)
        return False

    sudo_utils.delete_file(_ROUTE_TABLES_BCK)

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
    _logger.debug('%s: %s', where_am_i(), table_name)
    _all_new_lines = []
    with open(_ROUTE_TABLES) as f:
        _all_lines = f.readlines()
        for line in _all_lines:
            # format is '<index>\t<table name>'
            _s_l = line.split()
            if len(_s_l) > 1 and _s_l[1] == table_name:
                # found the table name , skip this line
                continue
            _all_new_lines.append(line)

    if sudo_utils.copy_file(_ROUTE_TABLES, _ROUTE_TABLES_BCK) != 0:
        _logger.debug('Cannot backup file [%s] to %s', _ROUTE_TABLES, _ROUTE_TABLES_BCK)
        return False
    if sudo_utils.write_to_file(_ROUTE_TABLES, ''.join(_all_new_lines)) != 0:
        _logger.debug('Cannot write new content to  file [%s]', _ROUTE_TABLES)
        sudo_utils.copy_file(_ROUTE_TABLES_BCK, _ROUTE_TABLES)
        return False
    sudo_utils.delete_file(_ROUTE_TABLES_BCK)
    return True


def network_prefix_to_mask(prefix):
    """
    Converts an ipv4 prefix to a netmask address

    Parameters
    ----------
       prefix: int
        the prefix
    Returns:
        The netmask address
    Exemple:
       network_prefix_to_mask(22) -> '255.255.252.0'
    """
    _logger.debug('%s: %s', where_am_i(), prefix)
    bits = 0xffffffff ^ (1 << 32 - prefix) - 1
    return inet_ntoa(pack('>I', bits))


def remove_static_ip_route4(link_name):
    """
    Deletes all ipv4 routes related to a network device.

    Parameter
    ----------
       link_name : str
          the ip link name
    Returns
    ------
        None
    """
    _logger.debug('%s: %s', where_am_i(), link_name)
    _logger.debug('Looking for ipv4 routes for dev=%s', link_name)
    _lines = []
    try:

        _lines = subprocess.check_output([IP_CMD, '-4', 'route', 'show', 'dev', link_name]).splitlines()
    except subprocess.CalledProcessError:
        pass
    _logger.debug('Routes found [%s]', _lines)
    for _line in _lines:
        _command = [IP_CMD, '-4', 'route', 'del']
        _command.extend(_line.decode().strip().split(' '))
        _out = sudo_utils.call_output(_command)
        if _out is not None and len(_out) > 0:
            _logger.warning('Removal of ipv4 route (%s) failed', _line)


def remove_static_ip_route6(link_name):
    """
    Deletes all ipv6 routes related to a network device.

    Parameter
    ----------
       link_name : str
          the ip link name
    Returns
    ------
        None
    """
    _logger.debug('%s: %s', where_am_i(), link_name)
    _logger.debug('Looking for ipv6 routes for dev=%s', link_name)
    _lines = []
    try:
        _lines = subprocess.check_output([IP_CMD, '-6', 'route', 'show', 'dev', link_name]).splitlines()
    except subprocess.CalledProcessError:
        pass
    _logger.debug('Routes found [%s]', _lines)
    for _line in _lines:
        _command = [IP_CMD, '-6', 'route', 'del']
        _command.extend(_line.decode().strip().split(' '))
        _out = sudo_utils.call_output(_command)
        if _out is not None and len(_out) > 0:
            _logger.warning('Removal of ipv6 route (%s) failed', _line)


def remove_static_ip_routes(link_name):
    """
    Deletes all routes related to a network device.

    Parameters
    ----------
       link_name : str
          the ip link name
    Returns
    ------
        None
    """
    _logger.debug('%s: %s', where_am_i(), link_name)
    # ipv4
    remove_static_ip_route4(link_name)
    # ipv6
    remove_static_ip_route6(link_name)


def add_static_ip_route4(*args, **kwargs):
    """
    Add a static ipv4 route

    Parameter
    ----------
        kwargs:
            namespace : network namespace in which to create the rule

        args : argument list as passed to the ip-route(8) command
    Returns
    ------
        (code,message): command code , on failure a message is sent back
    """
    _logger.debug('%s: \n%s\n%s', where_am_i(), args, kwargs)
    return add_static_ip_route([IP_CMD, '-4'], *args, **kwargs)


def add_static_ip_route6(*args, **kwargs):
    """
    Add a static ipv6 route

    Parameter
    ----------
        kwargs:
            namespace : network namespace in which to create the rule

        args : argument list as passed to the ip-route(8) command
    Returns
    ------
        (code,message): command code , on failure a message is sent back
    """
    _logger.debug('%s: \n%s\n%s', where_am_i(), args, kwargs)
    return add_static_ip_route([IP_CMD, '-6'], *args, **kwargs)


def add_static_ip_route(route_cmd, *args, **kwargs):
    """
    Add a static route

    Parameter
    ----------
        route_cmd: list
            version specific ip route command.
        kwargs:
            namespace : network namespace in which to create the rule

        args : argument list as passed to the ip-route(8) command
    Returns
    ------
        (code,message): command code , on failure a message is sent back
    """
    _logger.debug('%s: \n%s\n%s', where_am_i(), args, kwargs)
    routing_cmd = route_cmd
    if kwargs and 'namespace' in kwargs:
        routing_cmd.extend(['-netns', kwargs['namespace']])
    routing_cmd.extend(['route', 'add'])
    routing_cmd.extend(args)
    _logger.debug('Adding route : [%s]', ' '.join(routing_cmd))
    _ret = sudo_utils.call(routing_cmd)
    if _ret == 2:
        _logger.debug('Route %s already exists.', args)
        return 0, 'Route already exists.'
    if _ret != 0:
        _logger.warning('Add of ip route failed')
        return 1, 'Add of ip route failed'
    return 0, ''


def _compute_nm_conf_filename(mac):
    """
    Compute a filename from a mac address
      - capitalized it
      - replace ':' by '_'
      - add .conf at the end
    """
    _logger.debug('%s: %s', where_am_i(), mac)
    return "%s.conf" % mac.replace(':', '_').upper()


def remove_mac_from_nm(mac):
    """
    Removes given MAC addres from the ones managed by NetworkManager

    Parameter
    ----------
        mac : the mac address as string
    Returns
    ------
        None
    """
    _logger.debug('%s: %s', where_am_i(), mac)
    if not mac:
        raise Exception('Invalid MAC address')

    if not os.path.exists(_NM_CONF_DIR):
        if sudo_utils.create_dir(_NM_CONF_DIR) != 0:
            raise Exception('Cannot create directory %s' % _NM_CONF_DIR)
        _logger.debug('%s created', _NM_CONF_DIR)

    _cf = os.path.join(_NM_CONF_DIR, _compute_nm_conf_filename(mac))
    if sudo_utils.create_file(_cf) != 0:
        raise Exception('Cannot create file %s' % _cf)

    _logger.debug('%s created', _cf)

    nm_conf = StringIO()
    nm_conf.write('[keyfile]\n')
    nm_conf.write('unmanaged-devices+=mac:%s\n' % mac)

    sudo_utils.write_to_file(_cf, nm_conf.getvalue())

    nm_conf.close()


def add_mac_to_nm(mac):
    """
    Adds given MAC addres from the one managed by NetworkManager

    Parameter
    ----------
        mac : the mac address as string
    Returns
    -------
        None
    """
    _logger.debug('%s: %s', where_am_i(), mac)
    # if there is as nm conf file for this mac just remove it.
    _cf = os.path.join(_NM_CONF_DIR, _compute_nm_conf_filename(mac))
    if os.path.exists(_cf):
        sudo_utils.delete_file(_cf)
    else:
        _logger.debug('No NetworkManager file for %s', mac)


def remove_ip_addr(device, ip_addr, namespace=None):
    """
    Removes an IP address on a given device

    Parameters
    ----------
        device : network device  as string
        ip_addr : the ip address as string
        [namespace]: network namespace as string
    Returns
    -------
        None
    raise Exception : renmoval has failed
    """
    _logger.debug('%s: %s', where_am_i(), ip_addr)
    _cmd = [IP_CMD]
    if namespace and len(namespace) > 0:
        _cmd.extend(['-netns', namespace])
    _cmd.extend(['address', 'delete', ip_addr, 'dev', device])

    ret = sudo_utils.call(_cmd)
    if ret != 0:
        raise Exception('Cannot remove ip address')


def remove_ip_rules(ip_addr):
    """
    Remove all ip rules set for an  ip address

    Parameter
    ---------
        ip_addr : the ip address as string
    Returns
    -------
        None
    """
    _logger.debug('%s: %s', where_am_i(), ip_addr)
    _cmd = ip_cmd_version(ip_addr)
    if not _cmd:
        raise Exception('%s is not a valid ip address.' % ip_addr)
    _lines = ''
    try:
        _cmd.extend(['rule', 'list'])
        _logger.debug('Executing %s', _cmd)
        _lines = subprocess.check_output(_cmd).decode('utf-8').splitlines()
    except subprocess.CalledProcessError:
        pass
    # for any line (i.e rules) if the ip is involved , grab the priority number
    _matches = [_line for _line in _lines if ip_addr in _line.split()]
    _logger.debug('matches %s', _matches)
    # now grab the priority numbers
    # lines are like ''0:\tfrom all lookup local '' : take first item and remove trailing ':'
    prio_nums = [_l.split()[0][:-1] for _l in _matches]
    _logger.debug('prio_nums %s', prio_nums)
    # now del all rules by priority number
    for prio_num in prio_nums:
        _cmd = ip_cmd_version(ip_addr)
        _cmd.extend(['rule', 'del', 'pref', prio_num])
        _logger.debug('Executing %s', _cmd)
        _ret = sudo_utils.call(_cmd)
        if _ret != 0:
            _logger.warning('Cannot delete rule [%s]', prio_num)


def remove_static_ip_rules46(link_name, ipversion):
    """
    Delete all ipv4 or ipv6 rules related to a network device.

    Parameters
    ----------
    link_name: str
        The device.
    ipversion: int
        The ip version.

    Returns
    -------
        no return value.
    """
    _logger.debug('%s: %s', where_am_i(), link_name)
    _logger.debug('Looking for ip 4 rules for dev=%s', link_name)
    _lines = []

    ipcmd = [IP_CMD, '-%d' % ipversion]
    try:
        _cmd = [ipcmd, 'rule', 'show', 'lookup', link_name]
        _logger.debug('Executing [%s]', _cmd)
        _lines = subprocess.check_output(_cmd).splitlines()
    except subprocess.CalledProcessError:
        pass
    _logger.debug('Rules found [%s]', _lines)

    for _line in _lines:
        _command = [ipcmd, 'rule', 'del']
        # all line listed are like '<rule number>:\t<rule as string> '
        # when underlying device is down (i.e. virtual network is down)
        # the command append '[detached]' we have to remove this
        _command.extend(re.compile(r'\d:\t').split(_line.decode().strip())[1].replace('[detached] ', '').split(' '))
        _out = sudo_utils.call_output(_command)
        if _out is not None and len(_out) > 0:
            _logger.warning('Cannot delete rule [%s]: %s', ' '.join(_command), str(_out))


def remove_static_ip_rules(link_name):
    """
    Deletes all rules related to a network device

    Parameters
    ----------
       link_name : str
          the ip link name
    Returns
    -------
        None
    """
    _logger.debug('%s: %s', where_am_i(), link_name)
    _logger.debug('Looking for ip 6 rules for dev=%s', link_name)
    # ipv 4
    remove_static_ip_rules46(link_name, 4)
    # ipv 6
    remove_static_ip_rules46(link_name, 6)


def add_static_ip_rule4(*args, **kwargs):
    """
    Add a static rule for ipv4 address.

    Parameters
    ----------
    args: argument list as passed to the ip-rule(8) command
    kwargs: na

    Returns
    -------
        (code,message): command code , on failure a message is sent back
    """
    _logger.debug('%s: %s', where_am_i(), args)
    ip_cmd4 = [IP_CMD, '-4']
    return_code, message = add_static_ip_rule(ip_cmd4, *args, **kwargs)
    return return_code, message


def add_static_ip_rule6(*args, **kwargs):
    """
    Add a static rule for ipv4 address.

    Parameters
    ----------
    args: argument list as passed to the ip-rule(8) command
    kwargs: NA

    Returns
    -------
        (code,message): command code , on failure a message is sent back
    """
    _logger.debug('%s: %s', where_am_i(), args)
    ip_cmd6 = [IP_CMD, '-6']
    return_code, message = add_static_ip_rule(ip_cmd6, *args, **kwargs)
    return return_code, message


def add_static_ip_rule(ip_cmd, *args, **kwargs):
    """
    Add a static rule

    Parameters
    ----------
        ip_cmd: str
            ip command with version.
        kwargs:
            device : network device on which assign the rule
        args : argument list as passed to the ip-rule(8) command
    Return
    ------
        (code,message): command code , on failure a message is sent back
    """
    _logger.debug('%s: %s', where_am_i(), args)
    ip_rule_cmd = ip_cmd
    ip_rule_cmd.extend(['rule', 'add'])
    ip_rule_cmd.extend(args)
    _logger.debug('Adding rule : [%s]', ' '.join(ip_rule_cmd))
    _ret = sudo_utils.call(ip_rule_cmd)
    if _ret != 0:
        _logger.warning('Adding ip rule failed')
        return 1, 'Adding ip rule failed'

    return 0, ''


def add_firewall_rule(*args, **kwargs):
    """
    Add a static firewall rule

    Parameters
    ----------
        kwargs:
           script : a reference to StringIO object to write the command for future use in script
        *args : argument list as passed to the iptables(8) command
    Returns
    -------
        (code,message): command code , on failure a message is sent back
    """
    _logger.debug('%s: \n%s\n%s', where_am_i(), args, kwargs)
    fw_rule_cmd = ['/usr/sbin/iptables']
    fw_rule_cmd.extend(args)
    _logger.debug('Adding fw rule : [%s]', ' '.join(args))
    _ret = sudo_utils.call(fw_rule_cmd)
    if _ret != 0:
        _logger.warning('Add of firewall rule failed')
        return 1, 'add of firewall rule failed'
    if kwargs.get('script'):
        kwargs.get('script').write(' '.join(fw_rule_cmd))
        kwargs.get('script').write('\n')
    return 0, ''


def remove_firewall_rule(*args):
    """
    Remove a static firewall rule

    Parameters
    ----------
        *args : argument list as passed to the iptables(8) command
    Returns
    -------
        (code,message): command code , on failure a message is sent back
    """
    _logger.debug('%s: %s', where_am_i(), args)
    fw_rule_cmd = ['/usr/sbin/iptables']
    fw_rule_cmd.extend(args)
    _logger.debug('Removing fw rule : [%s]', ' '.join(args))
    _ret = sudo_utils.call(fw_rule_cmd)
    if _ret != 0:
        _logger.warning('Removal of firewall rule failed')
        return 1, 'removal of firewall rule failed'

    return 0, ''


def kill_processes_in_namespace(namespace):
    """
    Kills remaining process within a network namespace

    Parameters:
    -----------
        namespace : the namespace name as str
    Returns:
    --------
        None
    """
    _logger.debug('%s: %s', where_am_i(), namespace)
    _out = sudo_utils.call_output([IP_CMD, 'netns', 'pids', namespace])
    # one pid per line
    if _out:
        for pid in _out.splitlines():
            try:
                os.kill(int(pid), signal.SIGKILL)
            except (ValueError, OSError) as e:
                _logger.warning('Cannot terminate [%s]: %s ', pid, str(e))
