#!/usr/bin/env python2.7

import subprocess
import os.path
import urllib2
import posixfile
import json
import utils

from .. import metadata

# Verify if the IOMMU is enabled. Linux kernel logs the message "IOMMU: enabled"
# at boot time and the IOMMU subsystem creates 'dmar' device nodes under /sys/class/iommu
# directory. This functions check for both to confirm that the IOMMU is enabled.
def iommu_check():
    iommu_enabled_exp = "IOMMU.*enabled"
    dmar_file_path = "/sys/class/iommu/dmar0"
    output = utils._call_popen_output(['/bin/dmesg', '|', 'egrep', '"{}"'.format(iommu_enabled_exp)])
    if output and os.path.exists(dmar_file_path):
        return True 
    else:
        return False

# Verify if the system is a BM or a VM. This is accomplished with 'systemd-detect-virt' 
# command, which returns "none" when it not a VM.
def server_type_check():
    server_type = "none"
    output = utils._call_popen_output(['systemd-detect-virt'])
    if server_type == output.strip():
        return True
    return False

# Find the primary ethernet device interface name
def get_phys_device():
    try:
	    private_ip =  metadata()['vnics'][0]['privateIp'] 
    except:
	return None
    phys_dev = None
    output =  utils._call_output(['ip', '-o', '-4', 'addr', 'show'])
    lines = output.split('\n')
    for line in lines:
        if private_ip in line.strip():
            phys_dev = line.strip().split()[1]
    return phys_dev

# Verify if the primary ethernet device has SR-IOV enabled.
def sriov_numvfs_check(phys_dev):
    sriov_fpath = '/sys/class/net/{}/device/sriov_numvfs'.format(phys_dev)
    try:
        f = open(sriov_fpath, "r")
        output = f.read()
        f.close()
        if int(output) > 0:
            return True
        return False
    except IOError as e:
        return False


# Verify the bridge on primary ethernet device has VEPA link mode
def br_link_mode_check(phys_dev):
    vepa = "VEPA"
    res = utils._call_popen_output(['bridge', 'link', 'show', 'dev', '"{}"'.format(phys_dev)])
    if res and vepa == res.split()[-1]:
        return True
    return False
    

# Verify if we have valid KVM environment on a BM with the following
#   - Verify IOMMU is enabled
#   - Verify it is a BM
#   - Verify SR-IOV is enabled on primary ethernet device
#   - Verify the bridge on primary ethernet device has VEPA link mode set
def validate_kvm_env():
    phys_dev = get_phys_device()
    if phys_dev is None:
        return False
    if iommu_check() and server_type_check() and \
            sriov_numvfs_check(phys_dev) and    \
            br_link_mode_check(phys_dev):
        return True
    return False

ret = validate_kvm_env()
