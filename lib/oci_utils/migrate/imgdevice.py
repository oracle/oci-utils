# oci-utils
#
# Copyright (c) 2019, 2022 Oracle and/or its affiliates. All rights reserved.
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
from glob import glob

from oci_utils.migrate import ProgressBar
from oci_utils.migrate import bytes_to_hex
from oci_utils.migrate import console_msg
from oci_utils.migrate import error_msg
from oci_utils.migrate import migrate_data
from oci_utils.migrate import migrate_tools
from oci_utils.migrate import pause_msg
from oci_utils.migrate import reconfigure_network
from oci_utils.migrate import result_msg
from oci_utils.migrate import system_tools
from oci_utils.migrate import terminal_dimension
from oci_utils.migrate.exception import OciMigrateException
from oci_utils.migrate.migrate_tools import get_config_data
from pprint import pformat

_logger = logging.getLogger('oci-utils.imgdevice')


class UpdateImage(threading.Thread):
    """ Class to update the virtual disk image in a chroot jail.
    """

    def __init__(self, vdiskdata, clouddata):
        """
        Initialisation of the UpdateImage object.

        Parameters:
        ----------
            vdiskdata: dict
                Information about the virtual image as described in the
                readme.txt, img_info.
            clouddata: dict
                cloudconfig_file: str
                    Full path of the cloud.cfg file
                default_clouduser: str
                    The user name for the oci user.
        """
        self._imgdata = vdiskdata
        self._clouddata = clouddata
        threading.Thread.__init__(self)

    def run(self):
        """Run the chroot operations
        """
        _logger.debug('Opening Thread.')
        self.chrootjail_ops()

    def wait4end(self):
        """ Stop
        """
        _logger.debug('Waiting for end.')
        self.join()

    def chrootjail_ops(self):
        """
        Create the chroot jail and execute the operations in the changed root.

        Returns
        -------
            No return value.
        """
        _logger.debug('__ chroot jail operations.')
        result_msg(msg='Creating chroot jail.')
        pause_msg('chroot jail entry', pause_flag='_OCI_CHROOT')
        os_type = self._imgdata['ostype']
        try:
            self._imgdata['pseudomountlist'] \
                = system_tools.mount_pseudo(self._imgdata['rootmnt'][1])
            result_msg(msg='Mounted proc, sys, dev')
            console_msg('Executing os specific operations, this might take a while.')
            #
            # create progressbar here
            _, nbcols = terminal_dimension()
            os_specific_ops = ProgressBar(nbcols, 0.2, progress_chars=['os specific operations'])
            os_specific_ops.start()
            #
            # chroot
            _logger.debug('New root: %s', self._imgdata['rootmnt'][1])
            rootfd, pathsave, dir2return2 = system_tools.enter_chroot(self._imgdata['rootmnt'][1])
            _logger.debug('Changed root to %s.', self._imgdata['rootmnt'][1])
            #
            # check current working directory
            current_wd = os.getcwd()
            _logger.debug('Current working directory is %s', current_wd)
            #
            # verify existence /etc/resolve.conf
            if os.path.isfile('/etc/resolv.conf'):
                _logger.debug('File /etc/resolv.conf found.')
            else:
                _logger.debug('No file /etc/resolv.conf found')
                if os.path.islink('/etc/resolv.conf'):
                    _logger.debug('/etc/result.conf is a symbolic link.')
                else:
                    _logger.debug('Really no /etc/resolv.conf.')
            #
            # chroot entry notification
            pause_msg('In chroot:', pause_flag='_OCI_CHROOT')
            chroot_notification = 'Please verify nameserver, proxy, update-repository configuration before ' \
                                  'proceeding the cloud-init package install.'
            #
            # os type specific operations
            pause_msg(chroot_notification, pause_flag='_OCI_CHROOT')
            os_operations = os_type.execute_os_specific_tasks()
            #
            # verifying the return values, only drop an error message on failure,
            # it is the operator responsibility to evaluate if this is blocking.
            for method_name, return_val in os_operations.items():
                if return_val:
                    _logger.debug('Method %s successfully executed.', method_name)
                else:
                    _logger.error('Failed to execute %s successfully.', method_name)
            #
            # set the default cloud user
            pause_msg('os specific operations finished, updating default user', pause_flag='_OCI_CHROOT')
            if migrate_tools.set_default_user(
                    self._clouddata['cloudconfig_file'],
                    self._clouddata['default_clouduser']):
                _logger.debug('Default cloud user updated.')
            else:
                _logger.error('   Failed to update default cloud user.')
            # placeholder: failing to update the cloud user name is probably not fatal.
            #    raise OciMigrateException(
            #        'Failed to update default cloud user.')
            #
            # execute ldconfig
            ldconf = system_tools.exec_ldconfig()
            if ldconf == 0:
                _logger.debug('ldconfig successfully executed.')
            else:
                _logger.error('Execution of ldconfig failed, the modified image might not be able to '
                              'execute cloud-init tasks successfully.')
            pause_msg('chroot jail end', pause_flag='_OCI_CHROOT')
        except Exception as e:
            _logger.critical('   *** ERROR *** Unable to perform image update operations: %s', str(e), exc_info=True)
        finally:
            system_tools.leave_chroot(rootfd, dir2return2)
            _logger.debug('Left chroot jail.')
            system_tools.unmount_pseudo(self._imgdata['pseudomountlist'])
            result_msg(msg='Unmounted proc, sys, dev.')
            if system_tools.is_thread_running(os_specific_ops):
                os_specific_ops.stop()
        time.sleep(1)
        result_msg(msg='Leaving chroot jail.')


