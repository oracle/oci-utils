#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module to handle device data.
"""

import importlib
import logging
import os
import re
import sys
import threading
import time
from glob import glob as glob

# for the sake of testing
sys.path.append('/omv/data/git_pycharm/oci-utils/lib')
from oci_utils.migrate import migrate_utils as migrate_utils
from oci_utils.migrate.exception import OciMigrateException
from oci_utils.migrate import gen_tools
from oci_utils.migrate import configdata
from oci_utils.migrate import reconfigure_network

_logger = logging.getLogger('oci-image-migrate.')


def test():
    """
    Placeholder

    Returns
    -------
        No return value
    """
    gen_tools.result_msg(msg=__name__)


class UpdateImage(threading.Thread):
    """
    Class to update the virtual disk image in a chroot jail.

    Attributes
    ----------
    """
    def __init__(self, vdiskdata, logger=None):
        """ Initialisation of the UpdateImage object.
        """
        self._logger = logger or logging.getLogger(__name__)
        self.imgdata = vdiskdata
        threading.Thread.__init__(self)

    def run(self):
        """Run the chroot operations
        """
        gen_tools.result_msg(msg='Opening Thread.')
        self.chrootjail_ops()

#    def join(self, timeout=None):
#        """ Terminate
#        """
#        gen_tools.result_msg('Joining Thread.')
#        threading.Thread.join(self, timeout)

    def wait4end(self):
        """ Stop
        """
        gen_tools.result_msg(msg='Waiting for ')
        self.join()

    def chrootjail_ops(self):
        """
        Create the chroot jail.

        Returns
        -------

        """
        gen_tools.result_msg(msg='Creating chroot jail.')
        # gen_tools.pause_msg('chroot jail entry')
        os_type = self.imgdata['ostype']
        try:
            self.imgdata['pseudomountlist'] \
                = migrate_utils.mount_pseudo(self.imgdata['rootmnt'][1])
            gen_tools.result_msg(msg='Mounted proc, sys, dev')
            #
            # chroot
            self._logger.debug('New root: %s' % self.imgdata['rootmnt'][1])
            rootfd, pathsave = migrate_utils.enter_chroot(self.imgdata['rootmnt'][1])
            gen_tools.result_msg(msg='Changed root to %s.' % self.imgdata[
                'rootmnt'][1])
            #
            # check current working directory
            thiscwd = os.getcwd()
            gen_tools.result_msg(msg='Current working directory is %s' %
                                     thiscwd)
            #
            # verify existence /etc/resolve.conf
            if gen_tools.file_exists('/etc/resolv.conf'):
                gen_tools.result_msg(msg='File /etc/resolv.conf found.')
            else:
                gen_tools.result_msg(msg='No file /etc/resolv.conf found',
                                     result=True)
                if gen_tools.link_exists('/etc/resolv.conf'):
                    gen_tools.result_msg(msg='/etc/result.conf is a symbolic '
                                         'link.', result=True)
                else:
                    gen_tools.result_msg(msg='Really no /etc/resolv.conf.',
                                         result=True)
            #
            # gen_tools.pause_msg('In chroot:')
            pre_cloud_notification = 'Please verify nameserver, proxy, ' \
                                     'update-repository configuration before ' \
                                     'proceeding the cloud-init package ' \
                                     'install.'
            gen_tools.pause_msg(pre_cloud_notification)
            gen_tools.result_msg(msg='Installing the cloud-init package, '
                                 'this might take a while.', result=True)
            cloud_init_install = gen_tools.ProGressBar(1, 0.5)
            cloud_init_install.start()
            if os_type.install_cloud_init(self.imgdata['osinformation']['VERSION_ID']):
                gen_tools.result_msg(msg='', result=True)
                gen_tools.result_msg(msg='Installed cloud-init', result=True)
            else:
                self._logger.critical('Failed to install cloud init')
                # gen_tools.result_msg('Failed to install cloud-init.')
                raise OciMigrateException('Failed to install cloud init')
        except Exception as e:
            self._logger.critical('*** ERROR *** Unable to perform image '
                                  'update operations: %s' % str(e))
        finally:
            if gen_tools.isthreadrunning(cloud_init_install):
                cloud_init_install.stop()
            migrate_utils.leave_chroot(rootfd)
            gen_tools.result_msg(msg='Left chroot jail.')
            migrate_utils.unmount_pseudo(self.imgdata['pseudomountlist'])
            gen_tools.result_msg(msg='Unmounted proc, sys, dev.')
        time.sleep(1)
        gen_tools.result_msg(msg='Leaving chroot jail.')


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
            # active partition: find partition with bootflag
            self._logger.debug('boot? : %s' % partentry[0:2])
            if partentry[0:2] == bootflag:
                part['boot'] = True
            else:
                part['boot'] = False
            #
            # type
            typeflag = partentry[8:10].lower()
            self._logger.debug('type? : %s' % typeflag)
            if typeflag in configdata.partition_types:
                part['type'] = configdata.partition_types[typeflag]
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
        self._logger.debug('Collecting information on %s' % partitionname)
        blkid_args = ['-po', 'udev']
        blkid_args.append(partitionname)
        self._logger.debug('blkid %s' % blkid_args)
        gen_tools.result_msg(msg='Investigating partition %s' % partitionname)
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
            gen_tools.result_msg(msg='Partition type %s' % parttype)
            if parttype in configdata.filesystem_types:
                self._logger.debug('Partition %s contains filesystem %s'
                                   % (partitionname, parttype))
                part_info['supported'] = True
                part_info['usage'] = 'standard'
            elif parttype in configdata.logical_vol_types:
                self._logger.debug('Partition %s contains a logical volume %s'
                                   % (partitionname, parttype))
                part_info['supported'] = True
                part_info['usage'] = 'standard'
            elif parttype in configdata.partition_to_skip:
                self._logger.debug('Partition %s harmless: %s'
                                   % (partitionname, parttype))
                part_info['supported'] = False
                part_info['usage'] = 'na'
                gen_tools.result_msg(msg='Partition type %s for %s is not '
                                     'supported but harmless, skipping.\n'
                                     % (partitionname, parttype))
            else:
                self._logger.debug('Partition %s unusable: %s'
                                   % (partitionname, parttype))
                part_info['supported'] = False
                part_info['usage'] = 'na'
                gen_tools.error_msg('Partition type %s for %s is not '
                                    'supported, quitting.\n'
                                    % (parttype, partitionname))
                raise OciMigrateException('Partition type %s for %s is not '
                                          'recognised and may break the '
                                          'operation.'
                                          % (parttype, partitionname))
        else:
        #    raise OciMigrateException('FS type missing from partition '
        #                              'information %s' % partitionname)
            part_info['supported'] = False
            part_info['usage'] = 'na'
            self._logger.debug('No partition type specified, skipping')
            gen_tools.result_msg(msg='No partition type found for %s, skipping.'
                                 % partitionname)
        #
        # get label, if any
        partition_label = migrate_utils.exec_lsblk(['-n', '-o', 'LABEL',
                                                    partitionname])
        if len(partition_label.rstrip()) > 0:
            gen_tools.result_msg(msg='Partition label: %s' % partition_label)
            part_info['label'] = partition_label.rstrip()
        else:
            self._logger.debug('No label on %s.' % partitionname)
        #
        # for the sake of testing
        # gen_tools.pause_msg('test partition info')
        return part_info

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
            # gen_tools.pause_msg('file systems mounted')
            #
            # collect os data.
            _ = self.collect_os_data()
            #
            # pause here for test reasons..
            # gen_tools.pause_msg('pausing here for test reasons')
            #
            # update the network configuration.
            if reconfigure_network.update_network_config(self.img_info['rootmnt'][1]):
                self._logger.debug('Successfully upgraded the network configuration.')
            else:
                self._logger.error('Failed to update network configuration.')
                raise OciMigrateException('Failed to update network configuration.')
            # pause here for test reasons..
            # gen_tools.pause_msg('pausing here for test reasons')
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
            # unmount partitions from remount
            self._logger.debug('Unmount partitions.')
            if self.unmount_partitions():
                self._logger.debug('Successfully unmounted.')
            else:
                gen_tools.error_msg('Failed to release remounted filesystems, '
                                    'might prevent successful completions of %s.'
                                    % sys.argv[0])
            #
            # unmount filesystems
            self._logger.debug('Unmount filesystems.')
            for mnt in self.mountpoints:
                self._logger.debug('--- %s' % mnt)
                migrate_utils.unmount_part(mnt)
            #
            # release lvm
            self._logger.debug('release volume groups')
            if 'volume_groups' in self.img_info:
                migrate_utils.unmount_lvm2(self.img_info['volume_groups'])
            else:
                self._logger.debug('No volume groups defined.')
            #
            # release device and module
            if self.devicename:
                self._logger.debug('Releasing %s' % str(self.devicename))
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
                self.img_info['mbr'] = \
                    {'bin': thismbr, 'hex': migrate_utils.show_hex_dump(thismbr)}
                gen_tools.result_msg(msg='Found MBR.', result=True)
            #
            # Partition Table from MBR:
            mbrok, parttable = self.get_partition_table(self.img_info['mbr']['bin'])
            if not mbrok:
                raise OciMigrateException('Failed to get partition table from MBR')
            else:
                self.img_info['mbr']['valid'] = mbrok
                self.img_info['mbr']['partition_table'] = parttable
                gen_tools.result_msg(msg='Found partition table.', result=True)
            #
            # Device data
            parted_data = migrate_utils.exec_parted(self.devicename)
            if parted_data is None:
                raise OciMigrateException('Failed to collect parted %s '
                                          'device data.' % self.devicename)
            else:
                self.img_info['parted'] = parted_data
                gen_tools.result_msg(msg='Got parted data')
                self._logger.debug('partition data: %s'
                                   % self.img_info['parted'])
            #
            # Partition info
            sfdisk_info = migrate_utils.exec_sfdisk(self.devicename)
            if sfdisk_info is None:
                raise OciMigrateException('Failed to collect sfdisk %s '
                                          'partition data.' % self.devicename)
            else:
                gen_tools.result_msg(msg='Got sfdisk info')
                self.img_info['partitions'] = sfdisk_info
                self._logger.debug('Partition info: %s' % sfdisk_info)
                self._logger.debug('Partition info: %s'
                                   % self.img_info['partitions'])
                for k, v in self.img_info['partitions'].iteritems():
                    self._logger.debug('%s - %s' % (k, v))
                    v['usage'] = 'na'
                    v['supported'] = False
            #
            # Partition data
            parttemplate = self.devicename + 'p*'
            self._logger.debug('Partition %s : %s'
                               % (parttemplate, glob(parttemplate)))
            gen_tools.result_msg(msg='Partition data for device %s'
                                     % self.devicename)
            #
            # testing purposes
            # gen_tools.pause_msg('verify blkid..')
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
        gen_tools.result_msg(msg='Mounting partitions.')
        #
        # loop through identified partitions, identify the type, mount it if
        # it is a standard partition hosting a supported filesystem; if a
        # partition contains a LVM2 physical volume, add the partition to the
        # lvm list for later use.
        success = True
        for devname, devdetail in self.img_info['partitions'].iteritems():
            self._logger.debug('Device: %s' % devname)
            self._logger.debug('Details:\n %s' % devdetail)
            gen_tools.result_msg(msg='Partition %s' % devname)
            try:
                if 'ID_FS_TYPE' in devdetail:
                    if devdetail['ID_FS_TYPE'] in configdata.filesystem_types:
                        self._logger.debug('File system %s detected'
                                           % devdetail['ID_FS_TYPE'])
                        thismountpoint = migrate_utils.mount_partition(devname)
                        if thismountpoint is not None:
                            gen_tools.result_msg(msg='Partition %s with file '
                                                 'system %s mounted on %s.'
                                                 % (devname,
                                                    devdetail['ID_FS_TYPE'],
                                                    thismountpoint),
                                                 result=True)
                            self._logger.debug('%s mounted' % devname)
                            devdetail['mountpoint'] = thismountpoint
                            self.mountpoints.append(thismountpoint)
                        else:
                            self._logger.critical('Failed to mount %s'
                                                  % devname)
                            success = False
                    elif devdetail['ID_FS_TYPE'] in configdata.logical_vol_types:
                        self._logger.debug('Logical volume %s detected'
                                           % devdetail['ID_FS_TYPE'])
                        gen_tools.result_msg(msg='Logical volume %s'
                                                 % devdetail['ID_FS_TYPE'],
                                             result=True)
                        volume_groups = migrate_utils.mount_lvm2(devname)
                        self.img_info['volume_groups'].update(volume_groups)
                    else:
                        self._logger.debug('Skipping %s.' % devdetail['ID_FS_TYPE'])
                        gen_tools.result_msg(msg='Skipping %s'
                                                 % devdetail['ID_FS_TYPE'])
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
                gen_tools.result_msg(msg='Partition: %s' % partname)
                #
                # for the sake of testing
                # gen_tools.pause_msg('lv name test')
                devdetail = self.get_partition_info(partname)
                try:
                    if 'ID_FS_TYPE' in devdetail:
                        if devdetail['ID_FS_TYPE'] in configdata.filesystem_types:
                            self._logger.debug('file system %s detected'
                                               % devdetail['ID_FS_TYPE'])
                            thismountpoint = migrate_utils.mount_partition(partname)
                            if thismountpoint is not None:
                                gen_tools.result_msg(
                                    msg='Partition %s with file system %s '
                                        'mounted on %s.'
                                        % (partname, devdetail['ID_FS_TYPE'],
                                           thismountpoint), result=True)
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

    def remount_partitions(self):
        """
        Remount the partitions identified in fstab on the identified root
        partition.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        # self.img_info['remountlist'] = []
        rootfs = self.img_info['rootmnt'][1]
        self._logger.debug('Mounting on %s' % rootfs)
        # Loop through partition list and create a sorted list of the
        # non-root partitions and mount those on the root partition.
        # The list is sorted to avoid overwriting subdirectory mounts like
        # /var, /var/log, /van/log/auto,.....
        mountlist = []
        for k, v in self.img_info['partitions'].iteritems():
            self._logger.debug('remount?? %s' % k)
            self._logger.debug('remount?? %s' % v)
            if 'ID_FS_TYPE' not in v:
                self._logger.debug('%s is not in use' % k)
            else:
                if v['ID_FS_TYPE'] in configdata.filesystem_types:
                    if v['usage'] not in ['root', 'na']:
                        mountlist.append((v['usage'], k, v['mountpoint']))
                    else:
                        self._logger.debug('Partition %s not required.' % k)
                else:
                    self._logger.debug('Type %s not a mountable file '
                                       'system type.' % v['ID_FS_TYPE'])
        mountlist.sort()
        self._logger.debug('mountlist: %s' % mountlist)

        for part in mountlist:
            self._logger.debug('Is %s a candidate?' % part[0])
            mountdir = rootfs + '/' + part[0]
            self._logger.debug('Does mountpoint %s exist?' % mountdir)
            if gen_tools.dir_exists(mountdir):
                self._logger.debug('Mounting %s on %s.' % (part[1], mountdir))
                try:
                    resultmnt = migrate_utils.mount_partition(part[1], mountdir)
                    if resultmnt is not None:
                        self._logger.debug('Mounted %s successfully.' % resultmnt)
                        gen_tools.result_msg(msg='Mounted %s on %s.'
                                             % (part[1], mountdir),
                                             result=True)
                        self.img_info['remountlist'].append(resultmnt)
                    else:
                        self._logger.error('Failed to mount %s.' % mountdir)
                        raise OciMigrateException('Failed to mount %s'
                                                  % mountdir)
                except Exception as e:
                    self._logger.error('Failed to mount %s: %s.'
                                       % (mountdir, str(e)))
                    # not sure where to go from here
            else:
                self._logger.error('Something wrong, %s does not exist.')

        return True

    def unmount_partitions(self):
        """
        Unmount partitions mounted earlier.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        ret = True
        if 'remountlist' in self.img_info:
            if len(self.img_info['remountlist']) <= 0:
                return ret

            self.img_info['remountlist'].sort()
            for part in self.img_info['remountlist']:
                self._logger.debug('Releasing %s' % part)
                if migrate_utils.unmount_something(part):
                    self._logger.debug('Successfully released %s.' % part)
                else:
                    self._logger.error('Failed to release %s, might prevent '
                                       'clean termination.' % part)
                    ret = False
        else:
            self._logger.debug('No remountlist.')
        return ret

    def collect_os_data(self):
        """
        Collect the relevant OS data.

        Returns
        -------
            bool: True on success, raise exception otherwise.
        """
        self.img_info['remountlist'] = list()
        #
        # Collect the data
        oscollectmesg = ''
        try:
            #
            # import operation system type dependant modules
            osrelease = self.get_os_release()
            if not osrelease:
                oscollectmesg += '\n  . Unable to collect OS information.'
            else:
                self.img_info['osinformation'] = osrelease
                self._logger.debug('OS type: %s' % osrelease['ID'])
            #
            # import os-type specific modules
            os_spec_mod = migrate_utils.find_os_specific(osrelease['ID'])
            self._logger.debug('OS specification: %s' % os_spec_mod)
            if os_spec_mod is None:
                oscollectmesg += '\n  . OS type %s is not recognised.' \
                                 % osrelease['ID']
            else:
                self.img_info['ostype'] = \
                    importlib.import_module('oci_utils.migrate.' + os_spec_mod)
                self._logger.debug('OS type: %s' % self.img_info['ostype'])
                self.img_info['ostype'].os_banner()
            #
            # for the sake of testing
            # gen_tools.pause_msg('root and boot')
            #
            # root and boot
            rootpart, rootmount = self.identify_partitions()
            if rootpart is None:
                oscollectmesg += '\n  . Failed to locate root partition.'
            else:
                gen_tools.result_msg(msg='Root %s %s' % (rootpart, rootmount))
                self.img_info['rootmnt'] = [rootpart, rootmount]
                self._logger.debug('root: %s' % self.img_info['rootmnt'])
            bootpart, bootmount = self.get_partition('/boot')
            if bootpart is None:
                gen_tools.result_msg(msg='/boot is not on a separate partition '
                                     'or is missing. The latter case which '
                                     'will cause failure.', result=True)
            else:
                gen_tools.result_msg(msg='Boot %s %s' % (bootpart, bootmount))
            self.img_info['bootmnt'] = [bootpart, bootmount]
            self._logger.debug('boot: %s' % self.img_info['bootmnt'])
            #
            # remount image partitions on root partition
            if self.remount_partitions():
                self._logger.debug('Essential partitions mounted.')
                # gen_tools.pause_msg('Verify mounted partitions')
            else:
                raise OciMigrateException('Failed to mount essential partitions.')
            #
            if oscollectmesg:
                raise OciMigrateException(oscollectmesg)
            else:
                self._logger.debug('OS data collected.')
            #
            # grub
            self.img_info['grubdata'] = self.get_grub_data(self.img_info['rootmnt'][1])
            #
        except Exception as e:
            self._logger.critical('Failed to collect os data: %s' % str(e))
            raise OciMigrateException('Failed to collect os data: %s' % str(e))
        return True

    def update_image(self):
        """
        Prepare the image for migration.

        Returns
        -------
            No return value, raises an exception on failure
        """
        # os_type = self.img_info['ostype']

        try:
            self._logger.debug('Updating image.')
            updimg = UpdateImage(self.img_info)
            updimg.start()
            self._logger.debug('Waiting for update to end.')
            updimg.wait4end()

        except Exception as e:
            self._logger.error('Failed: %s' % str(e))
            raise OciMigrateException(str(e))
        finally:
            self._logger.debug('NOOP')

    def get_partition(self, mnt):
        """
        Find the definition of the boot partition in the device data structure.

        Returns
        -------
            tuple: partition, mountpoint on success, None otherwise.
        """
        thepartitions = self.img_info['partitions']
        for k, v in thepartitions.iteritems():
            if 'usage' in v:
                if v['usage'] == mnt:
                    self._logger.debug('Found %s in %s' % (mnt, v['mountpoint']))
                    return k, v['mountpoint']
            else:
                self._logger.debug('%s has no usage entry, skipping.' % k)
        self._logger.debug('%s not found.' % mnt)
        return None, None

    def identify_partitions(self):
        """
        Locate the root partition and collect relevant data; /etc/fstab is
        supposed to be on the root partition.
        Identify all partitions in the image.

        Returns
        -------
            tuple: (root partition, root mountpoint) on success,
            (None, None) otherwise
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
                        if line[1] in configdata.partition_to_skip:
                            self._logger.debug('Skipping %s' % line)
                        elif line[1] == '/':
                            self._logger.debug('Root partition is %s.' % line[0])
                            rootpart, rootmount = self.find_partition(line[0])
                            if (rootpart, rootmount) == (None, None):
                                self._logger.critical(
                                    'Failed to locate root partition %s.' % line[0])
                                raise OciMigrateException(
                                    'Failed to locate root partition %s.' % line[0])
                            else:
                                self.img_info['partitions'][rootpart]['usage'] \
                                    = 'root'
                        else:
                            self._logger.debug('Some other partition %s for %s.'
                                               % (line[0], line[1]))
                            part, mount = self.find_partition(line[0])
                            if (part, mount) == (None, None):
                                self._logger.debug(
                                    'Partition %s not used or not present.'
                                    % line[0])
                                raise OciMigrateException(
                                    'Failed to locate a partition %s.'
                                    % line[0])
                            else:
                                self.img_info['partitions'][part]['usage'] = line[1]
                        gen_tools.result_msg(msg='Identified partition %s'
                                             % line[1], result=True)
                    gen_tools.result_msg(msg='Root partition is mounted on %s.'
                                             % rootmount)
                    break
                else:
                    self._logger.debug('fstab not found in %s' % etcdir)
        except Exception as e:
            self._logger.critical('Error in partition identification: %s'
                                  % str(e))
            raise OciMigrateException('Error in partition identification: %s'
                                      % str(e))
        return rootpart, rootmount

    def skip_partition(self, partdata):
        """
        Verify if partition is to be included.

        Parameters
        ----------
        partdata: dict
            Partition data.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        skip_part = True
        self._logger.debug(partdata)
        # gen_tools.result_msg('skip: ')
        if 'ID_FS_TYPE' in partdata:
            self._logger.debug('Skip %s?' % partdata['ID_FS_TYPE'])
            if partdata['ID_FS_TYPE'] not in configdata.partition_to_skip:
                self._logger.debug('No skip')
                skip_part = False
            else:
                self._logger.debug('Skip')
        else:
            self._logger.debug('Skip anyway.')
        # gen_tools.pause_msg('partition %s' % skip_part)
        return skip_part

    def find_partition(self, uuidornameorlabel):
        """
        Identify a partition and its current mount point with respect to a
        UUID or LABEL or LVM2name.

        Parameters
        ----------
        uuidornameorlabel: str
            The UUID, LABEL or LVM2 name as specified in fstab.

        Returns
        -------
            tuple: The partition, the current mount point.
        """
        part, mount = None, None
        if 'UUID' in uuidornameorlabel:
            uuid_x = re.split('\\bUUID=\\b', uuidornameorlabel)[1]
            self._logger.debug('%s contains a UUID: %s'
                               % (uuidornameorlabel, uuid_x))
            for partition, partdata in self.img_info['partitions'].iteritems():
                if self.skip_partition(partdata):
                    self._logger.debug('Skipping %s' % partition)
                elif 'ID_FS_UUID' in partdata.keys():
                    if partdata['ID_FS_UUID'] == uuid_x:
                        part = partition
                        mount = partdata['mountpoint']
                        self._logger.debug('%s found in %s' % (uuid_x, partition))
                        break
                    else:
                        self._logger.debug('%s not in %s' % (uuid_x, partition))
                else:
                    self._logger.debug('%s : No ID_FS_UUID in partdata keys.'
                                       % partition)
            self._logger.debug('break..UUID')
        elif 'LABEL' in uuidornameorlabel:
            label_x = re.split('\\bLABEL=\\b', uuidornameorlabel)[1]
            self._logger.debug('%s contains a LABEL: %s'
                               % (uuidornameorlabel, label_x))
            for partition, partdata in self.img_info['partitions'].iteritems():
                if self.skip_partition(partdata):
                    self._logger.debug('Skipping %s' % partition)
                elif 'ID_FS_LABEL' in partdata.keys():
                    if partdata['ID_FS_LABEL'] == label_x:
                        part = partition
                        mount = partdata['mountpoint']
                        self._logger.debug('%s found in %s' % (label_x, partition))
                        break
                    else:
                        self._logger.debug('%s not in %s' % (label_x, partition))
                else:
                    self._logger.debug('%s: No ID_FS_LABEL in partdata keys.'
                                       % partition)
            self._logger.debug('break..LABEL')
        elif 'mapper' in uuidornameorlabel:
            lv_x = label_x = re.split('\\bmapper/\\b', uuidornameorlabel)
            self._logger.debug('%s contains a logical volune: %s'
                               % (uuidornameorlabel, lv_x))
            for partition, partdata in self.img_info['partitions'].iteritems():
                if self.skip_partition(partdata):
                    self._logger.debug('Skipping %s' % partition)
                elif partition == uuidornameorlabel:
                    part = partition
                    mount = partdata['mountpoint']
                    self._logger.debug('%s found in %s' % (lv_x, partition))
                    break
            self._logger.debug('break..LVM')
        else:
            self._logger.error('Unsupported fstab entry: %s' % uuidornameorlabel)
            part = 'na'
            mount = 'na'

        self._logger.debug('part ?? ')
        self._logger.debug(part)
        return part, mount

    def get_grub_data(self, rootdir):
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
            for grubroot in [rootdir + '/boot',
                             rootdir + '/grub',
                             rootdir + '/grub2']:
                self._logger.debug('Looking for %s in %s' % (grubname, grubroot))
                grubconf = migrate_utils.exec_find(grubname, grubroot)
                if grubconf is not None:
                    grub_cfg_path = grubconf
                    self._logger.debug('Found grub config file: %s' % grub_cfg_path)
                    break
                else:
                    self._logger.debug('No grub config file in %s' % grubroot)
        #
        # if no grub config file is found, need to quit.
        if grub_cfg_path is None:
            raise OciMigrateException('No grub config file found in %s' % self.fn)
        else:
            gen_tools.result_msg(msg='Grub config file: %s' % grub_cfg_path,
                                 result=True)
        #
        # investigate grub cfg path: contents of EFI/efi directory.
        if 'EFI' in grub_cfg_path.split('/'):
            self.img_info['boot_type'] = 'UEFI'
        else:
            self.img_info['boot_type'] = 'BIOS'
        # self._logger.debug('Image boot type is %s' % self.img_info[
        # 'boot_type'])
        gen_tools.result_msg(msg='Image boot type: %s' % self.img_info[
            'boot_type'])
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
            gen_tools.result_msg(msg='Found grub2 configuration file',
                                 result=True)
        else:
            gen_tools.result_msg(msg='Found grub configuration file',
                                 result=True)
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

    def get_os_release(self):
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
                        # fsline[0] != '#' ????
                        fstabdata.append(fsline.split())
                        gen_tools.result_msg(msg='%s' % fsline.split())
                    else:
                        self._logger.debug('skipping %s' % fsline)
        except Exception as e:
            self._logger.error('Problem reading %s: %s' % (fstabfile, str(e)))
        return fstabdata

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
            if self.img_info['boot_type'] in configdata.valid_boot_types:
                self._logger.debug('Boot type is %s, ok'
                                   % self.img_info['boot_type'])
                gen_tools.result_msg(msg='Boot type is %s, ok'
                                         % self.img_info['boot_type'],
                                     result=True)
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
                gen_tools.result_msg(msg='The image %s contains a valid MBR.'
                                         % self.img_info['img_name'],
                                     result=True)
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
                    gen_tools.result_msg(msg='The image %s is bootable'
                                             % self.img_info['img_name'],
                                         result=True)
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
                self._logger.debug('Fstabline: %s' % line)
                if 'UUID' in line[0]:
                    uuid_x = re.split('\\bUUID=\\b', line[0])[1]
                    for _, part in partitiondata.iteritems():
                        self._logger.debug('partition: %s' % part)
                        if 'ID_FS_UUID' in part:
                            if part['ID_FS_UUID'] == uuid_x:
                                part_pass = True
                                gen_tools.result_msg(
                                    msg='Found %s in partition table.'
                                        % uuid_x, result=True)
                                break
                elif 'LABEL' in line[0]:
                    label_x = re.split('\\bLABEL=\\b', line[0])[1]
                    for _, part in partitiondata.iteritems():
                        self._logger.debug('partition: %s' % part)
                        if 'ID_FS_LABEL' in part:
                            if part['ID_FS_LABEL'] == label_x:
                                part_pass = True
                                gen_tools.result_msg(
                                    msg='Found %s in partition table.'
                                        % label_x, result=True)
                                break
                elif 'mapper' in line[0]:
                    lv_x = re.split('\\bmapper/\\b', line[0])[1]
                    for part, _ in partitiondata.iteritems():
                        self._logger.debug('partition: %s' % part)
                        if lv_x in part:
                            part_pass = True
                            gen_tools.result_msg(
                                msg='Found %s in partition table.'
                                    % lv_x, result=True)
                            break
                elif '/dev/' in line[0]:
                    self._logger.critical('Device name %s in fstab are '
                                          'not supported.' % line[0])
                else:
                    part_pass = True
                    gen_tools.result_msg(msg='Unrecognised: %s, ignoring.'
                                         % line[0], result=True)

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
                                gen_tools.result_msg(
                                    msg='grub2 line ->%s<- specifies boot '
                                        'partition via UUID.' % l)
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
                                gen_tools.result_msg(
                                    msg='grub line ->%s<- specifies boot '
                                        'partition via UUID.' % l,
                                    result=True)
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
                    if vu in configdata.valid_os:
                        gen_tools.result_msg(msg='OS is a %s: valid' % v,
                                             result=True)
                        os_pass = True
                    else:
                        self._logger.error('->OS<- %s is not supported.' % v)
            if not os_pass:
                thispass = False
                failmsg += '\n  - OS %s is not supported' % os_name
        else:
            thispass = False
            failmsg += '\n  - OS release file not found.'

        return thispass, failmsg
