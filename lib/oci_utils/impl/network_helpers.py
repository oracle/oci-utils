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

__all__ = ['get_interfaces']

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
    for n, info in ret.iteritems():
        if not info['physical']:
            continue

        virt_fns = info.get('virtfns')
        if virt_fns is None:
            continue

        for k, v in virt_fns.iteritems():
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
