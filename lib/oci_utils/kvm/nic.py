#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

import os
import subprocess

__prefix = '/sys/class/net'

def get_interfaces():
    ret = {}

    pciIdToIface = {}

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

        ifaceInfo = {'physical': physical,
                     'mac': mac
                    }

        if physical:
            # Check to see if this is a physical or virtual
            # function
            dev = '{}/device'.format(iface)

            pciId = os.readlink(dev)
            pciId = pciId[pciId.rfind('/')+1:]

            pciIdToIface[pciId] = n
            ifaceInfo['pci'] = pciId

            try:
                physId = os.readlink('{}/physfn'.format(dev))[3:]
                ifaceInfo['physfn'] = physId
            except OSError:
                # If there is no physical function backing this
                # interface, then it must itself be one
                virtIfaces = {}
                dirs = os.listdir(dev)
                for d in dirs:
                    if not d.startswith('virtfn'):
                        continue

                    virtPciId = os.readlink('{}/{}'.format(dev, d))[3:]
                    #virtIfaces.append((virtPciId, int(d[6:])))
                    virtIfaces[int(d[6:])] = {'pciId': virtPciId}

                # TODO: find a better way to get mac addresses for
                # TODO: virtual functions
                for line in subprocess.check_output(['/usr/sbin/ip', 'link', 'show', n]).splitlines():
                    line = line.strip()
                    if not line.startswith('vf '):
                        continue

                    ents = line.split(' ')
                    vfNum = int(ents[1])
                    vfMac = ents[3][:-1]

                    virtIfaces[vfNum]['mac'] = vfMac

                ifaceInfo['virtfns'] = virtIfaces

        ret[n] = ifaceInfo

    # Populate any potentially invalid mac addresses with
    # the correct data
    for n, info in ret.iteritems():
        if not info['physical']:
            continue

        virtFns = info.get('virtfns')
        if virtFns is None:
            continue

        for k, v in virtFns.iteritems():
            try:
                v['mac'] = ret[pciIdToIface[v['pciId']]]['mac']
            except:
                pass

    # Convert the lists of pci ids to device names
    #for n in ret:
    #    info = ret[n]
    #    if not info['physical']:
    #        continue

    #    virt = info.get('virtfns')
    #    if virt is not None:
    #        #info['virtfns'] = set([pciIdToIface[x] for x in virt])
    #        info['virtfns'] = {pciIdToIface[x[0]]: x[1] for x in virt}
    #    else:
    #        info['physfn'] = pciIdToIface[info['physfn']]

    return ret
