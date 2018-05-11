#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

import os

from . import nic
from . import utils

__sysconfig = '/etc/sysconfig'
__netscripts = __sysconfig + '/network-scripts'

__iface_prefix = 'ifcfg-'

def parse_env_file(f):
    ret = {}
    for l in f:
        l = l.strip()
        if l.startswith('#'):
            # Skip comments
            continue
        c = l.split('=')
        if len(c) != 2:
            # Skip malformed lines
            continue

        ret[c[0]] = c[1]

    return ret

def read_network_file(path):
    try:
        #with f as open(path, 'r'):
        with open(path, 'r') as f:
            return parse_env_file(f)
    except Exception as e:
        raise e
    return None

def read_directory_files(path, reader, filt=None, fmt=None):
    ret = {}
    if not fmt:
        fmt = lambda x: x
    try:
        for d in os.listdir(path):
            p = '{}/{}'.format(path, d)
            if not filt or filt(d):
                ret[fmt(d)] = reader(p)

    except Exception as e:
        raise e
        return ret
    return ret

def read_network_config():
    return read_directory_files(__netscripts, read_network_file, lambda x: x.startswith(__iface_prefix), lambda x: x[len(__iface_prefix):])

def write_env_file(f, conf):
    for k, v in conf:
        f.write('{}={}'.format(k, v))

def build_env_file(conf):
    return "\n".join(['{}={}'.format(k, v) for k, v in conf.iteritems()])

def write_network_file(path, conf):
    # It's not possible to use native file output because these files must
    # be written with euid=0.  Of course, there is no way to elevate this
    # process.  Instead, shell out so that sudo can be applied.
    utils._call(['sh', '-c', 'echo \'{}\' > {}'.format(build_env_file(conf), path)])

def write_directory_files(path, conf, writer, fmt=None):
    if not fmt:
        fmt = lambda x: x
    try:
        for name, data in conf.iteritems():
            f = '{}/{}'.format(path, fmt(name))
            writer(f, data)
    except Exception as e:
        raise e

def write_network_config(data):
    write_directory_files(__netscripts, data, write_network_file, lambda x: __iface_prefix + x)

def apply_network_config():
    # If dhclient is running, then network.service cannot restart correctly.  There is nothing
    # in the OS that kills off dhclient, so it must be done here.
    utils._call(['/usr/bin/pkill', 'dhclient'])

    # Restart the network service to apply most of the relevant changes.  Note that network.service
    # does not have the ability to remove interfaces, so any virtual interfaces must be manually
    # deleted
    if utils._call(['/usr/sbin/service', 'network', 'restart']):
        return False

    # Poll for interface existence
    return True

def interfaces_up(ifaces):
    for i in ifaces:
        if utils._call(['/usr/sbin/ifup', i]):
            return False

    return True

def delete_file(path):
    utils._call(['rm', '-f', path])

def delete_directory_files(path, files, fmt=None):
    if not fmt:
        fmt = lambda x: x
    for name in files:
        delete_file('{}/{}'.format(path, fmt(name)))

def delete_virtual_interfaces(data):
    ifaces = nic.get_interfaces()

    for name in data:
        info = ifaces.get(name)
        if not info:
            continue
        if info['physical']:
            continue
        utils._call(['/usr/sbin/ip', 'link', 'delete', name])

def delete_network_config(data):
    delete_directory_files(__netscripts, data, lambda x: __iface_prefix + x)
    delete_virtual_interfaces(data)

def make_vf_name(name):
    return name

def make_vlan_name(parent, vlan_id):
    return '{}.{}'.format(parent, vlan_id)

def make_vf(name, mac):
    name = make_vf_name(name)
    return (name,
            {'DEVICE': name,
             'MACADDR': mac,
             'NM_CONTROLLED': 'no',
             'BOOTPROTO': 'none',
             'ONBOOT': 'yes',
             'MTU': '9000'
            }
           )

def make_vlan(parent, vlan_id, mac):
    name = make_vlan_name(parent, vlan_id)
    return (name,
            {'DEVICE': name,
             'MACADDR': mac,
             'PHYSDEV': parent,
             'NM_CONTROLLED': 'no',
             'BOOTPROTO': 'none',
             'ONBOOT': 'yes',
             'MTU': '9000',
             'VLAN': 'yes'
            }
           )
