#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2018 Oracle and/or its affiliates. All rights reserved.
#
# The Universal Permissive License (UPL), Version 1.0
#
# Subject to the condition set forth below, permission is hereby granted to
# any person obtaining a copy of this software, associated documentation
# and/or data (collectively the "Software"), free of charge and under any
# and all copyright rights in the Software, and any and all patent rights
# owned or freely licensable by each licensor hereunder covering either
# (i) the unmodified Software as contributed to or provided by such licensor, or
# (ii) the Larger Works (as defined below), to deal in both
# (a) the Software, and
# (b) any piece of software and/or hardware listed in the lrgrwrks.txt
# file if one is included with the Software (each a "Larger Work" to which
# the Software is contributed by such licensors),
#
# without restriction, including without limitation the rights to copy,
# create derivative works of, display, perform, and distribute the Software
# and make, use, sell, offer for sale, import, export, have made, and have
# sold the Software and the Larger Work(s), and to sublicense the foregoing
# rights on either these or other terms.
#
# This license is subject to the following condition:
#
# The above copyright notice and either this complete permission notice or
# at a minimum a reference to the UPL must be included in all copies or
# substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

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
