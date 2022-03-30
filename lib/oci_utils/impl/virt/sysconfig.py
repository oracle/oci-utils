# oci-utils
#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" System configuration.
"""
import os
import logging
import stat
from .. import sudo_utils
from ..network_helpers import network_prefix_to_mask

_logger = logging.getLogger('oci-utils.sysconfig')

__sysconfig = '/etc/sysconfig'
__netscripts = __sysconfig + '/network-scripts'
__iface_prefix = 'ifcfg-'
__ifup = '/usr/sbin/ifup'
__ifdown = '/usr/sbin/ifdown'
__nmcli = '/bin/nmcli'

def parse_env_file(f):
    """
    Parse a file for 'key=val' strings.

    Parameters
    ----------
    f :
        The file descriptor.

    Returns
    -------
        dict
            A dictionary with valid key val.
    """
    ret = {}
    for l in f:
        lstripped = l.strip()
        if lstripped.startswith('#'):
            # Skip comments
            continue
        c = lstripped.split('=')
        if len(c) != 2:
            # Skip malformed lines
            continue

        ret[c[0]] = c[1]

    return ret


def read_network_file(path):
    """
    Parse a file.

    Parameters
    ----------
    path : str
        The filename, full path.

    Returns
    -------
        dict
            The parsed data on success.
            None in case of failure.
    Raises
    ------
        Reraises exception raised at open or reading the file.
    """

    try:
        with open(path, 'r') as f:
            return parse_env_file(f)
    except Exception as e:
        raise e


def read_directory_files(path, reader, filt=None, fmt=None):
    """

    Parameters
    ----------
    path : str
        The filename, full path.
    reader : func
        The function for reading and parsing the file.
    filt : func
        A filter function.
    fmt : func
        A format function.

    Returns
    -------
        dict
            The dictionary containing the filtered data from the file.

    Raises
    ------
        Reraises eventual exceptions.
    """
    ret = {}
    if not fmt:
        def fmt(x):
            return x
    try:
        for d in os.listdir(path):
            p = '{}/{}'.format(path, d)
            if not filt or filt(d):
                ret[fmt(d)] = reader(p)

    except Exception as e:
        raise e
    return ret


def read_network_config():
    """
    Read and parse the network configuration.

    Returns
    -------
        dict
            The network configuration.
    """

    return read_directory_files(__netscripts, read_network_file,
                                lambda x: x.startswith(__iface_prefix),
                                lambda x: x[len(__iface_prefix):])


def _not_used_write_env_file(f, conf):
    """
    Write the configuration to a file.

    Parameters
    ----------
    f :
        The file descriptor.
    conf : dict
        The configuration key, value's.

    Returns
    -------
        No return value.
    """
    for k, v in conf:
        f.write('{}={}'.format(k, v))


def build_env_file(conf):
    """
    Construct the key=val string from the data structurr.

    Parameters
    ----------
    conf : dict
        The key value's

    Returns
    -------
        str
            The key=val strings.
    """
    return "\n".join(['{}={}'.format(k, v) for k, v in conf.items()])


def write_network_file(path, conf):
    """
    Write the key=val string to a file.

    It's not possible to use native file output because these files must
    be written with euid=0.  Of course, there is no way to elevate this
    process.  Instead, shell out so that sudo can be applied.

    Parameters
    ----------
    path :  str
        The full path of the file.
    conf : dict
        The configuration key, value's.

    Returns
    -------
        No return value.
    """
    sudo_utils.call(
        ['sh', '-c', 'echo \'{}\' > {}'.format(build_env_file(conf), path)])


def write_directory_files(path, conf, writer, fmt=None):
    """

    Parameters
    ----------
    path : str
        The filename, full path.
    conf : dict
        The data.
    writer : func
        The function for reading and parsing the file.
    fmt : func
        A format function.

    Returns
    -------
        No return value.

    Raises
    ------
        Reraises eventual exceptions.
    """
    if not fmt:
        def fmt(x):
            return x
    try:
        for name, data in conf.items():
            f = '{}/{}'.format(path, fmt(name))
            writer(f, data)
    except Exception as e:
        raise e


def write_network_config(data):
    """
    Write the network configuration to /etc/sysconfig/network-scripts

    Parameters
    ----------
    data : dict
        The data.

    Returns
    -------
        No return value.
    """

    write_directory_files(__netscripts, data, write_network_file,
                          lambda x: __iface_prefix + x)


def _not_used_apply_network_config():
    """
    Restart the network service.

    Returns
    -------
        bool
            True on successful restart of the network service,
            False otherwise.
    """
    # If dhclient is running, then network.service cannot restart correctly.
    # There is nothing
    # in the OS that kills off dhclient, so it must be done here.
    sudo_utils.call(['/usr/bin/pkill', 'dhclient'])

    # Restart the network service to apply most of the relevant changes.
    # Note that network.service
    # does not have the ability to remove interfaces, so any virtual
    # interfaces must be manually
    # deleted
    if sudo_utils.call(['/usr/sbin/service', 'network', 'restart']):
        return False

    # Poll for interface existence
    return True


def _is_exec(command):
    """
    Verify if a filename exists and is executable.

    Parameters
    ----------
    command: str
        The filename.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    if os.path.exists(command) and os.access(command, os.F_OK | os.X_OK) and not os.path.isdir(command):
        cmd_mod = os.stat(command).st_mode
        return bool(cmd_mod & stat.S_IXUSR or cmd_mod & stat.S_IXGRP or cmd_mod & stat.S_IXOTH)
    return False


