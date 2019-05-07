#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module to handle device data.
"""

import os
import sys
# for the sake of testing
sys.path.append('/omv/data/git_pycharm/oci-utils/lib')
from oci_utils.exceptions import OCISDKError

import logging
import time
import re
from glob import glob as glob
from oci_utils.migrate import migrate_utils as migrate_utils
from oci_utils.migrate.migrate_utils import OciMigrateException
from oci_utils.migrate.migrate_utils import NoSuchCommand

filesystems = ['ext2', 'ext3', 'ext4', 'xfs', 'btrfs', 'ocfs2']
lvms = ['LVM2_member']
parttypes_to_skip = ['swap']

partition_types = {'00': ' Empty', '01': ' FAT12', '02': ' XENIX root', '03': ' XENIX usr', '04': ' FAT16 <32M', '05': ' Extended',
                   '06': ' FAT16', '07': ' HPFS/NTFS', '08': ' AIX', '09': ' AIX bootable', '0a': ' OS/2 Boot Manag', '0b': ' W95 FAT32',
                   '0c': ' W95 FAT32 (LBA)', '0e': ' W95 FAT16 (LBA)', '0f': ' W95 Extd (LBA)', '10': ' OPUS', '11': ' Hidden FAT12',
                   '12': ' Compaq diagnost', '14': ' Hidden FAT16 <3', '16': ' Hidden FAT16', '17': ' Hidden HPFS/NTF', '18': ' AST SmartSleep',
                   '1b': ' Hidden W95 FAT3', '1c': ' Hidden W95 FAT3', '1e': ' Hidden W95 FAT1', '24': ' NEC DOS', '39': ' Plan 9',
                   '3c': ' PartitionMagic', '40': ' Venix 80286', '41': ' PPC PReP Boot', '42': ' SFS', '4d': ' QNX4.x', '4e': ' QNX4.x 2nd part',
                   '4f': ' QNX4.x 3rd part', '50': ' OnTrack DM', '51': ' OnTrack DM6 Aux', '52': ' CP/M', '53': ' OnTrack DM6 Aux', '54': ' OnTrackDM6',
                   '55': ' EZ-Drive', '56': ' Golden Bow', '5c': ' Priam Edisk', '61': ' SpeedStor', '63': ' GNU HURD or Sys', '64': ' Novell Netware',
                   '65': ' Novell Netware', '70': ' DiskSecure Mult', '75': ' PC/IX', '80': ' Old Minix', '81': ' Minix / old Lin',
                   '82': ' Linux swap / So', '83': ' Linux', '84': ' OS/2 hidden C:', '85': ' Linux extended', '86': ' NTFS volume set',
                   '87': ' NTFS volume set', '88': ' Linux plaintext', '8e': ' Linux LVM', '93': ' Amoeba', '94': ' Amoeba BBT',
                   '9f': ' BSD/OS', 'a0': ' IBM Thinkpad hi', 'a5': ' FreeBSD', 'a6': ' OpenBSD', 'a7': ' NeXTSTEP', 'a8': ' Darwin UFS',
                   'a9': ' NetBSD', 'ab': ' Darwin boot', 'af': ' HFS / HFS+', 'b7': ' BSDI fs', 'b8': ' BSDI swap', 'bb': ' Boot Wizard hid',
                   'be': ' Solaris boot', 'bf': ' Solaris', 'c1': ' DRDOS/sec (FAT-', 'c4': ' DRDOS/sec (FAT-', 'c6': ' DRDOS/sec (FAT-', 'c7': ' Syrinx',
                   'da': ' Non-FS data', 'db': ' CP/M / CTOS / .', 'de': ' Dell Utility', 'df': ' BootIt', 'e1': ' DOS access', 'e3': ' DOS R/O',
                   'e4': ' SpeedStor', 'eb': ' BeOS fs', 'ee': ' GPT', 'ef': ' EFI (FAT-12/16/', 'f0': ' Linux/PA-RISC b', 'f1': ' SpeedStor',
                   'f4': ' SpeedStor', 'f2': ' DOS secondary', 'fb': ' VMware VMFS', 'fc': ' VMware VMKCORE', 'fd': ' Linux raid auto',
                   'fe': ' LANstep', 'ff': ' BBT'}

valid_boot_types = ['BIOS']
valid_os = ['ORACLE LINUX SERVER', 'RHEL', 'CENTOS', 'UBUNTU']

_logger = logging.getLogger('oci-image-migrate.')


def test():
    """
    Placeholder

    Returns
    -------
        No return value
    """
    migrate_utils.progmsg(__name__)


class DeviceData(object):
    """
    Class to handle the data of device and partitions in an virtual disk
    image file. Contains methods shared by various image file types.

    Attributes
    ----------
        filename: str
            The full path of the virtual image file.
        logger: logger
            The logger.

    """
    def __init__(self, filename, logger=None):
        """ Initialisation of the generic header.
        """
        self._logger = logger or logging.getLogger(__name__)
        self.fn = filename
        self.devicename = None
        self.img_info = dict()
        self.mountpoints = list()
        self._logger.debug('Image file name: %s' % self.fn)


    def mount_img(self):
        """
        Loopback mount the image file.

        Returns
        -------
            str: mount point on success, None on failure, reraises an
            eventual exception.
        """
        self._logger.debug('Entering mount')
        try:
            nbdpath = migrate_utils.mount_imgfn(self.fn)
            if nbdpath is not None:
                self._logger.debug('%s successfully mounted' % nbdpath)
                return nbdpath
            else:
                self._logger.critical('Failed to mount %s' % nbdpath)
                return None
        except Exception as e:
            self._logger.critical(str(e))
            raise OciMigrateException(str(e))

    def umount_img(self, nbd):
        """
        Unmount loopback mounted image file.

        Returns
        -------
            bool: True on success, False Otherwise.
        """
        try:
            if migrate_utils.unmount_imgfn(nbd):
                self._logger.debug('%s successfully unmounted' % nbd)
                return True
            else:
                self._logger.error('Failed to unmount %s' % nbd)
                return False
        except:
            raise

    def get_mbr(self, device):
        """
        Collect the Master Boot Record from the device.

        Parameters
        ----------
        device: str
            The device name.

        Returns
        -------
            bytearray: the MBR on success, None on failure.
        """
        cmd = ['dd', 'if=%s' % device, 'bs=512', 'count=1']
        try:
            mbr = migrate_utils.run_popen_cmd(cmd)
            self._logger.debug('%s mbr: %s' % (device, mbr.encode('hex_codec')))
            return mbr
        except Exception as e:
            self._logger.error('Failed to read MBR on %s: %s' % (device, str(e)))
            return None


    def get_partition_table(self, mbr):
        """
        Collect and analyse partition table in MBR.

        Parameters
        ----------
        mbr: the 512 byte MBR.

        Returns
        -------
            bool: True if block has MBR signature, False otherwise.
            list: list with partiton table on success, None if the block has not the MBR signature.
        """
        bootflag = '80'
        mbrok = False
        hexmbr = mbr.encode('hex_codec')
        mbrsig = hexmbr[-4:]
        if mbrsig.upper() == '55AA':
            mbrok = True
            self._logger.debug('Is a valid MBR')
        else:
            self.logger.critical('Is not a valid MBR')
            return None

        ind = 892
        partitiontable = list()
        for i in range(0, 4):
            part = dict()
            partentry = hexmbr[ind:ind+32]
            part['entry'] = partentry
            ind += 32
            #
            # active partition
            self._logger.debug('boot? : %s' % partentry[0:2])
            if partentry[0:2] == bootflag:
                part['boot'] = True
            else:
                part['boot'] = False
            #
            # type
            typeflag = partentry[8:10].lower()
            self._logger.debug('type? : %s' % typeflag)
            if typeflag in partition_types:
                part['type'] = partition_types[typeflag]
            else:
                part['type'] = 'unknown'

            partitiontable.append(part)

        self._logger.debug('Partition table: %s' % partitiontable)
        return mbrok, partitiontable

    def get_partition_info(self, partitionname):
        """
        Collect information about partition.

        Parameters
        ----------
        partition: str
            The partition name.

        Returns
        -------
            dict: The information about the partition
        """
        self._logger.debug('Collecting informaton on %s' % partitionname)
        blkid_args = ['-po', 'udev']
        blkid_args.append(partitionname)
        self._logger.debug('blkid %s' % blkid_args)
        migrate_utils.progmsg('Investigation partition %s' % partitionname)
        part_info = dict()
        try:
            blkidres = migrate_utils.exec_blkid(blkid_args)
            if blkidres is None:
                self._logger.error('Failed to run blkid %s' % blkidres)
            else:
                self._logger.debug('%s output: blkid\n %s' % (blkid_args, blkidres.split()))
                # pass
        except Exception as e:
            self._logger.critical('blkid exception: %s' % str(e))
            raise OciMigrateException(str(e))
        #
        # make dictionary
        for kv in blkidres.splitlines():
            kvs = kv.split('=')
            part_info[kvs[0]] = kvs[1]
        #
        # add supported entry
        if 'ID_FS_TYPE' in part_info:
            parttype = part_info['ID_FS_TYPE']
        else:
            raise OciMigrateException('FS type missing from partition information %s' % partitionname)

        migrate_utils.progmsg('partition type %s' % parttype)
        if parttype in filesystems:
            self._logger.debug('Partition %s contains filesystem %s' % (partitionname, parttype))
            part_info['supported'] = True
            part_info['usage'] = 'standard'
        elif parttype in lvms:
            self._logger.debug('Partition %s contains a logical volume %s' % (partitionname, parttype))
            part_info['supported'] = True
            part_info['usage'] = 'standard'
        elif parttype in parttypes_to_skip:
            self._logger.debug('Partition %s harmless: %s' % (partitionname, parttype))
            part_info['supported'] = False
            part_info['usage'] = 'na'
            migrate_utils.progmsg('Partition type %s for %s is not supported but harmless, skipping.\n' % (partitionname, parttype))
        else:
            self._logger.debug('Partition %s unusable: %s' % (partitionname, parttype))
            part_info['supported'] = False
            part_info['usage'] = 'na'
            migrate_utils.progmsg('Partition type %s for %s is not supported, quitting.\n' % (partitionname, parttype))
            raise OciMigrateException('Partition type %s for %s is not recognised and may break the operation.' % (parttype, partitionname))
        #
        # get label, if any
        partition_label = migrate_utils.exec_lsblk(['-n', '-o', 'LABEL', partitionname])
        if len(partition_label.rstrip()) > 0:
            migrate_utils.progmsg('Partition label: %s' % partition_label)
            part_info['label'] = partition_label.rstrip()

        return part_info


    def get_image_data(self):
        """
        Get file system on the partition specified by device.

        Returns
        -------
            dict:
               device: file system data if found,
               None otherwise
        """
        success = True
        self._logger.debug('collecting data on %s' % self.devicename)
        try:
            #
            # Master Boot Record
            thismbr = self.get_mbr(self.devicename)
            self.img_info['mbr'] = {'bin': thismbr, 'hex': migrate_utils.show_hex_dump(thismbr)}
            migrate_utils.progmsg('got mbr')
            #
            # Partition Table:
            mbrok, parttable = self.get_partition_table(self.img_info['mbr']['bin'])
            self.img_info['mbr']['valid'] = mbrok
            self.img_info['mbr']['partition_table'] = parttable
            migrate_utils.progmsg('got partition table')
            #
            # Device data
            parted_data = migrate_utils.exec_parted(self.devicename)
            self.img_info['parted'] = parted_data
            migrate_utils.progmsg('got parted data')
            self._logger.debug('partition data: %s' % self.img_info['parted'])
            #
            # Partition info
            sfdisk_info = migrate_utils.exec_sfdisk(self.devicename)
            migrate_utils.progmsg('got sfdisk info')
            self.img_info['partitions'] = sfdisk_info
            self._logger.debug('Partition info: %s' % sfdisk_info)
            #
            # Partition data
            parttemplate = self.devicename + 'p*'
            self._logger.debug('partition %s : %s' % (parttemplate, glob(parttemplate)))
            migrate_utils.progmsg('partition data for device %s' % self.devicename)
            for partname in glob(parttemplate):
                self._logger.debug('Get info on %s' % partname)
                self.img_info['partitions'][partname].update(self.get_partition_info(partname))
        except Exception as e:
            self._logger.critical('Initial partition data collection failed: %s' % str(e))
            raise OciMigrateException('Initial partition data collection failed: %s' % str(e))
        #
        # initialise logical volume structure
        self.img_info['volume_groups'] = dict()
        #
        # initialise list of mountpoints
        #mountpointlist = []
        migrate_utils.progmsg('mount usable partition')
        #
        # loop through identified partitions, identify the type, mount it if
        # it is a standard partition hosting a supported filesystem; if a
        # partition contains a LVM2 physical volume, add the partition to the
        # lvm list for later use.
        for devname, devdetail in self.img_info['partitions'].iteritems():
            self._logger.debug('Device: %s' % devname)
            self._logger.debug('Details:\n %s' % devdetail)
    
            migrate_utils.progmsg('Partition %s' % devname)
            try:
                if 'ID_FS_TYPE' in devdetail:
                    if devdetail['ID_FS_TYPE'] in filesystems:
                        self._logger.debug('file system %s detected' % devdetail['ID_FS_TYPE'])
                        thismountpoint = migrate_utils.mount_part(devname)
                        if thismountpoint is not None:
                            migrate_utils.progmsg('Partition %s with file system %s mounted on %s.' % (devname, devdetail['ID_FS_TYPE'], thismountpoint))
                            self._logger.debug('%s mounted' % devname)
                            devdetail['mountpoint'] = thismountpoint
                            self.mountpoints.append(thismountpoint)
                        else:
                            self._logger.critical('Failed to mount %s' % devname)
                            raise OciMigrateException('Failed to mount %s' % devname)
                        #pause_gt('wait a moment: %s' % self.img_info['partitions'][devname])
                    elif devdetail['ID_FS_TYPE'] in lvms:
                        self._logger.debug('Logical volume %s detected' % devdetail['ID_FS_TYPE'])
                        migrate_utils.progmsg('Logical volume %s' % devdetail['ID_FS_TYPE'])
                        volume_groups = migrate_utils.mount_lvm2(devname)
                        self.img_info['volume_groups'].update(volume_groups)
                    else:
                        migrate_utils.progmsg('skipping %s' % devdetail['ID_FS_TYPE'])
                else:
                    self._logger.debug('%s does not exist or has unrecognised type' % devname)
            except Exception as e:
                success = False
                self._logger.critical('Failed to mount partition %s: %s' % (devname, str(e)))
        #
        # loop through the volume group list, identify the logical volumes
        # and mount them if they host a supported file system.
        for vg, lv in self.img_info['volume_groups'].iteritems():
            self._logger.debug('volume group %s' % vg)
            for part in lv:
                partname = '/dev/mapper/%s' % part[1]
                self._logger.debug('Partition %s' % partname)
                migrate_utils.progmsg('Partition: %s' % partname)
                devdetail = self.get_partition_info(partname)
                try:
                    if 'ID_FS_TYPE' in devdetail:
                        if devdetail['ID_FS_TYPE'] in filesystems:
                            self._logger.debug('file system %s detected' % devdetail['ID_FS_TYPE'])
                            thismountpoint = migrate_utils.mount_part(partname)
                            if thismountpoint is not None:
                                migrate_utils.progmsg('Partition %s with file system %s mounted on %s.' % (partname, devdetail['ID_FS_TYPE'], thismountpoint))
                                self._logger.debug('%s mounted' % partname)
                                devdetail['mountpoint'] = thismountpoint
                                self.mountpoints.append(thismountpoint)
                            else:
                                self._logger.critical('Failed to mount %s' % partname)
                                success = False
                                raise OciMigrateException('Failed to mount %s' % partname)
                        else:
                            self._logger.debug('%s does not exist or has unrecognised type' % partname)
                    self.img_info['partitions'][partname] = devdetail
                except Exception as e:
                    self._logger.critical('Failed to mount logical volumes %s: %s' % (partname, str(e)))
        #print 'mountpoints ... %s' % self.mountpoints
        try:
            #
            # operation system
            osdata = self.get_os_data()
            if osdata is not None:
                self.img_info['osinformation'] = osdata
            else:
                self._logger.critical('Unable to collect OS information')
                self.img_info['osinformation'] = dict()
            #
            #  boot
            part, mount = self.get_boot_partition()
            migrate_utils.progmsg('boot %s %s' % (part, mount))
            if part is not None:
                #self.img_info['partitions'][part]['usage'] = 'boot'
                self.img_info['bootmnt'] = (part, mount)
            else:
                self._logger.debug('Failed to locate boot partition')
                raise OciMigrateException('Failed to locate boot partition')
            #
            # root
            part, mount = self.get_root_partition()
            migrate_utils.progmsg('root %s %s' % (part, mount))
            if part is not None:
                #self.img_info['partitions'][part]['usage'] = 'root'
                self.img_info['rootmnt'] = (part, mount)
            else:
                self._logger.debug('Failed to locate root partition')
                raise OciMigrateException('Failed to locate root partition')
            #
            # grub
            self.img_info['grubdata'] = self.get_grub_data()
            #
            # fstab
            self.img_info['fstab'] = self.get_fstab()
            #
            # network
            self.img_info['network'] = self.get_network_data()
        except Exception as e:
            migrate_utils.progmsg('Something wrong in data collection: %s' % str(e))
            self._logger.error('Something wrong during data collection: %s' % str(e))

        migrate_utils.pause_gt('verify time')
        #
        # Release
        for devname, devdetail in self.img_info['partitions'].iteritems():
            migrate_utils.progmsg('%s' % devname)
            if 'mountpoint' in devdetail:
                try:
                    if migrate_utils.unmount_part(devname):
                        self._logger.debug('%s unmounted' % devname)
                    else:
                        self._logger.critical('failed to unmount %s' % devname)
                    migrate_utils.progmsg('unmounted %s' % devname)
                except Exception as e:
                    self._logger.error('Failed to unmount %s: %s' % (devname, str(e)))
                    pass
                #pause_gt('wait a moment: %s' % self.img_info['partitions'][devname])
        #
        # release lvm2 if any
        if self.img_info['volume_groups']:
            migrate_utils.unmount_lvm2(self.img_info['volume_groups'])

        if success:
            return self.img_info
        else:
            return False

    def get_boot_partition(self):
        """
        Locate the boot partition and collect relevant data. The bootable
        partiton is not necessarily mounted, e.g. if it is a logical volume.

        Returns
        -------
            tuple: boot partition, boot mountpoint
        """
        thispartitions = self.img_info['partitions']
        bootpart, bootmount = None, None
        try:
            for part, partdata in thispartitions.iteritems():
                self._logger.debug('looking in partition %s' % part)
                if 'bootable' in partdata:
                    if partdata['bootable']:
                        bootpart = part
                        if 'mountpoint' in partdata:
                            bootmount = partdata['mountpoint']
                        else:
                            self._logger.debug('%s is not mounted' % part)
                            bootmount = None
                        migrate_utils.progmsg('Bootable partition %s mounted '
                                              'on %s' % (bootpart, bootmount))
                        break
                    else:
                        self._logger.debug('%s is not bootable' % part)
                else:
                    self._logger.debug('%s is not mounted' % part)
        except Exception as e:
            self._logger.debug('Failed to find the boot partition: %s' % str(e))
            raise OciMigrateException('Failed to find the boot partition: %s' % str(e))
        return bootpart, bootmount

    def get_root_partition(self):
        """
        Locate the root partition and collect relevant data; /etc/fstab is
        supposed to be on the root partition.

        Returns
        -------
            tuple: (root partition, root mountpoint), (None, None) otherwise
        """
        thisfile = 'fstab'
        # thispartitions = self.img_info['partitions']
        rootpart, rootmount = None, None
        try:
            for mnt in self.mountpoints:
                self._logger.debug('Looking in partition %s' % mnt)
                fstab = migrate_utils.exec_find(thisfile, mnt)
                if fstab is not None:
                    rootpart = mnt
                    rootmount = mnt
                    migrate_utils.progmsg('root partition is mounted on %s' % rootmount)
                    break
                else:
                    self._logger.debug('fstab not found in %s' % mnt)
        except Exception as e:
            self._logger.critical('Failed to find the root partition: %s' % str(e))
            raise OciMigrateException('Failed to find the root partition: %s' % str(e))
        return rootpart, rootmount

    def get_grub_data(self):
        """
        Collect data related to boot and grub.

        Returns
        -------
            list: List with relevant data from the grub config file.
        """
        #
        # find grub.cfg, grub.conf, ...
        grubconflist = ['grub.cfg', 'grub.conf']
        grub_cfg_path = None
        for grubname in grubconflist:
            for mnt in self.mountpoints:
                for grubroot in [mnt + '/boot', mnt + '/grub', mnt + '/grub2']:
                    self._logger.debug('looking for %s in %s' % (grubname, grubroot))
                    grubconf = migrate_utils.exec_find(grubname, grubroot)
                    if grubconf is not None:
                        grub_cfg_path = grubconf
                        self._logger.debug('Found grub config file: %s' % grub_cfg_path)
                        break
                    else:
                        self._logger.debug('No grub config file in %s' % mnt + '/boot')

        if grub_cfg_path is None:
            self._logger.debug('No grub config file found in %s' % self.fn)
            raise OciMigrateException('No grub config file found in %s' % self.fn)
        migrate_utils.progmsg('grub config file: %s' % grub_cfg_path)
        #
        # investigate grub cfg path: contents of EFI/efi directory.
        if 'EFI' in grub_cfg_path.split('/'):
            self.img_info['boot_type'] = 'UEFI'
        else:
            self.img_info['boot_type'] = 'BIOS'
        self._logger.debug('Image boot type is %s' % self.img_info['boot_type'])
        migrate_utils.progmsg('image boot type: %s' % self.img_info['boot_type'])

        grubdata = list()
        grub2 = False
        grubentry = dict()
        self._logger.debug('initialised grub structure')
        try:
            #
            # check for grub2 data
            mentry = False
            with open(grub_cfg_path, 'rb') as f:
                for ffsline in f:
                    fsline = ffsline.strip()
                    if len(fsline.split()) > 0:
                        self._logger.debug('%s' % fsline)
                        if fsline.split()[0] == 'menuentry':
                            mentry = True
                            grub2 = True
                            if grubentry:
                                grubdata.append(grubentry)
                            grubentry = {'menuentry': [fsline]}
                            self._logger.debug('grub line: %s' % fsline)
                        elif fsline.split()[0] == 'search':
                            if mentry:
                                grubentry['menuentry'].append(fsline)
                                self._logger.debug('grub line: %s' % grubentry['menuentry'])
                            else:
                                self._logger.debug('Not a menuentry, skipping %s' % fsline)
                        else:
                            self._logger.debug('Skipping %s' % fsline)
            if grubentry:
                grubdata.append(grubentry)
        except Exception as e:
            self._logger.error('Errors during reading %s: %s' % (grub_cfg_path, str(e)))
            OciMigrateException('Errors during reading %s: %s' % (grub_cfg_path, str(e)))
        if grub2:
            self._logger.debug('Found grub2 configuration file.')
            migrate_utils.progmsg('Found grub2 configuration file')
        else:
            try:
                #
                # check for grub data
                with open(grub_cfg_path, 'rb') as f:
                    for ffsline in f:
                        fsline = ffsline.strip()
                        if len(fsline.split()) > 0:
                            self._logger.debug('%s' % fsline)
                            if fsline.split()[0] == 'title':
                                if grubentry:
                                    grubdata.append(grubentry)
                                grubentry = {'title': [fsline]}
                                self._logger.debug('grub line: %s' % fsline)
                            elif fsline.split()[0] == 'kernel':
                                grubentry['title'].append(fsline)
                                self._logger.debug('grub line: %s' % grubentry['title'])
                            else:
                                self._logger.debug('skipping %s' % fsline)
                if grubentry:
                    grubdata.append(grubentry)
            except Exception as e:
                self._logger.error('Errors during reading %s: %s' % (grub_cfg_path, str(e)))
                OciMigrateException('Errors during reading %s: %s' % (grub_cfg_path, str(e)))

        return grubdata

    def get_os_data(self):
        """
        Collect information on the linux operating system and release.

        Returns
        -------
            dict: Dictionary containing the os and version data on success, None otherwise.
        """
        self._logger.debug('Collection os data, looking in %s' % self.mountpoints)
        osdict = dict()
        #
        # hostnamectl is a systemd command, not available in OL/RHEL/CentOS 6
        try:
            for mnt in self.mountpoints:
                osdata = migrate_utils.exec_find('os-release', mnt)
                if osdata is not None:
                    with open(osdata, 'rb') as f:
                        osreleasedata = [line for line in f.read().splitlines() if '=' in line]
                    osdict = dict([re.sub(r'"', '', kv).split('=') for kv in osreleasedata])
                    break
        except Exception as e:
            self._logger.error('Failed to collect os data: %s' % str(e))
            #raise OciMigrateException('Failed to collect os data: %s' % str(e))
        self._logger.debug('os data: %s' % osdict)
        return osdict

    def get_fstab(self):
        """
        Read and analyse fstab file.

        Returns
        -------

        """
        fstabdata = list()
        fstabfile = self.img_info['rootmnt'][1] + '/etc/fstab'
        try:
            with open(fstabfile, 'rb') as f:
                for fsline in f:
                    if '#' not in fsline and len(fsline.split()) > 5:
                        fstabdata.append(fsline.split())
                        migrate_utils.progmsg('%s' % fsline.split())
                    else:
                        self._logger.debug('skipping %s' % fsline)
        except Exception as e:
            self._logger.error('Problem reading %s: %s' % (fstabfile, str(e)))
        return fstabdata

    def get_network_data(self):
        """
        Collect the network configuration files.

        Returns
        -------
            list: List with dictionary representation of the network configuration files.
        """
        network_list = list()
        network_dir = self.img_info['rootmnt'][1] + '/etc/sysconfig/network-scripts'
        self._logger.debug('network directory: %s' % network_dir)
        try:
            for cfgfile in glob(network_dir + '/ifcfg-*'):
                ifcfg = dict()
                with open(cfgfile, 'rb') as f:
                    #nl = filter(None, [x[:x.find('#')] for x in f])
                    nl = filter(None, [x[:x.find('#')] for x in f])
                self._logger.debug('%s' % nl)
                ifcfg = dict(l.translate(None, '"').split('=') for l in nl)
                migrate_utils.progmsg('%s' % ifcfg)
                network_list.append({cfgfile.split('/')[-1]: ifcfg})
        except Exception as e:
            self._logger.error('Problem reading network configuration files: %s' % str(e))
        return network_list

    def generic_prereq_check(self):
        """
        Verify the generic prequisites.
        Returns
        -------
            bool: True or False.
            str : The eventual message.
        """
        thispass = True
        failmsg = ''
        #
        # BIOS boot
        if self.img_info['boot_type'] in valid_boot_types:
            self._logger.debug('Boot type is %s, ok' % self.img_info['boot_type'])
            migrate_utils.progmsg('Boot type is %s, ok' % self.img_info['boot_type'])
        else:
            thispass = False
            self._logger.debug('Boot type %s is not a valid boot type. ' % self.img_info['boot_type'])
            failmsg += '\nBoot type %s is not a valid boot type. ' % \
                       self.img_info['boot_type']
        #
        # MBR
        if self.img_info['mbr']['valid']:
            self._logger.debug('The image %s contains a valid MBR.' % self.img_info['img_name'])
            migrate_utils.progmsg('The image %s contains a valid MBR.' % self.img_info['img_name'])
        else:
            thispass = False
            self._logger.debug('The image %s does not contain a valid MBR.' % self.img_info['img_name'])
            failmsg += '\nThe image %s does not contain a valid MBR.' % \
                       self.img_info['img_name']
        #
        # 1 disk: considering only 1 image file, representing 1 virtual disk,
        # implicitly.
        #
        # Bootable
        partitiontable = self.img_info['mbr']['partition_table']
        bootflag = False
        for i in range(0, len(partitiontable)):
            if partitiontable[i]['boot']:
                bootflag = True
                self._logger.debug('The image %s is bootable' % self.img_info['img_name'])
                migrate_utils.progmsg('The image %s is bootable' % self.img_info['img_name'])
        if not bootflag:
            thispass = False
            failmsg += '\nThe image %s is not bootable.' % self.img_info['img_name']
        #
        # Everything needed to boot in this image? Compairing fstab with
        # partition data.
        fstabdata = self.img_info['fstab']
        partitiondata = self.img_info['partitions']

        fstab_pass = True
        for line in fstabdata:
            part_pass = False
            if 'UUID' in line[0]:
                uuid_x = re.split('\\bUUID=\\b', line[0])[1]
                for _, part in partitiondata.iteritems():
                    if 'ID_FS_UUID' in part:
                        if part['ID_FS_UUID'] == uuid_x:
                            part_pass = True
                            self._logger.debug('Found %s in partition table.' % uuid_x)
                            migrate_utils.progmsg('Found %s in partition table.' % uuid_x)
                            break
            elif 'LABEL' in line[0]:
                label_x = re.split('\\bLABEL=\\b', line[0])[1]
                for _, part in partitiondata.iteritems():
                    if 'label' in part:
                        if part['label'] == label_x:
                            part_pass = True
                            self._logger.debug('Found %s in partition table.' % label_x)
                            migrate_utils.progmsg('Found %s in partition table.' % label_x)
                            break
            elif 'mapper' in line[0]:
                lv_x = re.split('\\bmapper/\\b', line[0])[1]
                for part, _ in partitiondata.iteritems():
                    if  lv_x in part:
                        part_pass = True
                        self._logger.debug('Found %s in partition table.' % lv_x)
                        migrate_utils.progmsg('Found %s in partition table.' % lv_x)
                        break
            elif '/dev/' in line[0]:
                self._logger.critical('Device name %s in fstab are not supported.' % line[0])
            else:
                part_pass = True
                self._logger.debug('Unrecognised: %s, ignoring.' % line[0])
                migrate_utils.progmsg('Unrecognised: %s, ignoring.' % line[0])

            if not part_pass:
                fstab_pass = False
                break

        if not fstab_pass:
            thispass = False
            failmsg += '\nfstab file refers to unsupported or unreachable partitions.'
        #
        # boot using LVM or UUID
        grubdata = self.img_info['grubdata']
        #
        # grub: 'root=UUID'
        # grub2: '--fs-uuid'
        grub_fail = 0
        for entry in grubdata:
            for key in entry:
                for l in entry[key]:
                    l_split = l.split()
                    if l_split[0] == 'search' and '--fs-uuid' not in l_split:
                        self._logger.error('grub line --%s-- does not specify boot partition via UUID.' % l)
                        grub_fail += 1
                    else:
                        migrate_utils.progmsg('grub line --%s-- specifies boot partition via UUID.' % l)
                    if l_split[0] == 'kernel' and 'root=UUID=' not in l_split:
                        self._logger.error('grub line --%s-- does not specify boot partition via UUID.' % l)
                        grub_fail += 1
                    else:
                        migrate_utils.progmsg('grub line --%s-- specifies boot partition via UUID.' % l)
        if grub_fail > 0:
            thispass = False
            failmsg += '\ngrub config file does not guarantee booting using UUID'

        #
        # OS
        osdata = self.img_info['osinformation']
        os_pass = False
        os_name = 'notsupportedos'
        for k, v in osdata.iteritems():
            if k.upper() == 'NAME':
                if v.upper() in valid_os:
                    self._logger.debug('OS is a %s: valid' % v)
                    migrate_utils.progmsg('OS is a %s: valid' % v)
                    osname = v
                    os_pass = True
                else:
                    self._logger.error('OS %s is not supported.' % v)
        if not os_pass:
            thispass = False
            failmsg += '\nOS %s is not supported' % os_name


        #
        # network interface configuration, need to remount /etc at least



        return thispass, failmsg


