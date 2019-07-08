#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Static data with respect to the oci-image-migrate.
"""
#
# dummy format key
dummy_format_key = '01234567'
#
# python version
pythonver = 2
#
# log file path, without .log extension, timestamp and extension added runtime.
logfilepath = '/tmp/oci-image-migrate'
#
# result file path without extension, image references are added runtime,
resultfilepath = '/tmp/ocimigrate'
#
# oci configuration file
ociconfigfile = '/root/.oci/config'
#
# recognised file system types.
filesystem_types = ['ext2', 'ext3', 'ext4', 'xfs', 'btrfs', 'ocfs2']
logical_vol_types = ['LVM2_member']
partition_to_skip = ['swap']
#
# recognised partition types.
partition_types = {'00': ' Empty',
                   '01': ' FAT12',
                   '02': ' XENIX root',
                   '03': ' XENIX usr',
                   '04': ' FAT16 <32M',
                   '05': ' Extended',
                   '06': ' FAT16',
                   '07': ' HPFS/NTFS',
                   '08': ' AIX',
                   '09': ' AIX bootable',
                   '0a': ' OS/2 Boot Manag',
                   '0b': ' W95 FAT32',
                   '0c': ' W95 FAT32 (LBA)',
                   '0e': ' W95 FAT16 (LBA)',
                   '0f': ' W95 Extd (LBA)',
                   '10': ' OPUS',
                   '11': ' Hidden FAT12',
                   '12': ' Compaq diagnost',
                   '14': ' Hidden FAT16 <32>',
                   '16': ' Hidden FAT16',
                   '17': ' Hidden HPFS/NTFS',
                   '18': ' AST SmartSleep',
                   '1b': ' Hidden W95 FAT32',
                   '1c': ' Hidden W95 FAT32',
                   '1e': ' Hidden W95 FAT16',
                   '24': ' NEC DOS',
                   '39': ' Plan 9',
                   '3c': ' PartitionMagic',
                   '40': ' Venix 80286',
                   '41': ' PPC PReP Boot',
                   '42': ' SFS',
                   '4d': ' QNX4.x',
                   '4e': ' QNX4.x 2nd part',
                   '4f': ' QNX4.x 3rd part',
                   '50': ' OnTrack DM',
                   '51': ' OnTrack DM6 Aux',
                   '52': ' CP/M',
                   '53': ' OnTrack DM6 Aux',
                   '54': ' OnTrackDM6',
                   '55': ' EZ-Drive',
                   '56': ' Golden Bow',
                   '5c': ' Priam Edisk',
                   '61': ' SpeedStor',
                   '63': ' GNU HURD or Sys',
                   '64': ' Novell Netware',
                   '65': ' Novell Netware',
                   '70': ' DiskSecure Mult',
                   '75': ' PC/IX',
                   '80': ' Old Minix',
                   '81': ' Minix / old Lin',
                   '82': ' Linux swap / Solaris x86',
                   '83': ' Linux',
                   '84': ' OS/2 hidden C:',
                   '85': ' Linux extended',
                   '86': ' NTFS volume set',
                   '87': ' NTFS volume set',
                   '88': ' Linux plaintext',
                   '8e': ' Linux LVM',
                   '93': ' Amoeba',
                   '94': ' Amoeba BBT',
                   '9f': ' BSD/OS',
                   'a0': ' IBM Thinkpad hi',
                   'a5': ' FreeBSD',
                   'a6': ' OpenBSD',
                   'a7': ' NeXTSTEP',
                   'a8': ' Darwin UFS',
                   'a9': ' NetBSD',
                   'ab': ' Darwin boot',
                   'af': ' HFS / HFS+',
                   'b7': ' BSDI fs',
                   'b8': ' BSDI swap',
                   'bb': ' Boot Wizard hid',
                   'be': ' Solaris boot',
                   'bf': ' Solaris',
                   'c1': ' DRDOS/sec (FAT-12)',
                   'c4': ' DRDOS/sec (FAT-16)',
                   'c6': ' DRDOS/sec (FAT-16B)',
                   'c7': ' Syrinx',
                   'da': ' Non-FS data',
                   'db': ' CP/M / CTOS / .',
                   'de': ' Dell Utility',
                   'df': ' BootIt',
                   'e1': ' DOS access',
                   'e3': ' DOS R/O',
                   'e4': ' SpeedStor',
                   'eb': ' BeOS fs',
                   'ee': ' GPT',
                   'ef': ' EFI (FAT-12/16/',
                   'f0': ' Linux/PA-RISC b',
                   'f1': ' SpeedStor',
                   'f4': ' SpeedStor',
                   'f2': ' DOS secondary',
                   'fb': ' VMware VMFS',
                   'fc': ' VMware VMKCORE',
                   'fd': ' Linux raid auto',
                   'fe': ' LANstep',
                   'ff': ' BBT'}
#
# list of valid boot configurations.
valid_boot_types = ['BIOS']
#
# list of directories required for a normal boot of a linux type os; if
# those directories reside in separate partitions, those partition have to
# be in the same image file.
essential_dir_list = ['/boot',
                      '/bin',
                      '/etc',
                      '/home',
                      '/lib',
                      '/opt',
                      '/sbin',
                      '/srv',
                      '/usr',
                      '/var']

#
# default network configuration file for OL type linux
default_if_network_config = ['TYPE="Ethernet"',
                             'PROXY_METHOD="none"',
                             'BROWSER_ONLY="no"',
                             'BOOTPROTO="dhcp"',
                             'DEFROUTE="yes"',
                             'IPV4_FAILURE_FATAL="no"',
                             'IPV6INIT="yes"',
                             'IPV6_AUTOCONF="yes"',
                             'IPV6_DEFROUTE="yes"',
                             'IPV6_FAILURE_FATAL="no"',
                             'IPV6_ADDR_GEN_MODE="stable-privacy"',
                             'NAME="eth0"',
                             'DEVICE="eth0"',
                             'ONBOOT="yes"']
#
# (Ubuntu) network configuration file paths
default_nwmconfig = '/etc/NetworkManager/NetworkManager.conf'
default_nwconnections = '/etc/NetworkManager/system-connections'
default_netplan = '/etc/netplan'
default_interfaces = '/etc/network/interfaces'
#
# Ubuntu default network manager config file.
default_nwm_file = [
    '[main]',
    'plugins=ifupdown,keyfile',
    '',
    '[ifupdown]',
    'managed=false',
    '',
    '[device]',
    'wifi.scan-rand-mac-address=no', ]
# Ubuntu default netplan configuration file
default_netplan_file = '/etc/netplan/10-default-network.yaml'
default_netplan_config = {'network': {'ethernets': {'_XXXX_': {'addresses': [], 'dhcp4': True}}}}
#
# Ubuntu default interfaces file
default_interfaces_file = [
    '# This file describes the network interfaces available on your system',
    '# and how to activate them. For more information, see interfaces(5).',
    '',
    '# source /etc/network/interfaces.d/*',
    '# The loopback network interface',
    '',
    'auto lo',
    'iface lo inet loopback',
    '',
    '# The primary network interface',
    'auto _XXXX_',
    'iface _XXXX_ inet dhcp', ]
#
# list of supported operating systems.
valid_os = ['ORACLE LINUX SERVER',
            'RHEL',
            'CENTOS',
            'UBUNTU']
#
#