#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module to handle device data.
"""

import sys
# for the sake of testing
sys.path.append('/omv/data/git_pycharm/oci-utils/lib')

import logging
import re
import importlib
from glob import glob as glob
from oci_utils.migrate import migrate_utils as migrate_utils
from oci_utils.migrate.exception import OciMigrateException
from oci_utils.migrate import gen_tools
from oci_utils.migrate import data


_logger = logging.getLogger('oci-image-migrate.')


def test():
    """
    Placeholder

    Returns
    -------
        No return value
    """
    gen_tools.result_msg(__name__)


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
        Loopback mount the image file on /dev/nbd.

        Returns
        -------
            str: mount point on success, None on failure, reraises an
            eventual exception.
        """
        self._logger.debug('Entering mount')
        try:
            nbdpath = migrate_utils.mount_imgfn(self.fn)
            self._logger.debug('%s successfully mounted' % nbdpath)
            return nbdpath
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
        except Exception as e:
            raise OciMigrateException(str(e))

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
            mbr = gen_tools.run_popen_cmd(cmd)
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
            list: list with partiton table.
        """
        bootflag = '80'
        mbrok = False
        partitiontable = list()
        hexmbr = mbr.encode('hex_codec')
        mbrsig = hexmbr[-4:]
        if mbrsig.upper() == '55AA':
            mbrok = True
            self._logger.debug('Is a valid MBR')
        else:
            self._logger.critical('Is not a valid MBR')
            return mbrok, partitiontable

        ind = 892
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
            if typeflag in data.partition_types:
                part['type'] = data.partition_types[typeflag]
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
        partitionname: str
            The partition name.

        Returns
        -------
            dict: The information about the partition
        """
        #
        # blkid data
        self._logger.debug('Collecting informaton on %s' % partitionname)
        blkid_args = ['-po', 'udev']
        blkid_args.append(partitionname)
        self._logger.debug('blkid %s' % blkid_args)
        gen_tools.result_msg('Investigating partition %s' % partitionname)
        part_info = dict()
        blkidres = migrate_utils.exec_blkid(blkid_args)
        if blkidres is None:
            raise OciMigrateException('Failed to run blkid %s' % blkidres)
        else:
            self._logger.debug('%s output: blkid\n %s'
                               % (blkid_args, blkidres.split()))
        #
        # make dictionary
        for kv in blkidres.splitlines():
            kvs = kv.split('=')
            part_info[kvs[0]] = kvs[1]
        #
        # add supported entry
        if 'ID_FS_TYPE' in part_info:
            parttype = part_info['ID_FS_TYPE']
            #
            # verify partition type is supported
            gen_tools.result_msg('Partition type %s' % parttype)
            if parttype in data.filesystem_types:
                self._logger.debug('Partition %s contains filesystem %s'
                                   % (partitionname, parttype))
                part_info['supported'] = True
                part_info['usage'] = 'standard'
            elif parttype in data.logical_vol_types:
                self._logger.debug('Partition %s contains a logical volume %s'
                                   % (partitionname, parttype))
                part_info['supported'] = True
                part_info['usage'] = 'standard'
            elif parttype in data.partition_to_skip:
                self._logger.debug('Partition %s harmless: %s'
                                   % (partitionname, parttype))
                part_info['supported'] = False
                part_info['usage'] = 'na'
                gen_tools.result_msg('Partition type %s for %s is not '
                                     'supported but harmless, skipping.\n'
                                     % (partitionname, parttype))
            else:
                self._logger.debug('Partition %s unusable: %s'
                                   % (partitionname, parttype))
                part_info['supported'] = False
                part_info['usage'] = 'na'
                gen_tools.error_msg('Partition type %s for %s is not '
                                    'supported, quitting.\n'
                                    % (partitionname, parttype))
                raise OciMigrateException('Partition type %s for %s is not '
                                          'recognised and may break the '
                                          'operation.'
                                          % (parttype, partitionname))
        else:
        #    raise OciMigrateException('FS type missing from partition '
        #                              'information %s' % partitionname)
            self._logger.debug('No partition type specified, skipping')
            gen_tools.result_msg('No partition type found for %s, skipping.'
                                 % partitionname)
        #
        # get label, if any
        partition_label = migrate_utils.exec_lsblk(['-n', '-o', 'LABEL',
                                                    partitionname])
        if len(partition_label.rstrip()) > 0:
            gen_tools.result_msg('Partition label: %s' % partition_label)
            part_info['label'] = partition_label.rstrip()
        else:
            self._logger.debug('No label on %s.' % partitionname)
        #
        # for the sake of testing
        # gen_tools.pause_gt('test partition info')
        return part_info

    def mount_essential_dirs(self):
        """
        Mount directories defined in fstab which are required for a
        functional environment; failure to mount those file systems suggest
        not all partitions required for a successfully boot are present in
        this image file.

        Returns
        -------
            bool: True on success, raise an exception otherwise.
        """
        fstabline1 = [dirs[1] for dirs in self.img_info['fstab']]
        self._logger.debug('directories: %s' % fstabline1)
        self.img_info['remountlist'] = []
        for dirs in fstabline1:
            if dirs in data.essential_dir_list:
                gen_tools.result_msg('Should mount dir %s' % dirs)
                if migrate_utils.mount_fs(dirs):
                    self._logger.debug('Successfully mounted %s' % dirs)
                    self.img_info['remountlist'].append(dirs)
                else:
                    self._logger.critical('Failed to mount %s' % dirs)
                    raise OciMigrateException('Failed to mount %s' % dirs)
        return True

    def unmount_essential_dirs(self):
        """
        Unmount directories defined in fstab, if mounted.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        ret = True
        for mnt in self.img_info['remountlist']:
            if not migrate_utils.unmount_something(mnt):
                ret = False
        return ret

    def handle_image(self):
        """
        Process the image.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        try:
            #
            # mount image.
            self.devicename = self.mount_img()
            #
            # collect the image data.
            image_date_result = self.get_image_data()
            #
            # mount filesystems.
            if not self.mount_filesystems():
                raise OciMigrateException('Failed to mount filessystems')
            else:
                self._logger.debug('Mounting file systems succeeded.')
            #
            # collect os data.
            collect_data_result = self.collect_os_data()
            #
            # exit here for test reasons..
            # gen_tools.pause_gt('exiting here for test reasons')
            # return True
            #
            # update the image.
            _ = self.update_image()
            #
            # just for the matter of completeness:
            # get the oci configuration.
            ociconfig = migrate_utils.get_oci_config()
            self.img_info['oci_config'] = ociconfig
            return True
        except Exception as e:
            self._logger.critical('Image %s handling failed: %s'
                                  % (self.img_info['img_name'], str(e)))
            return False
        finally:
            #
            # unmount filesystems
            for mnt in self.mountpoints:
                migrate_utils.unmount_part(mnt)
            #
            # release lvm
            if 'volume_groups' in self.img_info:
                migrate_utils.unmount_lvm2(self.img_info['volume_groups'])
            #
            # release device and module
            if self.devicename:
                self._logger.debug('Releasing %s' % self.devicename)
                self.umount_img(self.devicename)
                if migrate_utils.rm_nbd():
                    self._logger.debug('Kernel module nbd removed.')
                else:
                    self._logger.error('Failed to remove kernel module nbd.')

    def get_image_data(self):
        """
        Get file system on the partition specified by device.

        Returns
        -------
            bool: True on success, raises an exception otherwise.
        """
        #
        # reading from the mounted image file
        self._logger.debug('Collecting data on %s' % self.devicename)
        try:
            #
            # Master Boot Record:
            thismbr = self.get_mbr(self.devicename)
            if thismbr is None:
                raise OciMigrateException('Failed to get MBR from '
                                          'device file %s' % self.devicename)
            else:
                self.img_info['mbr'] = {'bin': thismbr, 'hex':
                    migrate_utils.show_hex_dump(thismbr)}
                gen_tools.result_msg('Got mbr')
            #
            # Partition Table from MBR:
            mbrok, parttable = self.get_partition_table(self.img_info['mbr']['bin'])
            if not mbrok:
                raise OciMigrateException('Failed to get partition table from MBR')
            else:
                self.img_info['mbr']['valid'] = mbrok
                self.img_info['mbr']['partition_table'] = parttable
                gen_tools.result_msg('Got partition table')
            #
            # Device data
            parted_data = migrate_utils.exec_parted(self.devicename)
            if parted_data is None:
                raise OciMigrateException('Failed to collect parted %s '
                                          'device data.' % self.devicename)
            else:
                self.img_info['parted'] = parted_data
                gen_tools.result_msg('Got parted data')
                self._logger.debug('partition data: %s'
                                   % self.img_info['parted'])
            #
            # Partition info
            sfdisk_info = migrate_utils.exec_sfdisk(self.devicename)
            if sfdisk_info is None:
                raise OciMigrateException('Failed to collect sfdisk %s '
                                          'partition data.' % self.devicename)
            else:
                gen_tools.result_msg('Got sfdisk info')
                self.img_info['partitions'] = sfdisk_info
                self._logger.debug('Partition info: %s' % sfdisk_info)
            #
            # Partition data
            parttemplate = self.devicename + 'p*'
            self._logger.debug('partition %s : %s'
                               % (parttemplate, glob(parttemplate)))
            gen_tools.result_msg('Partition data for device %s'
                               % self.devicename)
            #
            # testing purposes
            # gen_tools.pause_gt('verify blkid..')
            for partname in glob(parttemplate):
                self._logger.debug('Get info on %s' % partname)
                self.img_info['partitions'][partname].update(
                    self.get_partition_info(partname))
            return True
        except Exception as e:
            #
            # need to release mount of image file and exit
            self._logger.critical('Initial partition data collection '
                                  'failed: %s' % str(e))
            raise OciMigrateException('Initial partition data collection '
                                      'failed:\n %s' % str(e))

    def mount_filesystems(self):
        """
        Mount the file systems in partitons and logical volumes.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        #
        # initialise logical volume structure
        self.img_info['volume_groups'] = dict()
        #
        # initialise list of mountpoints
        gen_tools.result_msg('Mount usable partition')
        #
        # loop through identified partitions, identify the type, mount it if
        # it is a standard partition hosting a supported filesystem; if a
        # partition contains a LVM2 physical volume, add the partition to the
        # lvm list for later use.
        success = True
        for devname, devdetail in self.img_info['partitions'].iteritems():
            self._logger.debug('Device: %s' % devname)
            self._logger.debug('Details:\n %s' % devdetail)
            gen_tools.result_msg('Partition %s' % devname)
            try:
                if 'ID_FS_TYPE' in devdetail:
                    if devdetail['ID_FS_TYPE'] in data.filesystem_types:
                        self._logger.debug('File system %s detected'
                                           % devdetail['ID_FS_TYPE'])
                        thismountpoint = migrate_utils.mount_partition(devname)
                        if thismountpoint is not None:
                            gen_tools.result_msg('Partition %s with file '
                                               'system %s mounted on %s.'
                                               % (devname, devdetail['ID_FS_TYPE'],
                                                  thismountpoint))
                            self._logger.debug('%s mounted' % devname)
                            devdetail['mountpoint'] = thismountpoint
                            self.mountpoints.append(thismountpoint)
                        else:
                            self._logger.critical('Failed to mount %s'
                                                  % devname)
                            success = False
                    elif devdetail['ID_FS_TYPE'] in data.logical_vol_types:
                        self._logger.debug('Logical volume %s detected'
                                           % devdetail['ID_FS_TYPE'])
                        gen_tools.result_msg('Logical volume %s'
                                           % devdetail['ID_FS_TYPE'])
                        volume_groups = migrate_utils.mount_lvm2(devname)
                        self.img_info['volume_groups'].update(volume_groups)
                    else:
                        self._logger.debug('Skipping %s.' % devdetail['ID_FS_TYPE'])
                        gen_tools.result_msg('Skipping %s' % devdetail['ID_FS_TYPE'])
                else:
                    self._logger.debug('%s does not exist or has '
                                       'unrecognised type' % devname)
            except Exception as e:
                #
                # failed to mount a supported filesystem on a partition...
                # not quitting yet, trying to collect as much info a possible
                # in this stage.
                success = False
                self._logger.critical('Failed to mount partition %s: %s'
                                      % (devname, str(e)))
        #
        # loop through the volume group list, identify the logical volumes
        # and mount them if they host a supported file system.
        for vg, lv in self.img_info['volume_groups'].iteritems():
            self._logger.debug('volume group %s' % vg)
            for part in lv:
                partname = '/dev/mapper/%s' % part[1]
                self._logger.debug('Partition %s' % partname)
                gen_tools.result_msg('Partition: %s' % partname)
                #
                # for the sake of testing
                # gen_tools.pause_gt('lv name test')
                devdetail = self.get_partition_info(partname)
                try:
                    if 'ID_FS_TYPE' in devdetail:
                        if devdetail['ID_FS_TYPE'] in data.filesystem_types:
                            self._logger.debug('file system %s detected'
                                               % devdetail['ID_FS_TYPE'])
                            thismountpoint = migrate_utils.mount_partition(partname)
                            if thismountpoint is not None:
                                gen_tools.result_msg('Partition %s with file '
                                                   'system %s mounted on %s.'
                                                   % (partname,
                                                      devdetail['ID_FS_TYPE'],
                                                      thismountpoint))
                                self._logger.debug('%s mounted' % partname)
                                devdetail['mountpoint'] = thismountpoint
                                self.mountpoints.append(thismountpoint)
                            else:
                                self._logger.critical('Failed to mount %s'
                                                      % partname)
                                success = False
                        else:
                            self._logger.debug('%s does not exist or has '
                                               'unrecognised type' % partname)
                    self.img_info['partitions'][partname] = devdetail
                except Exception as e:
                    success = False
                    self._logger.critical('Failed to mount logical '
                                          'volumes %s: %s' % (partname, str(e)))

        return success

    def collect_os_data(self):
        """
        Collect the relevant OS data.

        Returns
        -------
            bool: True on success, raise exception otherwise.
        """
        #
        # Collect the data
        oscollectmesg = ''
        try:
            #
            # import operation system type dependant modules
            osdata = self.get_os_data()
            if not osdata:
                oscollectmesg += '\n  . Unable to collect OS information.'
            else:
                self.img_info['osinformation'] = osdata
                self._logger.debug('OS type: %s' % osdata['ID'])
            #
            # import os-type specific modules
            os_spec_mod = migrate_utils.find_os_specific(osdata['ID'])
            self._logger.debug('OS specification: %s' % os_spec_mod)
            if os_spec_mod is None:
                oscollectmesg += '\n  . OS type %s is not recognised.' \
                                 % osdata['ID']
            else:
                self.img_info['ostype'] = \
                    importlib.import_module('oci_utils.migrate.' + os_spec_mod)
                self._logger.debug('OS type: %s' % self.img_info['ostype'])
            #
            # for the sake of testing
            # gen_tools.pause_gt('root and boot')
            #
            # root and boot
            rootpart, rootmount, bootpart, bootmount = self.get_root_boot_partition()
            if rootpart is None:
                oscollectmesg += '\n  . Failed to locate root partition.'
            else:
                gen_tools.result_msg('Root %s %s' % (rootpart, rootmount))
                self.img_info['rootmnt'] = [rootpart, rootmount]
                self.img_info['partitions'][rootpart]['usage'] = 'root'
                self._logger.debug('root: %s' % self.img_info['rootmnt'])
            if bootpart is None:
                oscollectmesg += '\n  . Failed to locate boot partition.'
            else:
                gen_tools.result_msg('Boot %s %s' % (bootpart, bootmount))
                self.img_info['bootmnt'] = [bootpart, bootmount]
                self.img_info['partitions'][bootpart]['usage'] = 'boot'
                self._logger.debug('boot: %s' % self.img_info['bootmnt'])
            #
            #
            if oscollectmesg:
                raise OciMigrateException(oscollectmesg)
            #
            # grub
            self.img_info['grubdata'] = self.get_grub_data()
            #
            # network
            self.img_info['network'] = \
                self.img_info['ostype'].get_network_data(rootmount)
        except Exception as e:
            self._logger.debug('Failed to collect os data: %s' % str(e))
            raise OciMigrateException('Failed to collect os data: %s' % str(e))
        return True

    def update_image(self):
        """
        Prepare the image for migration.

        Returns
        -------
            No return value, raises an exception on failure
        """
        os_type = self.img_info['ostype']
        try:
            #
            # mount fs: proc sys and dev
            self.img_info['pseudomountlist'] = \
                migrate_utils.mount_pseudo(self.img_info['rootmnt'][1])
            if self.img_info['pseudomountlist'] is None:
                raise OciMigrateException('Failed to mount proc sys or dev')
            else:
                self._logger.debug('pseudo mount list: %s'
                                   % self.img_info['pseudomountlist'])
                gen_tools.result_msg('Mounted: %s'
                                   % self.img_info['pseudomountlist'])
            #
            # chroot
            self._logger.debug('New root: %s' % self.img_info['rootmnt'][1])
            rootfd, pathsave = \
                migrate_utils.enter_chroot(self.img_info['rootmnt'][1])
            self._logger.debug('rootfd %s path %s' % (rootfd, pathsave))
            gen_tools.result_msg('Changed root to %s.' % pathsave)
            #
            # for the sake of testing
            with open('/etc/os-release', 'rb') as f:
                for line in f:
                    sys.stdout.write(line)
            gen_tools.pause_gt('chroot ...')
            #
            #  mount eventual file systems which are essential for the
            #  functioning of the os.
            if not self.mount_essential_dirs():
                raise OciMigrateException('Failed to mount essential '
                                          'file systems')
            else:
                self._logger.debug('All directories required for running the '
                                   'linux os are present.')
            #
            # for the sake of testing
            migrate_utils.exec_df()

            if not os_type.update_network_config():
                self._logger.error('Failed to update network configuration.')
                raise OciMigrateException('Failed to update network '
                                          'configuration.')
            else:
                self._logger.debug('Successfully upgraded network '
                                   'configuration.')
            #
            # this is the place to provide the opportunity to verify and
            # eventually modify data in the image, e.g. proxy configs,
            # nameserver settings,.. before installing cloud-init packages.
            pre_cloud_notification = 'Please verify nameserver, proxy, ' \
                                     'update-repository configuration before ' \
                                     'proceeding the cloud-init package ' \
                                     'install.'
            gen_tools.pause_gt(pre_cloud_notification)
            gen_tools.prog_msg('Installing the cloud-init package, '
                               'this might take a while.')
            cloud_init_install = gen_tools.ProGressBar(40, 0.5, ['_', '-', '+'])
            cloud_init_install.start()
            if os_type.install_cloud_init(
                    self.img_info['osinformation']['VERSION_ID']):
                self._logger.debug('Installed cloud init')
                gen_tools.result_msg('Installed cloud-init')
            else:
                self._logger.critical('Failed to install cloud init')
                gen_tools.result_msg('Failed to install cloud-init.')
                raise OciMigrateException('Failed to install cloud init')
            cloud_init_install.stop()
        except Exception as e:
            self._logger.error('Failed: %s' % str(e))
            raise OciMigrateException(str(e))
        finally:
            # if progressthread was started, needs to be terminated.
            if gen_tools.isthreadrunning(cloud_init_install):
                cloud_init_install.stop()
            #
            # unmount essential directories
            if self.unmount_essential_dirs():
                self._logger.debug('Successfully unmount essential file systems')
            else:
                self._logger.debug('Failed to unmout essential file systems')
            #
            # leave the chroot
            xx = migrate_utils.leave_chroot(rootfd, pathsave)
            self._logger.debug('Exit chroot: %s' % xx)
            #
            # unmount proc, sys dev
            migrate_utils.unmount_pseudo(self.img_info['pseudomountlist'])
            self._logger.debug('Released proc, sys, dev')

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
                        gen_tools.result_msg('Bootable partition %s mounted '
                                           'on %s' % (bootpart, bootmount))
                        break
                    else:
                        self._logger.debug('%s is not bootable' % part)
                else:
                    self._logger.debug('%s is not mounted' % part)
        except Exception as e:
            self._logger.debug('Failed to find the boot partition: %s'
                               % str(e))
            raise OciMigrateException('Failed to find the boot partition: %s'
                                      % str(e))
        return bootpart, bootmount

    def get_root_boot_partition(self):
        """
        Locate the root partition and collect relevant data; /etc/fstab is
        supposed to be on the root partition.

        Returns
        -------
            tuple: (root partition, root mountpoint, boot partiton ,
            boot mountpoint), (None, None, None, None) otherwise
        """
        thisfile = 'fstab'
        self._logger.debug('Looking for root and boot partition in %s'
                           % self.mountpoints)
        rootpart, rootmount, bootpart, bootmount = None, None, None, None
        try:
            for mnt in self.mountpoints:
                etcdir = mnt + '/etc'
                self._logger.debug('Looking in partition %s' % mnt)
                fstab = migrate_utils.exec_find(thisfile, etcdir)
                if fstab is not None:
                    #
                    # found fstab, reading it
                    # self.img_info['fstab'] = self.get_fstab()
                    fstabdata = self.get_fstab(fstab)
                    self.img_info['fstab'] = fstabdata
                    for line in fstabdata:
                        self._logger.debug('Checking %s' % line)
                        if line[1] == '/':
                            self._logger.debug('Root partition is %s.' % line[0])
                            rootpart, rootmount = self.find_partition(line[0])
                            if (rootpart, rootmount) == (None, None):
                                self._logger.critical('failed to locate '
                                                      'root partition %s.'
                                                      % line[0])
                        elif line[1] == '/boot':
                            self._logger.debug('Boot partition is %s.' % line[0])
                            bootpart, bootmount = self.find_partition(line[0])
                            if (bootpart, bootmount) == (None, None):
                                self._logger.critical('failed to locate '
                                                      'boot partition %s.'
                                                      % line[0])
                    gen_tools.result_msg('Root partition is mounted on %s.'
                                       % rootmount)
                    gen_tools.result_msg('Boot partition is mounted on %s.'
                                       % bootmount)
                    break
                else:
                    self._logger.debug('fstab not found in %s' % etcdir)
        except Exception as e:
            self._logger.critical('Failed to find the root or '
                                  'boot partition: %s' % str(e))
            raise OciMigrateException('Failed to find the root or '
                                      'boot partition: %s' % str(e))
        return rootpart, rootmount, bootpart, bootmount

    def find_partition(self, uuidorname):
        """
        Identify a partition and its current mount point with respect to a
        UUID or and LVM2name.

        Parameters
        ----------
        uuidorname: str
            The UUID or LVM2 name.

        Returns
        -------
            tuple: The partition and the current mount point.
        """
        part, mount = None, None
        uuid_s = re.split('\\bUUID=\\b', uuidorname)
        if len(uuid_s) > 1:
            uuid_x = uuid_s[1]
        else:
            uuid_x = uuid_s[0]
        for partition, partdata in self.img_info['partitions'].iteritems():
            self._logger.debug('uuidorname: %s' % uuid_x)
            if 'ID_FS_UUID' in partdata.keys():
                if partdata['ID_FS_UUID'] == uuid_x:
                    part = partition
                    mount = partdata['mountpoint']
                    self._logger.debug('%s found in %s' % (uuid_x, partition))
                    break
                else:
                    self._logger.debug('%s not in %s' % (uuid_x, partition))
            if partition == uuidorname:
                part = partition
                mount = partdata['mountpoint']
                self._logger.debug('%s found in %s' % (uuid_x, partition))
                break
        return part, mount

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
                    self._logger.debug('Looking for %s in %s'
                                       % (grubname, grubroot))
                    grubconf = migrate_utils.exec_find(grubname, grubroot)
                    if grubconf is not None:
                        grub_cfg_path = grubconf
                        self._logger.debug('Found grub config file: %s'
                                           % grub_cfg_path)
                        break
                    else:
                        self._logger.debug('No grub config file in %s'
                                           % mnt + '/boot')
        #
        # if no grub config file is found, need to quit.
        if grub_cfg_path is None:
            raise OciMigrateException('No grub config file found in %s'
                                      % self.fn)
        else:
            gen_tools.result_msg('Grub config file: %s' % grub_cfg_path)
        #
        # investigate grub cfg path: contents of EFI/efi directory.
        if 'EFI' in grub_cfg_path.split('/'):
            self.img_info['boot_type'] = 'UEFI'
        else:
            self.img_info['boot_type'] = 'BIOS'
        self._logger.debug('Image boot type is %s' % self.img_info['boot_type'])
        gen_tools.result_msg('Image boot type: %s' % self.img_info['boot_type'])
        #
        # get grub config contents
        grubdata = list()
        grub2 = False
        grubentry = dict()
        self._logger.debug('Initialised grub structure')
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
                                self._logger.debug('Grub line: %s'
                                                   % grubentry['menuentry'])
                            else:
                                self._logger.debug('Not a menuentry, '
                                                   'skipping %s' % fsline)
                        else:
                            self._logger.debug('Skipping %s' % fsline)
            if grubentry:
                grubdata.append(grubentry)
        except Exception as e:
            self._logger.error('Errors during reading %s: %s'
                               % (grub_cfg_path, str(e)))
            raise OciMigrateException('Errors during reading %s: %s'
                                      % (grub_cfg_path, str(e)))
        if grub2:
            self._logger.debug('Found grub2 configuration file.')
            gen_tools.result_msg('Found grub2 configuration file')
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
                                self._logger.debug('grub line: %s'
                                                   % grubentry['title'])
                            else:
                                self._logger.debug('skipping %s' % fsline)
                if grubentry:
                    grubdata.append(grubentry)
            except Exception as e:
                self._logger.error('Errors during reading %s: %s'
                                   % (grub_cfg_path, str(e)))
                raise OciMigrateException('Errors during reading %s: %s'
                                          % (grub_cfg_path, str(e)))

        return grubdata

    def get_os_data(self):
        """
        Collect information on the linux operating system and release.
        Currently is only able to handle linux type os.

        Returns
        -------
            dict: Dictionary containing the os and version data on success,
            empty dict otherwise.
        """
        self._logger.debug('Collection os data, looking in %s'
                           % self.mountpoints)
        osdict = dict()
        #
        # hostnamectl is a systemd command, not available in OL/RHEL/CentOS 6
        try:
            for mnt in self.mountpoints:
                osdata = migrate_utils.exec_find('os-release', mnt)
                if osdata is not None:
                    with open(osdata, 'rb') as f:
                        osreleasedata = [line.strip()
                                         for line in f.read().splitlines()
                                         if '=' in line]
                    osdict = dict([re.sub(r'"', '', kv).split('=')
                                   for kv in osreleasedata])
                    break
                else:
                    self._logger.debug('os-release not found in %s' % mnt)
        except Exception as e:
            self._logger.error('Failed to collect os data: %s' % str(e))
        self._logger.debug('os data: %s' % osdict)
        return osdict

    def get_fstab(self, fstabfile):
        """
        Read and analyse fstab file.

        Parameters
        ----------
            fstabfile: str
                Full path of the fstab file.

        Returns
        -------
            list: Relevant lines of fstab files as list.
        """
        fstabdata = list()
        # fstabfile = self.img_info['rootmnt'][1] + '/etc/fstab'
        self._logger.debug('Fstabfile: %s' % fstabfile)
        try:
            with open(fstabfile, 'rb') as f:
                for fsline in f:
                    if '#' not in fsline and len(fsline.split()) > 5:
                        fstabdata.append(fsline.split())
                        gen_tools.result_msg('%s' % fsline.split())
                    else:
                        self._logger.debug('skipping %s' % fsline)
        except Exception as e:
            self._logger.error('Problem reading %s: %s' % (fstabfile, str(e)))
        return fstabdata

#    def get_network_data(self):
#        """
#        Collect the network configuration files.
#
#        Returns
#        -------
#            list: List with dictionary representation of the network
#            configuration files.
#        """
#        network_list = dict()
#        network_dir = self.img_info['rootmnt'][1] \
#                      + '/etc/sysconfig/network-scripts'
#        self._logger.debug('Network directory: %s' % network_dir)
#        try:
#            for cfgfile in glob(network_dir + '/ifcfg-*'):
#                with open(cfgfile, 'rb') as f:
#                    nl = filter(None, [x[:x.find('#')] for x in f])
#                ifcfg = dict(l.translate(None, '"').split('=') for l in nl)
#                network_list.update({cfgfile.split('/')[-1]: ifcfg})
#                self._logger.debug('Network interface: %s : %s' %
#                                   (cfgfile.split('/')[-1], ifcfg))
#                gen_tools.result_msg('Network interface: %s : %s' %
#                                   (cfgfile.split('/')[-1], ifcfg))
#        except Exception as e:
#            self._logger.error('Problem reading network configuration '
#                               'files: %s' % str(e))
#        return network_list

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
        if 'boot_type' in self.img_info:
            if self.img_info['boot_type'] in data.valid_boot_types:
                self._logger.debug('Boot type is %s, ok'
                                   % self.img_info['boot_type'])
                gen_tools.result_msg('Boot type is %s, ok'
                                   % self.img_info['boot_type'])
            else:
                thispass = False
                self._logger.debug('Boot type %s is not a valid boot '
                                   'type. ' % self.img_info['boot_type'])
                failmsg += '\n  - Boot type %s is not a valid boot ' \
                           'type. ' % self.img_info['boot_type']
        else:
            thispass = False
            failmsg += '\n  - Boot type not found.'
        #
        # MBR
        if 'mbr' in self.img_info:
            if self.img_info['mbr']['valid']:
                self._logger.debug('The image %s contains a '
                                   'valid MBR.' % self.img_info['img_name'])
                gen_tools.result_msg('The image %s contains a '
                                   'valid MBR.' % self.img_info['img_name'])
            else:
                thispass = False
                self._logger.debug('The image %s does not contain a '
                                   'valid MBR.' % self.img_info['img_name'])
                failmsg += '\n  - The image %s does not contain a ' \
                           'valid MBR.' % self.img_info['img_name']
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
                    self._logger.debug('The image %s is bootable'
                                       % self.img_info['img_name'])
                    gen_tools.result_msg('The image %s is bootable'
                                       % self.img_info['img_name'])
            if not bootflag:
                thispass = False
                failmsg += '\n  - The image %s is not bootable.' \
                           % self.img_info['img_name']
        else:
            thispass = False
            failmsg += '\n  - MBR not found.'
        #
        # Everything needed to boot in this image? Compairing fstab with
        # partition data.
        if 'fstab' in self.img_info:
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
                                self._logger.debug('Found %s in partition '
                                                   'table.' % uuid_x)
                                gen_tools.result_msg('Found %s in partition '
                                                   'table.' % uuid_x)
                                break
                elif 'LABEL' in line[0]:
                    label_x = re.split('\\bLABEL=\\b', line[0])[1]
                    for _, part in partitiondata.iteritems():
                        if 'label' in part:
                            if part['label'] == label_x:
                                part_pass = True
                                self._logger.debug('Found %s in partition '
                                                   'table.' % label_x)
                                gen_tools.result_msg('Found %s in partition '
                                                   'table.' % label_x)
                                break
                elif 'mapper' in line[0]:
                    lv_x = re.split('\\bmapper/\\b', line[0])[1]
                    for part, _ in partitiondata.iteritems():
                        if lv_x in part:
                            part_pass = True
                            self._logger.debug('Found %s in partition '
                                               'table.' % lv_x)
                            gen_tools.result_msg('Found %s in partition '
                                               'table.' % lv_x)
                            break
                elif '/dev/' in line[0]:
                    self._logger.critical('Device name %s in fstab are '
                                          'not supported.' % line[0])
                else:
                    part_pass = True
                    self._logger.debug('Unrecognised: %s, ignoring.' % line[0])
                    gen_tools.result_msg('Unrecognised: %s, ignoring.' % line[0])

                if not part_pass:
                    fstab_pass = False
                    break

            if not fstab_pass:
                thispass = False
                failmsg += '\n  - fstab file refers to unsupported or ' \
                           'unreachable partitions.'
        else:
            thispass = False
            failmsg += '\n  - fstab file not found.'
        #
        # boot using LVM or UUID
        if 'grubdata' in self.img_info:
            grubdata = self.img_info['grubdata']
        #
        # grub: 'root=UUID'
        # grub2: '--fs-uuid'
            grub_fail = 0
            grub_l = 0
            for entry in grubdata:
                for key in entry:
                    for l in entry[key]:
                        l_split = l.split()
                        if l_split[0] == 'search':
                            grub_l += 1
                            if '--fs-uuid' not in l_split:
                                self._logger.error('grub2 line ->%s<- does not '
                                                   'specify boot partition '
                                                   'via UUID.' % l)
                                grub_fail += 1
                            else:
                                gen_tools.result_msg('grub2 line ->%s<- '
                                                   'specifies boot partition '
                                                   'via UUID.' % l)
                        elif l_split[0] == 'kernel':
                            grub_l += 1
                            if len([a for a in l_split
                                    if any(b in a
                                           for b in ['root=UUID='])]) == 0:
                                self._logger.error('grub line ->%s<- does not '
                                                   'specify boot partition '
                                                   'via UUID.' % l)
                                grub_fail += 1
                            else:
                                gen_tools.result_msg('grub line ->%s<- '
                                                   'specifies boot partition '
                                                   'via UUID.' % l)
                        else:
                            self._logger.debug('skipping %s' % l_split)
            if grub_l == 0:
                thispass = False
                failmsg += '\n  - No boot entry found in grub/gru2 config file.'
            elif grub_fail > 0:
                thispass = False
                failmsg += '\n  - grub config file does not guarantee booting ' \
                           'using UUID'
            else:
                self._logger.debug('Grub config file ok.')
        else:
            thispass = False
            failmsg += '\n  - Grub config file not found.'
        #
        # OS
        if 'osinformation' in self.img_info:
            osdata = self.img_info['osinformation']
            os_pass = False
            os_name = 'notsupportedos'
            for k, v in osdata.iteritems():
                self._logger.debug('%s %s' % (k, v))
                if k.upper() == 'NAME':
                    vu = v.upper().strip()
                    os_name = v
                    self._logger.debug('OS name: %s' % vu)
                    if vu in data.valid_os:
                        self._logger.debug('OS is a %s: valid' % v)
                        gen_tools.result_msg('OS is a %s: valid' % v)
                        os_pass = True
                    else:
                        self._logger.error('->OS<- %s is not supported.' % v)
            if not os_pass:
                thispass = False
                failmsg += '\n  - OS %s is not supported' % os_name
        else:
            thispass = False
            failmsg += '\n  - OS release file not found.'
        #
        # network interface configuration, need to remount /etc at least???
        if 'network' in self.img_info:
            networkdata = self.img_info['network']
            for network, nicdata in networkdata.iteritems():
                gen_tools.result_msg('Network interface: %s' % network)
                if 'HWADDR' in nicdata:
                    self._logger.error('Hardcoded mac addres %s, fail'
                                       % nicdata['HWADDR'])
                    failmsg += '\n  - Hardcoded mac addres %s for %s' \
                               % (nicdata['HWADDR'], network)
                    thispass = False
                    gen_tools.result_msg('  Hardcoded mac addres, fail')
                if 'BOOTPROTO' in nicdata:
                    if nicdata['BOOTPROTO'].upper() != 'DHCP':
                        gen_tools.result_msg('  BOOTPROTO is not dhcp')
                if 'ONBOOT' in nicdata:
                    if nicdata['ONBOOT'].upper() == 'YES':
                        gen_tools.result_msg('  ONBOOT is yes')
        else:
            thispass = False
            failmsg += '\n  - Network data not found.'

        return thispass, failmsg

