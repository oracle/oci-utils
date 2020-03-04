# oci-utils
#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Network Interface Controller.
"""
import os
import subprocess

__prefix = '/sys/class/net'


def get_interfaces():
    """
    Collect the network interfaces and their properties.

    Returns
    -------
        dict
            List of the network interfaces and their properties.
    """
    ret = {}

    pci_id_to_iface = {}

    for n in os.listdir(__prefix):
        physical = True
        iface = "{}/{}".format(__prefix, n)
        try:
            link = os.readlink(iface)
            if link.startswith('../../devices/virtual'):
                physical = False
        except OSError:
            continue

        mac = open('{}/address'.format(iface)).read().strip().lower()

        iface_info = {
            'physical': physical,
            'mac': mac}

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

                    virtpci_id = os.readlink('{}/{}'.format(dev, d))[3:]
                    # virt_ifaces.append((virtpci_id, int(d[6:])))
                    virt_ifaces[int(d[6:])] = {'pci_id': virtpci_id}

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

                iface_info['virt_fns'] = virt_ifaces

        ret[n] = iface_info

    # Populate any potentially invalid mac addresses with
    # the correct data
    for n, info in ret.items():
        if not info['physical']:
            continue

        virt_fns = info.get('virt_fns')
        if virt_fns is None:
            continue

        for k, v in virt_fns.items():
            try:
                v['mac'] = ret[pci_id_to_iface[v['pci_id']]]['mac']
            except Exception:
                pass

    # Convert the lists of pci ids to device names
    # for n in ret:
    #    info = ret[n]
    #    if not info['physical']:
    #        continue

    #    virt = info.get('virt_fns')
    #    if virt is not None:
    #        #info['virt_fns'] = set([pci_id_to_iface[x] for x in virt])
    #        info['virt_fns'] = {pci_id_to_iface[x[0]]: x[1] for x in virt}
    #    else:
    #        info['physfn'] = pci_id_to_iface[info['physfn']]

    return ret