class DeviceData():
    """
    Class to handle the data of device and partitions in an virtual disk
    image file. Contains methods shared by various image file types.
    """

    def __init__(self, filename):
        """
        Parameters:
        ----------
            Initialisation of the generic header.
            filename: str
                The full path of the virtual disk image file.
        """
        self._fn = filename
        self._devicename = None
        self.image_info = dict()
        self._mountpoints = list()
        _logger.debug('Image file name: %s', self._fn)

    def mount_img(self):
        """
        Loopback mount the image file on /dev/nbd.

        Returns
        -------
            str: mount point on success, None on failure, reraises an
            eventual exception.
        """
        _logger.debug('__ Entering mount_img')
        try:
            nbdpath = migrate_tools.mount_imgfn(self._fn)
            _logger.debug('%s successfully mounted', nbdpath)
            return nbdpath
        except Exception as e:
            _logger.critical('   %s', str(e))
            raise OciMigrateException('Failing:') from e

    @staticmethod
    def umount_img(nbd):
        """
        Unmount loopback mounted image file.

        Returns
        -------
            bool: True on success, False Otherwise.
        """
        _logger.debug('__ Entering unmount_img')
        try:
            if migrate_tools.unmount_imgfn(nbd):
                _logger.debug('%s successfully unmounted', nbd)
                return True

            _logger.error('   Failed to unmount %s', nbd, exc_info=True)
            return False
        except Exception as e:
            raise OciMigrateException('Failing:') from e

    @staticmethod
    def get_mbr(device):
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
        _logger.debug('__ Read the MBR.')
        try:
            with open(device, 'rb') as f:
                mbr = f.read(512)
            _logger.debug('%s mbr: %s', device, bytes_to_hex(mbr))
            return mbr
        except Exception as e:
            _logger.error('   Failed to read MBR on %s: %s', device, str(e))
            return None

    @staticmethod
    def get_partition_table(mbr):
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
        _logger.debug('__ Get the partition table from the MBR.')
        bootflag = '80'
        mbrok = False
        partitiontable = list()
        hexmbr = bytes_to_hex(mbr)
        mbrsig = hexmbr[-4:]
        if mbrsig.upper() == '55AA':
            mbrok = True
            _logger.debug('Is a valid MBR')
        else:
            _logger.critical('   Is not a valid MBR')
            return mbrok, partitiontable

        ind = 892
        for _ in range(0, 4):
            part = dict()
            partentry = hexmbr[ind:ind + 32]
            part['entry'] = partentry
            ind += 32
            #
            # active partition: find partition with bootflag
            _logger.debug('boot? : %s', partentry[0:2])
            if partentry[0:2] == bootflag:
                part['boot'] = True
            else:
                part['boot'] = False
            #
            # type
            typeflag = partentry[8:10].lower()
            _logger.debug('type? : %s', typeflag)
            partition_types = get_config_data('partition_types')
            if typeflag in partition_types:
                part['type'] = partition_types[typeflag]
            else:
                part['type'] = 'unknown'

            partitiontable.append(part)

        _logger.debug('Partition table: %s', partitiontable)
        return mbrok, partitiontable

    @staticmethod
    def get_partition_info(partition_name):
        """
        Collect information about partition.

        Parameters
        ----------
        partition_name: str
            The partition name.

        Returns
        -------
            dict: The information about the partition
        """
        #
        # blkid data
        _logger.debug('__ Collecting information on %s', partition_name)
        blkid_args = ['-po', 'udev']
        blkid_args.append(partition_name)
        _logger.debug('blkid %s', blkid_args)
        result_msg(msg='Investigating partition %s' % partition_name)
        part_info = dict()
        blkidres = system_tools.exec_blkid(blkid_args)
        if blkidres is None:
            raise OciMigrateException('Failed to run blkid %s' % blkidres)
        _logger.debug('%s output: blkid\n %s', blkid_args, blkidres.split())
        #
        # make dictionary
        for kv in blkidres.splitlines():
            kvs = kv.split('=')
            part_info[kvs[0]] = kvs[1]
        #
        # add supported entry
        if 'ID_FS_TYPE' in part_info:
            partition_type = part_info['ID_FS_TYPE']
            #
            # verify partition type is supported
            result_msg(msg='Partition type %s' % partition_type)
            if partition_type in get_config_data('filesystem_types'):
                _logger.debug('Partition %s contains filesystem %s', partition_name, partition_type)
                part_info['supported'] = True
                part_info['usage'] = 'standard'
            elif partition_type in get_config_data('logical_vol_types'):
                _logger.debug('Partition %s contains a logical volume %s', partition_name, partition_type)
                part_info['supported'] = True
                part_info['usage'] = 'standard'
            elif partition_type in get_config_data('partition_to_skip'):
                _logger.debug('Partition %s harmless: %s', partition_name, partition_type)
                part_info['supported'] = False
                part_info['usage'] = 'na'
                result_msg(msg='Partition type %s for %s is not supported but harmless, skipping.\n'
                               % (partition_name, partition_type))
            else:
                _logger.debug('Partition %s unusable: %s', partition_name, partition_type)
                part_info['supported'] = False
                part_info['usage'] = 'na'
                error_msg('Partition type %s for %s is not supported, quitting.\n' % (partition_type, partition_name))
                raise OciMigrateException('Partition type %s for %s is not recognised and may break the operation.'
                                          % (partition_type, partition_name))
        else:
            # raise OciMigrateException('FS type missing from partition '
            #                           'information %s' % partition_name)
            part_info['supported'] = False
            part_info['usage'] = 'na'
            _logger.debug('No partition type specified, skipping')
            result_msg(msg='No partition type found for %s, skipping.' % partition_name)
        #
        # get label, if any
        partition_label = system_tools.exec_lsblk(['-n', '-o', 'LABEL', partition_name])
        if len(partition_label.rstrip()) > 0:
            result_msg(msg='Partition label: %s' % partition_label)
            part_info['label'] = partition_label.rstrip()
        else:
            _logger.debug('No label on %s.', partition_name)
        #
        pause_msg('test partition info %s' % partition_name, pause_flag='_OCI_PART')
        return part_info

    def handle_image(self):
        """
        Process the image.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        _logger.debug('__ Process the image.')
        try:
            #
            # mount image.
            self._devicename = self.mount_img()
            #
            # collect the image data.
            image_date_result = self.get_image_data()
            #
            # mount filesystems.
            if not self.mount_filesystems():
                raise OciMigrateException('Failed to mount filesystems')
            _logger.debug('Mounting file systems succeeded.')
            pause_msg('file systems mounted', pause_flag='_OCI_MOUNT')
            #
            # collect os data.
            _ = self.collect_os_data()
            #
            # oracle cloud agent download, if appropriate; a failure of this
            # operation is not fatal.
            _ = migrate_tools.get_cloud_agent_if_relevant(
                self.image_info['rootmnt'][1],
                self.image_info['osinformation']['ID'],
                self.image_info['major_release'])
            #
            # pause here for test reasons..
            pause_msg('os data collected', pause_flag='_OCI_MOUNT')
            #
            # update the network configuration.
            nics, nicconfig = reconfigure_network.update_network_config(self.image_info['rootmnt'][1])
            if bool(nics):
                _logger.debug('Successfully upgraded the network configuration.')
            else:
                _logger.warning('   Failed to update network configuration or no configured network\n'
                                '   found. . Proceeding anyway but this could cause troubles at instance\n'
                                '   creation time.')
                result_msg(msg='   Failed to update network configuration or no configured network\n'
                               '   found. Proceeding anyway but this could cause troubles at instance\n'
                               '   creation time.', result=False)
                # raise OciMigrateException(
                #    'Failed to update network configuration.')
            #
            # pause here for test reasons..
            pause_msg('network reconfigured', pause_flag='_OCI_NETWORK')
            #
            # update the image.
            self.update_image()
            return True
        except Exception as e:
            _logger.debug('   Image %s handling failed: %s', self.image_info['img_name'], str(e), exc_info=True)
            _logger.critical('\n   Image %s handling failed: %s', self.image_info['img_name'], str(e))
            return False
        finally:
            _, nbcols = terminal_dimension()
            cleanup = ProgressBar(nbcols, 0.2, progress_chars=['cleaning up'])
            cleanup.start()
            #
            # unmount partitions from remount
            _logger.debug('Unmount partitions.')
            if self.unmount_partitions():
                _logger.debug('Successfully unmounted.')
            else:
                error_msg('Failed to release remounted filesystems, might prevent successful completions of %s.'
                          % sys.argv[0])
            #
            # unmount filesystems
            _logger.debug('Unmount filesystems.')
            for mnt in self._mountpoints:
                _logger.debug('--- %s', mnt)
                migrate_tools.unmount_part(mnt)
            #
            # release lvm
            if 'volume_groups' in self.image_info:
                _logger.debug('Release volume groups: %s', self.image_info['volume_groups'])
                migrate_tools.unmount_lvm2(self.image_info['volume_groups'])
            else:
                _logger.debug('No volume groups defined.')
            #
            # release device and module
            if self._devicename:
                _logger.debug('Releasing %s', str(self._devicename))
                self.umount_img(self._devicename)
                if system_tools.rm_nbd():
                    _logger.debug('Kernel module nbd removed.')
                else:
                    _logger.error('   Failed to remove kernel module nbd.')
            if system_tools.is_thread_running(cleanup):
                cleanup.stop()

    def get_image_data(self):
        """
        Get file system on the partition specified by device.

        Returns
        -------
            bool: True on success, raises an exception otherwise.
        """
        #
        # reading from the mounted image file
        _logger.debug('__ Collecting data on %s', self._devicename)
        try:
            #
            # Master Boot Record:
            img_mbr = self.get_mbr(self._devicename)
            if img_mbr is None:
                raise OciMigrateException('Failed to get MBR from device file %s' % self._devicename)

            self.image_info['mbr'] = {'bin': img_mbr, 'hex': system_tools.show_hex_dump(img_mbr)}
            result_msg(msg='Found MBR.', result=False)
            #
            # Partition Table from MBR:
            mbrok, parttable = self.get_partition_table(self.image_info['mbr']['bin'])
            if not mbrok:
                raise OciMigrateException('Failed to get partition table from MBR')

            self.image_info['mbr']['valid'] = mbrok
            self.image_info['mbr']['partition_table'] = parttable
            result_msg(msg='Found partition table.', result=False)
            #
            # Device data
            parted_data = system_tools.exec_parted(self._devicename)
            if parted_data is None:
                raise OciMigrateException('Failed to collect parted %s device data.' % self._devicename)

            self.image_info['parted'] = parted_data
            result_msg(msg='Got parted data')
            _logger.debug('partition data: %s', self.image_info['parted'])
            #
            # Partition info
            sfdisk_info = system_tools.exec_sfdisk(self._devicename)
            if sfdisk_info is None:
                raise OciMigrateException('Failed to collect sfdisk %s partition data.' % self._devicename)

            result_msg(msg='Got sfdisk info')
            self.image_info['partitions'] = sfdisk_info
            _logger.debug('Partition info: %s', sfdisk_info)
            _logger.debug('Partition info: %s', self.image_info['partitions'])
            for k, v in list(self.image_info['partitions'].items()):
                _logger.debug('%s - %s', k, v)
                v['usage'] = 'na'
                v['supported'] = False
            #
            # Partition data
            parttemplate = self._devicename + 'p*'
            _logger.debug('Partition %s : %s', parttemplate, glob(parttemplate))
            result_msg(msg='Partition data for device %s' % self._devicename)
            #
            #
            pause_msg('verify blkid..', pause_flag='_OCI_PART')
            for partname in glob(parttemplate):
                _logger.debug('Get info on %s', partname)
                self.image_info['partitions'][partname].update(self.get_partition_info(partname))
            return True
        except Exception as e:
            #
            # need to release mount of image file and exit
            _logger.critical('   Initial partition data collection failed: %s', str(e), exc_info=True, stack_info=True)
            raise OciMigrateException('Initial partition data collection failed:\n') from e

    def mount_filesystems(self):
        """
        Mount the file systems in partitons and logical volumes.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        _logger.debug('__ Mount the filesystems.')
        #
        # initialise logical volume structure
        self.image_info['volume_groups'] = dict()
        #
        # initialise list of mountpoints
        result_msg(msg='Mounting partitions.')
        #
        # loop through identified partitions, identify the type, mount it if
        # it is a standard partition hosting a supported filesystem; if a
        # partition contains a LVM2 physical volume, add the partition to the
        # lvm list for later use.
        success = True
        pause_msg(self.image_info['partitions'], pause_flag='_OCI_PART')
        for devname, devdetail in list(self.image_info['partitions'].items()):
            _logger.debug('Device: %s', devname)
            _logger.debug('Details:\n %s', devdetail)
            result_msg(msg='Partition %s' % devname)
            try:
                if 'ID_FS_TYPE' in devdetail:
                    if devdetail['ID_FS_TYPE'] in get_config_data('filesystem_types'):
                        _logger.debug('File system %s detected', devdetail['ID_FS_TYPE'])
                        fs_mount_point = migrate_tools.mount_partition(devname)
                        if fs_mount_point is not None:
                            result_msg(msg='Partition %s with file system %s mounted on %s.'
                                           % (devname, devdetail['ID_FS_TYPE'], fs_mount_point), result=False)
                            _logger.debug('%s mounted', devname)
                            devdetail['mountpoint'] = fs_mount_point
                            self._mountpoints.append(fs_mount_point)
                        else:
                            _logger.critical('   Failed to mount %s', devname)
                            success = False
                    elif devdetail['ID_FS_TYPE'] in get_config_data('logical_vol_types'):
                        _logger.debug('Logical volume %s detected', devdetail['ID_FS_TYPE'])
                        result_msg(msg='Logical volume %s' % devdetail['ID_FS_TYPE'], result=False)
                        volume_groups = migrate_tools.mount_lvm2(devname)
                        self.image_info['volume_groups'].update(volume_groups)
                    else:
                        _logger.debug('Skipping %s.', devdetail['ID_FS_TYPE'])
                        result_msg(msg='Skipping %s' % devdetail['ID_FS_TYPE'])
                else:
                    _logger.debug('%s does not exist or has unrecognised type', devname)
            except Exception as e:
                #
                # failed to mount a supported filesystem on a partition...
                # not quitting yet, trying to collect as much info a possible
                # in this stage.
                success = False
                _logger.critical('   Failed to mount partition %s: %s', devname, str(e))
        #
        # loop through the volume group list, identify the logical volumes
        # and mount them if they host a supported file system.
        for vg, lv in list(self.image_info['volume_groups'].items()):
            _logger.debug('volume group %s', vg)
            for part in lv:
                partname = '/dev/mapper/%s' % part[1]
                _logger.debug('Partition %s', partname)
                result_msg(msg='Partition: %s' % partname)
                #
                # for the sake of testing
                pause_msg('lv name test', pause_flag='_OCI_LVM')
                devdetail = self.get_partition_info(partname)
                try:
                    if 'ID_FS_TYPE' in devdetail:
                        if devdetail['ID_FS_TYPE'] in get_config_data('filesystem_types'):
                            _logger.debug('file system %s detected', devdetail['ID_FS_TYPE'])
                            fs_mount_point = migrate_tools.mount_partition(partname)
                            if fs_mount_point is not None:
                                result_msg(msg='Partition %s with file system %s mounted on %s.'
                                               % (partname, devdetail['ID_FS_TYPE'], fs_mount_point), result=False)
                                _logger.debug('%s mounted', partname)
                                devdetail['mountpoint'] = fs_mount_point
                                self._mountpoints.append(fs_mount_point)
                            else:
                                _logger.critical('   Failed to mount %s', partname)
                                success = False
                        else:
                            _logger.debug('%s does not exist or has unrecognised type', partname)
                    self.image_info['partitions'][partname] = devdetail
                except Exception as e:
                    success = False
                    _logger.critical('   Failed to mount logical volumes %s: %s', partname, str(e))
        return success

    def remount_partitions(self):
        """
        Remount the partitions identified in fstab on the identified root
        partition.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        _logger.debug('__ Remount the partions from fstab.')
        rootfs = self.image_info['rootmnt'][1]
        _logger.debug('Mounting on %s', rootfs)
        # Loop through partition list and create a sorted list of the
        # non-root partitions and mount those on the root partition.
        # The list is sorted to avoid overwriting subdirectory mounts like
        # /var, /var/log, /van/log/auto,.....
        mountlist = []
        for k, v in list(self.image_info['partitions'].items()):
            _logger.debug('remount?? %s on %s', v, k)
            if 'ID_FS_TYPE' not in v:
                _logger.debug('%s is not in use', k)
            else:
                if v['ID_FS_TYPE'] in get_config_data('filesystem_types'):
                    if v['usage'] not in ['root', 'na']:
                        mountlist.append((v['usage'], k, v['mountpoint']))
                    else:
                        _logger.debug('Partition %s not required.', k)
                else:
                    _logger.debug('Type %s not a mountable file system type.', v['ID_FS_TYPE'])
        mountlist.sort()
        _logger.debug('mountlist: %s', mountlist)

        for part in mountlist:
            _logger.debug('Is %s a candidate?', part[0])
            mountdir = rootfs + '/' + part[0]
            _logger.debug('Does mountpoint %s exist?', mountdir)
            if os.path.isdir(mountdir):
                _logger.debug('Mounting %s on %s.', part[1], mountdir)
                try:
                    resultmnt = migrate_tools.mount_partition(part[1], mountdir)
                    if resultmnt is not None:
                        _logger.debug('Mounted %s successfully.', resultmnt)
                        result_msg(msg='Mounted %s on %s.' % (part[1], mountdir), result=False)
                        self.image_info['remountlist'].append(resultmnt)
                    else:
                        _logger.error('   Failed to mount %s.', mountdir, exc_info=True)
                        raise OciMigrateException('Failed to mount %s' % mountdir)
                except Exception as e:
                    _logger.error('   Failed to mount %s: %s.', mountdir, str(e), exc_info=True)
                    # not sure if this should be fatal.
            else:
                _logger.error('   Something wrong, %s does not exist.', mountdir)

        return True

    def unmount_partitions(self):
        """
        Unmount partitions mounted earlier and listed in image info dict as
        'remountlist'.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        _logger.debug('__ Unmount the partitions.')
        ret = True
        if 'remountlist' in self.image_info:
            if len(self.image_info['remountlist']) <= 0:
                return ret
            #
            # sort inverse to unmount cleanly
            self.image_info['remountlist'].sort(reverse=True)
            for part in self.image_info['remountlist']:
                _logger.debug('Releasing %s', part)
                if system_tools.unmount_something(part):
                    _logger.debug('Successfully released %s.', part)
                else:
                    _logger.error('   Failed to release %s, might prevent clean termination.', part, exc_info=True)
                    ret = False
        else:
            _logger.debug('No remountlist.')
        return ret

    def collect_os_data(self):
        """
        Collect OS data relevant for the migration of the image to OCI and
        save it in the img_info dictionary.

        Returns
        -------
            bool: True on success, raise exception otherwise.
        """
        _logger.debug('__ Collect OS data.')
        self.image_info['remountlist'] = list()
        #
        # Collect the data
        oscollectmesg = ''
        try:
            #
            # import operation system type dependant modules
            osrelease = self.get_os_release()
            if bool(osrelease):
                self.image_info['osinformation'] = osrelease
                _logger.debug('OS type: %s', osrelease['ID'])
                migrate_data.os_version_id = osrelease['VERSION_ID']
                _logger.debug('OS version: %s', osrelease['VERSION_ID'])
                self.image_info['major_release'] = re.split('\\.', osrelease['VERSION_ID'])[0]
                _logger.debug('Major release: %s', self.image_info['major_release'])
            else:
                oscollectmesg += '\n  . Unable to collect OS information.'
                raise OciMigrateException('Failed to find OS release information')
            #
            # import os-type specific modules
            os_spec_mod = migrate_tools.find_os_specific(osrelease['ID'])
            _logger.debug('OS specification: %s', os_spec_mod)
            if os_spec_mod is None:
                oscollectmesg += '\n  . OS type %s is not recognised.' % osrelease['ID']
            else:
                self.image_info['ostype'] = importlib.import_module('oci_utils.migrate.os_types.' + os_spec_mod)
                _logger.debug('OS type: %s', self.image_info['ostype'])
                self.image_info['ostype'].os_banner()
            #
            pause_msg('root and boot', pause_flag='_OCI_MOUNT')
            #
            # root and boot
            root_partition, root_mount_point = self.identify_partitions()
            if root_partition is None:
                oscollectmesg += '\n  . Failed to locate root partition.'
            else:
                result_msg(msg='Root %s %s' % (root_partition, root_mount_point))
                self.image_info['rootmnt'] = [root_partition, root_mount_point]
                _logger.debug('root: %s', self.image_info['rootmnt'])
            bootpart, bootmount = self.get_partition('/boot')
            if bootpart is None:
                result_msg(msg='/boot is not on a separate partition or is missing. The latter case will '
                               'cause failure.', result=True)
            else:
                result_msg(msg='Boot %s %s' % (bootpart, bootmount))
            self.image_info['bootmnt'] = [bootpart, bootmount]
            _logger.debug('boot: %s', self.image_info['bootmnt'])
            #
            # remount image partitions on root partition
            if self.remount_partitions():
                _logger.debug('Essential partitions mounted.')
                pause_msg('Verify mounted partitions', pause_flag='_OCI_MOUNT')
            else:
                raise OciMigrateException(
                    'Failed to mount essential partitions.')
            #
            if oscollectmesg:
                _logger.debug('OS Collect message:\n%s', oscollectmesg)
                raise OciMigrateException(oscollectmesg)
            _logger.debug('OS data collected.')
            #
            # grub
            grub_data, kernel_version, kernel_list = self.get_grub_data(self.image_info['rootmnt'][1])
            self.image_info['grubdata'] = grub_data
            self.image_info['kernelversion'] = kernel_version
            self.image_info['kernellist'] = kernel_list
            #
        except Exception as e:
            _logger.critical('   Failed to collect os data: %s', str(e), exc_info=True)
            raise OciMigrateException('Failed to collect os data:') from e
        return True

    def update_image(self):
        """
        Prepare the image for migration by installing the cloud-init package.

        Returns
        -------
            No return value, raises an exception on failure
        """
        _logger.debug('__ Update the image.')
        try:
            cldata = dict()
            cldata['cloudconfig_file'] = get_config_data('cloudconfig_file')
            cldata['default_clouduser'] = get_config_data('default_clouduser')
            _logger.debug('Updating image.')
            updimg = UpdateImage(self.image_info, cldata)
            updimg.start()
            _logger.debug('Waiting for update to end.')
            updimg.wait4end()
        except Exception as e:
            _logger.error('   Failed: %s', str(e), exc_info=True)
            raise OciMigrateException('Failing:') from e
        finally:
            _logger.debug('NOOP')

    def get_partition(self, mnt):
        """
        Find the partition in the device data structure which has a usage
        specified in 'mnt'.

        Parameters:
        ----------
            mnt: str
                The usage as specified in the img_info.partitions info

        Returns
        -------
            tuple: partition, mountpoint on success, None otherwise.
        """
        _logger.debug('__ Get the partition from device data.')
        thepartitions = self.image_info['partitions']
        for k, v in list(thepartitions.items()):
            if 'usage' in v:
                if v['usage'] == mnt:
                    _logger.debug('Found %s in %s', mnt, v['mountpoint'])
                    return k, v['mountpoint']
            else:
                _logger.debug('%s has no usage entry, skipping.', k)
        _logger.debug('%s not found.', mnt)
        return None, None

    def identify_partitions(self):
        """
        Locate the root partition and collect relevant data; /etc/fstab is
        supposed to be on the root partition.
        Identify all partitions in the image.

        Returns
        -------
            tuple: (root partition, root mount point) on success,
            (None, None) otherwise
        """
        fs_tab_file = 'fstab'
        _logger.debug('__ Looking for root and boot partition in %s', self._mountpoints)
        root_partition, root_mount_point, bootpart, bootmount = None, None, None, None
        try:
            for mnt in self._mountpoints:
                etcdir = mnt + '/etc'
                _logger.debug('Looking in partition %s', mnt)
                fstab = migrate_tools.exec_search(fs_tab_file, rootdir=etcdir)
                if fstab is not None:
                    #
                    # found fstab, reading it
                    fstabdata = self.get_fstab(fstab)
                    self.image_info['fstab'] = fstabdata
                    for line in fstabdata:
                        _logger.debug('Checking %s', line)
                        if line[1] in get_config_data('partition_to_skip'):
                            _logger.debug('Skipping %s', line)
                        elif line[1] == '/':
                            _logger.debug('Root partition is %s.', line[0])
                            root_partition, root_mount_point = self.find_partition(line[0])
                            if (root_partition, root_mount_point) == ('na', 'na'):
                                _logger.critical('   Failed to locate root partition %s.', line[0])
                                raise OciMigrateException('Failed to locate root partition %s.' % line[0])
                            self.image_info['partitions'][root_partition]['usage'] = 'root'
                        else:
                            _logger.debug('Some other partition %s for %s.', line[0], line[1])
                            part, mount = self.find_partition(line[0])
                            if (part, mount) == ('na', 'na'):
                                _logger.debug('Partition %s not used or not present.', line[0])
                                raise OciMigrateException('Failed to locate a partition %s.' % line[0])
                            self.image_info['partitions'][part]['usage'] = line[1]
                        result_msg(msg='Identified partition %s' % line[1], result=True)
                    result_msg(msg='Root partition is mounted on %s.' % root_mount_point)
                    break
                _logger.debug('fstab not found in %s', etcdir)
        except Exception as e:
            _logger.critical('   Error in partition identification: %s', str(e))
            raise OciMigrateException('Error in partition identification:') from e
        return root_partition, root_mount_point

    @staticmethod
    def skip_partition(partdata):
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
        _logger.debug('__ Skip partition?.')
        skip_part = True
        _logger.debug(partdata)
        if 'ID_FS_TYPE' in partdata:
            _logger.debug('Skip %s?', partdata['ID_FS_TYPE'])
            if partdata['ID_FS_TYPE'] not in get_config_data('partition_to_skip'):
                _logger.debug('No skip')
                skip_part = False
            else:
                _logger.debug('Skip')
        else:
            _logger.debug('Skip anyway.')
        pause_msg('partition %s' % skip_part, pause_flag='_OCI_PART')
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
        def find_uuid_partition(uuid_part):
            """
            Search in the list of partitions the one with a specific uuid.

            Parameters
            ----------
            uuid_part: str
                The uuid.

            Returns
            -------
                tuple: The partition, the current mount point.
            """
            part_p = 'na'
            mount_p = 'na'
            for partition, partdata in list(self.image_info['partitions'].items()):
                if self.skip_partition(partdata):
                    _logger.debug('Skipping %s', partition)
                elif 'ID_FS_UUID' in list(partdata.keys()):
                    if partdata['ID_FS_UUID'] == uuid_part:
                        part_p = partition
                        mount_p = partdata['mountpoint']
                        _logger.debug('%s found in %s', uuid_part, partition)
                        break
                    _logger.debug('%s not in %s', uuid_part, partition)
                else:
                    _logger.debug('%s : No ID_FS_UUID in partdata keys.', partition)
            return part_p, mount_p

        def find_label_partition(label_part):
            """
            Search in the list of partitions the one with a specific label.

            Parameters
            ----------
            label_part : str
                The label.

            Returns
            -------
               tuple: The partition, the current mount point.
            """
            part_p = 'na'
            mount_p = 'na'
            for partition, partdata in list(self.image_info['partitions'].items()):
                if self.skip_partition(partdata):
                    _logger.debug('Skipping %s', partition)
                elif 'ID_FS_LABEL' in list(partdata.keys()):
                    if partdata['ID_FS_LABEL'] == label_part:
                        part_p = partition
                        mount_p = partdata['mountpoint']
                        _logger.debug('%s found in %s', label_part, partition)
                        break
                    _logger.debug('%s not in %s', label_part, partition)
                else:
                    _logger.debug('%s: No ID_FS_LABEL in partdata keys.', partition)
            return part_p, mount_p

        def find_mapper_partition(mapper_part):
            """
            Search in the list of partitions the one with a specific mapper name.

            Parameters
            ----------
            mapper_part : str
                The mapper id.

            Returns
            -------
                tuple: The partition, the current mount point.
            """
            part_p = 'na'
            mount_p = 'na'
            for partition, partdata in list(self.image_info['partitions'].items()):
                if self.skip_partition(partdata):
                    _logger.debug('Skipping %s', partition)
                elif partition == mapper_part:
                    part_p = partition
                    mount_p = partdata['mountpoint']
                    _logger.debug('%s found in %s', mapper_part, partition)
                    break
            return part_p, mount_p

        _logger.debug('__ Find partition and mount point for %s.', uuidornameorlabel)
        pause_msg(msg='Looking for partitions', pause_flag='_OCI_PART')
        part, mount = None, None
        if 'UUID' in uuidornameorlabel:
            pause_msg(msg='Found UUID', pause_flag='_OCI_PART')
            _logger.debug('UUID')
            uuid_x = re.split('\\bUUID=\\b', uuidornameorlabel)[1]
            _logger.debug('%s contains a UUID: %s', uuidornameorlabel, uuid_x)
            part, mount = find_uuid_partition(uuid_x)
            _logger.debug('UUID')
        elif '/dev/disk/by-uuid' in uuidornameorlabel:
            pause_msg(msg='Found /dev/disk/by-uuid', pause_flag='_OCI_PART')
            _logger.debug('/dev/disk/by-uuid')
            uuid_x = re.split('\\bdev/disk/by-uuid/\\b', uuidornameorlabel)[1]
            _logger.debug('%s contains a /dev/disk/by-uuid: %s', uuidornameorlabel, uuid_x)
            part, mount = find_uuid_partition(uuid_x)
            _logger.debug('/dev/disk/by-uuid')
        elif 'LABEL' in uuidornameorlabel:
            pause_msg(msg='Found LABEL', pause_flag='_OCI_PART')
            _logger.debug('LABEL')
            label_x = re.split('\\bLABEL=\\b', uuidornameorlabel)[1]
            _logger.debug('%s contains a LABEL: %s', uuidornameorlabel, label_x)
            part, mount = find_label_partition(label_x)
            _logger.debug('LABEL')
        elif 'mapper' in uuidornameorlabel:
            pause_msg(msg='Found mapper', pause_flag='_OCI_PART')
            _logger.debug('mapper')
            # lv_x = re.split('\\bmapper/\\b', uuidornameorlabel)
            lv_x = uuidornameorlabel
            _logger.debug('%s contains is a logical volume.', lv_x)
            part, mount = find_mapper_partition(lv_x)
            _logger.debug('LVM')
        else:
            pause_msg(msg='Found unsupported', pause_flag='_OCI_PART')
            _logger.warning('   Unsupported fstab entry: %s', uuidornameorlabel)
            part = 'na'
            mount = 'na'

        _logger.debug('part found: %s', part)
        pause_msg(msg='Looked for partitions', pause_flag='_OCI_PART')
        return part, mount

    def get_grub_data(self, loopdir):
        """
        Collect data related to boot and grub.

        Parameters:
        ----------
            loopdir: str
                Mountpoint of the root partition.

        Returns
        -------
            list: List with relevant data from the grub config file:
               boot type, BIOS or UEFI,
               boot instructions
        """
        _logger.debug('__ Retrieve grub data.')

        def find_grub_config_file():
            """
            Locate the grub configuration file.

            Returns
            -------
                str: full path of the grub configuration file, None if not found.
            """
            _logger.debug('__ Looking for grub config file.')
            grubconflist = ['grub.cfg', 'grub.conf']
            grub_path = None
            for grubname in grubconflist:
                for grubroot in [loopdir + '/boot', loopdir + '/grub', loopdir + '/grub2']:
                    _logger.debug('Looking for %s in %s', grubname, grubroot)
                    grubconf = migrate_tools.exec_search(grubname, rootdir=grubroot)
                    if grubconf is not None:
                        grub_path = grubconf
                        _logger.debug('Found grub config file: %s', grub_path)
                        break
                    _logger.debug('No grub config file in %s', grubroot)
            return grub_path

        def find_boot_loader_entries_dir():
            """
            Verify if the directory /boot/loader/entries exists and contains files.

            Returns
            -------
                str: the path of the boot loader entries.
            """
            _logger.debug('__ Looking for /boot/loader/entries')
            boot_loader_entries = os.path.join(loopdir, 'boot/loader/entries')
            if os.path.exists(boot_loader_entries):
                if os.listdir(boot_loader_entries):
                    return boot_loader_entries
            return None

        def find_grubenv_dir():
            """
            Verify if the grubenv file exists.

            Returns
            -------
                str: the path of the grubenv file.
            """
            _logger.debug('__ Looking for /boot/grub2/grubenv')
            grubenvpath = os.path.join(loopdir, 'boot/grub2/grubenv')
            if os.path.exists(grubenvpath):
                return grubenvpath
            return None

        def find_efi_boot_config():
            """
            Find out if the image is using BIOS or UEFI boot.

            Returns
            -------
                str: [BIOS|UEFI]
            """
            #
            # somewhat experimental, needs serious testing.
            _logger.debug('__ Looking for UEFI boot configuration.')
            boot_type = 'BIOS'
            efiboot = migrate_tools.exec_search('BOOT', rootdir=loopdir + '/boot', dirnames=True)
            self.image_info['boot_type'] = 'BIOS'
            if efiboot is not None:
                #
                # /boot/../BOOT exists
                if os.path.isdir(efiboot):
                    #
                    # and is not empty
                    if bool(os.listdir(efiboot)):
                        boot_type = 'UEFI'
                        self.image_info['boot_type'] = 'UEFI'
                    else:
                        #
                        # but is empty
                        _logger.debug('/boot/.../BOOT exists but is empty.')
            else:
                #
                # does not exists
                _logger.debug('Boot type is not UEFI.')
            return boot_type

        #
        # if no grub config file is found, this operation is doomed.
        grub_cfg_path = find_grub_config_file()
        if grub_cfg_path is None:
            raise OciMigrateException('No grub config file found in %s' % self._fn)
        result_msg(msg='Grub config file: %s' % grub_cfg_path, result=False)
        #
        # verify if a boot loader entries is present
        boot_loader_entries_path = find_boot_loader_entries_dir()
        grub_env_path = find_grubenv_dir()
        #
        # investigate boot type
        self.image_info['boot_type'] = find_efi_boot_config()
        result_msg(msg='Image boot type: %s' % self.image_info['boot_type'])
        #
        # get grub config contents
        grubdata = list()
        grub2 = False
        grubby = True if boot_loader_entries_path else False
        grubentry = dict()
        grubefi = dict()
        kernelversion = '0'
        kernellist = list()
        _logger.debug('Initialised grub structure')

        if not grubby:
            try:
                #
                # check for grub2 data
                mentry = False
                with open(grub_cfg_path, 'r') as f:
                    for ffsline in f:
                        fsline = ffsline.strip()
                        fsline_split = re.split('[ "]', fsline)
                        if bool(fsline.split()):
                            _logger.debug('%s', fsline)
                            if fsline_split[0] == 'menuentry':
                                mentry = True
                                grub2 = True
                                if grubentry:
                                    grubdata.append(grubentry)
                                grubentry = {'menuentry': [fsline]}
                                _logger.debug('grub line: %s', fsline)
                            elif fsline_split[0] == 'search':
                                if mentry:
                                    grubentry['menuentry'].append(fsline)
                                    _logger.debug('Grub line: %s', grubentry['menuentry'])
                                else:
                                    _logger.debug('Not a menuentry, skipping %s', fsline)
                            elif fsline_split[0] == 'set':
                                if 'default_kernelopts' in fsline_split[1]:
                                    grubefi = {'grubefi': [fsline]}
                                    _logger.debug('efi line: %s', fsline)
                            else:
                                _logger.debug('Skipping %s', fsline)
                if bool(grubentry):
                    grubdata.append(grubentry)
                if bool(grubefi):
                    grubdata.append(grubefi)
            except Exception as e:
                _logger.error('   Errors during reading %s: %s', grub_cfg_path, str(e))
                raise OciMigrateException('Errors during reading %s:' % grub_cfg_path) from e

        if grubby:
            _logger.debug('Found /boot/loader/entries')
            result_msg(msg='Found /boot/loader/entries directory.', result=False)
            #
            # find all kernels defined in loader entries directory.
            kernellist = system_tools.get_grubby_kernels(boot_loader_entries_path)
            _logger.debug('Kernels defined in boot laoder entries: %s', kernellist)
            if grub_env_path:
                kernelversion = system_tools.get_grubby_default_kernel(grub_env_path)
                _logger.debug('Default kernel: %s', kernelversion)
            kernelopts = ''
            try:
                # find kernel options
                with open(grub_cfg_path, 'r') as f:
                    for ffsline in f:
                        fsline = ffsline.strip()
                        fsline_split = re.split('[ "]', fsline)
                        if bool(fsline.split()):
                            if fsline_split[0] == 'set':
                                if 'kernelopts' in fsline_split[1]:
                                    kernelopts = ' '.join(fsline_split[1:])
                                    break
                for _, _, files in os.walk(boot_loader_entries_path):
                    for name in files:
                        with open(os.path.join(boot_loader_entries_path, name), 'r') as f:
                            for ffsline in f:
                                fsline = ffsline.strip()
                                if len(fsline) > 0:
                                    _logger.debug('%s', fsline)
                                    if fsline.split()[0] == 'title':
                                        if grubentry:
                                            grubdata.append(grubentry)
                                        grubentry = {'title': [fsline]}
                                        _logger.debug('grub line: %s', fsline)
                                    elif fsline.split()[0] == 'linux':
                                        grubentry['title'].append(fsline)
                                        _logger.debug('grub line: %s', grubentry['title'])
                                    else:
                                        _logger.debug('skipping %s', fsline)
                        if grubentry:
                            if kernelopts:
                                grubentry['title'].append(kernelopts)
                            grubdata.append(grubentry)

            except Exception as e:
                _logger.error('   Errors during reading %s: %s', boot_loader_entries_path, str(e))
                raise OciMigrateException('Errors during reading %s:' % boot_loader_entries_path) from e

        elif grub2:
            _logger.debug('Found grub2 configuration file.')
            result_msg(msg='Found grub2 configuration file.', result=False)
            #
            # find all kernels defined in grub(1) config file.
            kernellist = system_tools.get_grub2_kernels(grub_cfg_path)
            _logger.debug('Kernels defined in grub2 config: %s', kernellist)
        else:
            #
            # grub configuration
            result_msg(msg='Found grub configuration file', result=False)
            #
            # find default kernel in grub(1) config file.
            kernelversion = system_tools.get_grub_default_kernel(grub_cfg_path)
            _logger.debug('Default kernel %s', kernelversion)
            #
            # find all kernels defined in grub(1) config file.
            kernellist = system_tools.get_grub_kernels(grub_cfg_path)
            _logger.debug('Kernels defined in grub config: %s', kernellist)
            try:
                #
                # check for grub data
                with open(grub_cfg_path, 'r') as f:
                    for ffsline in f:
                        fsline = ffsline.strip()
                        if len(fsline.split()) > 0:
                            _logger.debug('%s', fsline)
                            if fsline.split()[0] == 'title':
                                if grubentry:
                                    grubdata.append(grubentry)
                                grubentry = {'title': [fsline]}
                                _logger.debug('grub line: %s', fsline)
                            elif fsline.split()[0] == 'kernel':
                                grubentry['title'].append(fsline)
                                _logger.debug('grub line: %s', grubentry['title'])
                            else:
                                _logger.debug('skipping %s', fsline)
                if grubentry:
                    grubdata.append(grubentry)
            except Exception as e:
                _logger.error('   Errors during reading %s: %s', grub_cfg_path, str(e))
                raise OciMigrateException('Errors during reading %s:' % grub_cfg_path) from e

        _logger.debug('grubdata:\n %s', pformat(grubdata, indent=4))
        _logger.debug('kernellist\n %s', pformat(kernellist, indent=4))
        _logger.debug('kernelversion\n %s', kernelversion)
        return grubdata, kernelversion, kernellist

    def get_os_release(self):
        """
        Collect information on the linux operating system and release.
        Currently is only able to handle linux type os.

        Returns
        -------
            dict: Dictionary containing the os and version data on success,
            empty dict otherwise.
        """
        _logger.debug('__ Collection os data, looking in %s', self._mountpoints)
        osdict = dict()
        #
        # hostnamectl is a systemd command, not available in OL/RHEL/CentOS 6
        _, nb_columns = terminal_dimension()
        osreleasewait = ProgressBar(nb_columns, 0.2, progress_chars=['search os release'])
        osreleasewait.start()
        try:
            for mnt in self._mountpoints:
                osdata = migrate_tools.exec_search('os-release', rootdir=mnt)
                if osdata is not None:
                    with open(osdata, 'r') as f:
                        osreleasedata = [line.strip() for line in f.read().splitlines() if '=' in line]
                    osdict = dict([re.sub(r'"', '', kv).split('=') for kv in osreleasedata])
                    break
                _logger.debug('os-release not found in %s', mnt)
        except Exception as e:
            _logger.error('   Failed to collect os data: %s', str(e), exc_info=True)
        finally:
            if system_tools.is_thread_running(osreleasewait):
                osreleasewait.stop()

        _logger.debug('os data: %s', osdict)
        return osdict

    @staticmethod
    def get_fstab(fstabfile):
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
        _logger.debug('__ Read fstabfile: %s', fstabfile)
        try:
            with open(fstabfile, 'r') as f:
                for fsline in f:
                    if '#' not in fsline and len(fsline.split()) > 5:
                        # fsline[0] != '#' ????
                        fstabdata.append(fsline.split())
                        result_msg(msg='%s' % fsline.split())
                    else:
                        _logger.debug('skipping %s', fsline)
        except Exception as e:
            _logger.error('   Problem reading %s: %s', fstabfile, str(e))
        return fstabdata

    def generic_prereq_check(self):
        """
        Verify the generic prequisites.
        Returns
        -------
            bool: True or False.
            str : The eventual fail message.
        """
        _logger.debug('__ Verify the generic prerequisites.')
        passed_requirement = True
        failmsg = ''
        #
        # BIOS/UEFI boot
        if 'boot_type' in self.image_info:
            if self.image_info['boot_type'] in get_config_data('valid_boot_types'):
                _logger.debug('Boot type is %s, ok', self.image_info['boot_type'])
                result_msg(msg='Boot type is %s, ok' % self.image_info['boot_type'], result=True)
            else:
                passed_requirement = False
                _logger.debug('Boot type %s is not a valid boot type. ', self.image_info['boot_type'])
                failmsg += '\n  - Boot type %s is not a valid boot type. ' % self.image_info['boot_type']
        else:
            passed_requirement = False
            failmsg += '\n  - Boot type not found.'
        #
        # MBR
        if 'mbr' in self.image_info:
            if self.image_info['mbr']['valid']:
                _logger.debug('The image %s contains a valid MBR.', self.image_info['img_name'])
                result_msg(msg='The image %s contains a valid MBR.' % self.image_info['img_name'], result=False)
            else:
                passed_requirement = False
                _logger.debug('The image %s does not contain a valid MBR.', self.image_info['img_name'])
                failmsg += '\n  - The image %s does not contain a valid MBR.' % self.image_info['img_name']
            #
            # 1 disk: considering only 1 image file, representing 1 virtual
            # disk, implictly.
            #
            # Bootable
            #   from MBR
            partitiontable = self.image_info['mbr']['partition_table']
            bootflag = False
            # for i in range(0, len(partitiontable)):
            for _, table in enumerate(partitiontable):
                # if partitiontable[i]['boot']:
                if table['boot']:
                    bootflag = True
                    _logger.debug('The image %s is bootable', self.image_info['img_name'])
                    result_msg(msg='The image %s is bootable' % self.image_info['img_name'], result=False)
            #
            # from parted
            # todo: better way of parsing the partition table.
            partition_list = self.image_info['parted']['Partition List']
            for part in partition_list:
                for props in part:
                    if 'boot' in props or 'bios_grub' in props:
                        _logger.debug('Bootflag found in %s', part)
                        bootflag = True
                        result_msg(msg='The image %s is bootable' % self.image_info['img_name'], result=False)
            #
            #
            if not bootflag:
                passed_requirement = False
                _logger.error('   The image %s is not bootable', self.image_info['img_name'])
                failmsg += '\n  - The image %s is not bootable.' % self.image_info['img_name']
        else:
            passed_requirement = False
            failmsg += '\n  - MBR not found.'
        #
        # Everything needed to boot in this image? Compairing fstab with
        # partition data.
        if 'fstab' in self.image_info:
            fstabdata = self.image_info['fstab']
            partitiondata = self.image_info['partitions']

            fstab_pass = True
            for line in fstabdata:
                part_pass = False
                _logger.debug('Fstabline: %s', line)
                if 'UUID' in line[0]:
                    uuid_x = re.split('\\bUUID=\\b', line[0])[1]
                    for _, part in list(partitiondata.items()):
                        _logger.debug('partition: %s', part)
                        if 'ID_FS_UUID' in part:
                            if part['ID_FS_UUID'] == uuid_x:
                                part_pass = True
                                result_msg(msg='Found %s in partition table.' % uuid_x, result=False)
                                break
                elif '/dev/disk/by-uuid' in line[0]:
                    uuid_x = re.split('\\bdev/disk/by-uuid/\\b', line[0])[1]
                    for _, part in list(partitiondata.items()):
                        _logger.debug('partition: %s', part)
                        if 'ID_FS_UUID' in part:
                            if part['ID_FS_UUID'] == uuid_x:
                                part_pass = True
                                result_msg(msg='Found %s in partition table.' % uuid_x, result=False)
                                break
                elif 'LABEL' in line[0]:
                    label_x = re.split('\\bLABEL=\\b', line[0])[1]
                    for _, part in list(partitiondata.items()):
                        _logger.debug('partition: %s', part)
                        if 'ID_FS_LABEL' in part:
                            if part['ID_FS_LABEL'] == label_x:
                                part_pass = True
                                result_msg(msg='Found %s in partition table.' % label_x, result=False)
                                break
                elif 'mapper' in line[0]:
                    lv_x = re.split('\\bmapper/\\b', line[0])[1]
                    for part, _ in list(partitiondata.items()):
                        _logger.debug('partition: %s', part)
                        if lv_x in part:
                            part_pass = True
                            result_msg(msg='Found %s in partition table.' % lv_x, result=False)
                            break
                elif '/dev/' in line[0]:
                    _logger.critical('   Device name %s in fstab are not supported.', line[0])
                else:
                    part_pass = True
                    result_msg(msg='Unrecognised: %s, ignoring.' % line[0], result=False)

                if not part_pass:
                    fstab_pass = False
                    break

            if not fstab_pass:
                passed_requirement = False
                failmsg += '\n  - fstab file refers to unsupported or unreachable partitions.'
        else:
            passed_requirement = False
            failmsg += '\n  - fstab file not found.'
        #
        # boot using LVM or UUID
        # todo: better way to parse grub data.
        if 'grubdata' in self.image_info:
            grubdata = self.image_info['grubdata']
            #
            # grub: 'root=UUID'
            # grub2: '--fs-uuid'
            # efi: 'default_kernelopts' & 'root=UUID'
            grub_fail = 0
            grub_l = 0
            _logger.debug('grubdata: %s', grubdata)
            for entry in grubdata:
                for key in entry:
                    for le in entry[key]:
                        l_split = re.split('[ "]', le)
                        if l_split[0] == 'search':
                            grub_l += 1
                            if '--fs-uuid' not in l_split:
                                _logger.error('   grub2 line ->%s<- does not specify boot partition via UUID.', le)
                                grub_fail += 1
                            else:
                                result_msg(
                                    msg='grub2 line ->%s<- specifies boot partition via UUID.' % le)
                        elif l_split[0] == 'kernel':
                            grub_l += 1
                            if len([a for a in l_split if any(b in a for b in ['root=UUID=', 'root=/dev/mapper/'])]) == 0:
                                _logger.debug('grub line ->%s<- does not specify boot partition via UUID nor LVM2.', le)
                                grub_fail += 1
                            else:
                                result_msg(msg='grub line ->%s<- specifies boot partition via UUID or LVM2.' % le,)
                        elif 'default_kernelopts' in l_split[1]:
                            grub_l += 1
                            if len([a for a in l_split if any(b in a for b in ['root=UUID=', 'root=/dev/mapper/'])]) == 0:
                                _logger.debug('grub line ->%s<- does not specify boot partition via UUID nor LVM2.', le)
                                grub_fail += 1
                            else:
                                result_msg(msg='grub line ->%s<- specifies boot partition via UUID or LVM2.' % le)
                        elif l_split[0] == 'kernelopts=':
                            grub_l += 1
                            if len([a for a in l_split if any(b in a for b in ['root=UUID=', 'root=/dev/mapper/'])]) == 0:
                                _logger.debug('grub line ->%s<- does not specify boot partition via UUID nor LVM2.', le)
                                grub_fail += 1
                            else:
                                result_msg(msg='grub line ->%s<- specifies boot partition via UUID or LVM2.' % le)
                        else:
                            _logger.debug('skipping %s', l_split)
            if grub_l == 0:
                passed_requirement = False
                failmsg += '\n  - No boot entry found in grub/grub2 config file.'
            elif grub_fail > 0:
                passed_requirement = False
                failmsg += '\n  - grub config file does not guarantee booting using UUID or LVM2.'
            else:
                _logger.debug('Grub config file ok.')
                result_msg(msg='Grub config file ok.', result=True)
        else:
            passed_requirement = False
            failmsg += '\n  - Grub config file not found.'
        #
        # OS
        if 'osinformation' in self.image_info:
            osdata = self.image_info['osinformation']
            os_pass = False
            os_name = 'notsupportedos'
            for k, v in list(osdata.items()):
                _logger.debug('%s %s', k, v)
                if k.upper() == 'NAME':
                    vu = v.upper().strip()
                    os_name = v
                    _logger.debug('OS name: %s', vu)
                    if vu in get_config_data('valid_os'):
                        result_msg(msg='OS is: %s: valid' % v, result=True)
                        os_pass = True
                    else:
                        _logger.error('   ->OS<- %s is not supported.', v)
            if not os_pass:
                passed_requirement = False
                failmsg += '\n  - OS %s is not supported' % os_name
        else:
            passed_requirement = False
            failmsg += '\n  - OS release file not found.'

        return passed_requirement, failmsg