def interfaces_up(ifaces):
    """
    Bring the interfaces up.

    Parameters
    ----------
    ifaces : list
        The list of network interfaces.

    Returns
    -------
        bool
            True on success, False otherwise.
    """

    if _is_exec(__ifup):
        for i in ifaces:
            if sudo_utils.call([__ifup, i],True):
                _logger.debug('Cannot bring up interface %s', i)
                return False
        return True
    elif _is_exec(__nmcli):
        for i in ifaces:
            if sudo_utils.call([__nmcli, 'connection', 'up',i], True):
                _logger.debug('Cannot bring up interface %s', i)
                return False
        return True
    return False


def delete_directory_files(path, files, fmt=None):
    """
    Delete a list of files in a directory.

    Parameters
    ----------
    path : str
        The full path of the directory.
    files : list
        The list of files.
    fmt : func
        The formatter function.

    Returns
    -------
        No return value.
    """
    if not fmt:
        def fmt(x):
            return x
    for name in files:
        sudo_utils.delete_file('{}/{}'.format(path, fmt(name)))


def delete_virtual_interfaces(data):
    """
    Bring down network interfaces.

    Parameters
    ----------
    data : list
        The list of network interfaces.

    Returns
    -------
        No return value.
    """
    if _is_exec(__ifdown):
        for name in data:
            sudo_utils.call([__ifdown, name])
            _logger.debug('interface %s down.', name)
    elif _is_exec(__nmcli):
        for name in data:
            sudo_utils.call([__nmcli, 'connection', 'down', name])
            _logger.debug('interface %s down.', name)


def delete_network_config(data):
    """
    Delete the network configuration.

    Parameters
    ----------
    data : list
        The list of network interfaces.

    Returns
    -------
        No return value.
    """
    delete_virtual_interfaces(data)
    delete_directory_files(__netscripts, data, lambda x: __iface_prefix + x)


def make_vf_name(name):
    """
    Create a virtual name

    Parameters
    ----------
    name : str
        The vf name name.

    Returns
    -------
        The vf name.
    """
    return name


def make_vlan_name(parent, vlan_id):
    """
    Create a VLAN name.

    Parameters
    ----------
    parent : str
        The parent interface.
    vlan_id :
        The vlan id.

    Returns
    -------
        str
            The VLAN name.
    """
    return '{}.{}'.format(parent, vlan_id)


def make_vf(name, mac, ip=None, prefix=None):
    """
    Create a network interface file contents.

    Parameters
    ----------
    name : str
        The network interface name.
    mac : str
        The network interface MAC address.
    ip : str
        The Ip for the new interface
    prefix :
        the prefix from wich to compute the netmask

    Returns
    -------
        str
            The network interface file contents.
    """
    name = make_vf_name(name)
    if ip and prefix:
        return ('vm-{}'.format(name),
                {'DEVICE': name,
                 'MACADDR': mac,
                 'NM_CONTROLLED': 'no',
                 'BOOTPROTO': 'none',
                 'ONBOOT': 'yes',
                 'MTU': '9000',
                 'NOZEROCONF': 'yes',
                 'IPADDR': ip,
                 'NETMASK': network_prefix_to_mask(prefix)
                 }
                )

    return ('vm-{}'.format(name),
                {'DEVICE': name,
                 'MACADDR': mac,
                 'NM_CONTROLLED': 'no',
                 'BOOTPROTO': 'none',
                 'ONBOOT': 'yes',
                 'MTU': '9000',
                 'NOZEROCONF': 'yes'
                 }
                )


def make_vlan(parent, vlan_id, mac):
    """
    Create a VLAN file contents.
    See make_vlan_with_ip(parent, vlan_id, mac, None, None)
    """
    return make_vlan_with_ip(parent, vlan_id, mac, None, None)


def make_vlan_with_ip(parent, vlan, mac, ip, prefix):
    """
    Create a VLAN file contents.

    Parameters
    ----------
    parent : str
        The parent interface.
    vlan_id : str
        The VLAN id.
    mac : str
        The interface MAC address
    ip : str
        The Ip for the new interface
    prefix :
        the prefix from wich to compute the netmask

    Returns
    -------
        The VLAN interface file contents.
    """
    name = make_vlan_name(parent, vlan)
    if ip and prefix:
        return ('vm-{}'.format(name),
                {'DEVICE': name,
                 'MACADDR': mac,
                 'PHYSDEV': parent,
                 'NM_CONTROLLED': 'no',
                 'BOOTPROTO': 'none',
                 'ONBOOT': 'yes',
                 'MTU': '9000',
                 'NOZEROCONF': 'yes',
                 'VLAN': 'yes',
                 'IPADDR': ip,
                 'NETMASK': network_prefix_to_mask(prefix)
                 }
                )
    return ('vm-{}'.format(name),
                {'DEVICE': name,
                 'MACADDR': mac,
                 'PHYSDEV': parent,
                 'NM_CONTROLLED': 'no',
                 'BOOTPROTO': 'none',
                 'ONBOOT': 'yes',
                 'MTU': '9000',
                 'NOZEROCONF': 'yes',
                 'VLAN': 'yes'
                 }
                )
