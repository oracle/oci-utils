# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
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

from oci_utils.migrate import bytes_to_hex, console_msg, pause_msg
from oci_utils.migrate import get_config_data
from oci_utils.migrate import migrate_tools
from oci_utils.migrate import migrate_utils
from oci_utils.migrate import reconfigure_network
from oci_utils.migrate.exception import OciMigrateException

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
        migrate_tools.result_msg(msg='Creating chroot jail.')
        pause_msg('chroot jail entry')
        os_type = self._imgdata['ostype']
        try:
            self._imgdata['pseudomountlist'] \
                = migrate_utils.mount_pseudo(self._imgdata['rootmnt'][1])
            migrate_tools.result_msg(msg='Mounted proc, sys, dev')
            console_msg(
                'Installing the cloud-init package, this might take a while.')
            #
            # create progressbar here
            _, clmns = os.popen('stty size', 'r').read().split()
            cloud_init_install = migrate_tools.ProgressBar(
                int(clmns), 0.2, progress_chars=['installing cloud-init'])
            cloud_init_install.start()
            #
            # chroot
            _logger.debug('New root: %s' % self._imgdata['rootmnt'][1])
            rootfd, pathsave, dir2return2 = migrate_utils.enter_chroot(
                self._imgdata['rootmnt'][1])
            _logger.debug('Changed root to %s.' % self._imgdata['rootmnt'][1])
            #
            # check current working directory
            current_wd = os.getcwd()
            _logger.debug('Current working directory is %s' % current_wd)
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
            # Install cloud-init
            pause_msg('In chroot:')
            pre_cloud_notification = 'Please verify nameserver, proxy, ' \
                                     'update-repository configuration before ' \
                                     'proceeding the cloud-init package ' \
                                     'install.'
            #
            # os type specific operations
            pause_msg(pre_cloud_notification)
            if os_type.install_cloud_init(
                    self._imgdata['osinformation']['VERSION_ID']):
                _logger.debug('Successfully installed cloud-init')
            else:
                _logger.critical(' Failed to install cloud init')
                raise OciMigrateException('Failed to install cloud init')
            #
            # Update cloud.cfg file with default user
            pause_msg('cloud-init installed, updating default user')
            if migrate_utils.set_default_user(
                    self._clouddata['cloudconfig_file'],
                    self._clouddata['default_clouduser']):
                _logger.debug('Default cloud user updated.')
            else:
                _logger.error('   Failed to update default cloud user.')
                raise OciMigrateException(
                    'Failed to update default cloud user.')
        except Exception as e:
            _logger.critical('  *** ERROR *** Unable to perform image update '
                             'operations: %s' % str(e), exc_info=True)
        finally:
            migrate_utils.leave_chroot(rootfd, dir2return2)
            _logger.debug('Left chroot jail.')
            migrate_utils.unmount_pseudo(self._imgdata['pseudomountlist'])
            migrate_tools.result_msg(msg='Unmounted proc, sys, dev.')
            if migrate_tools.isthreadrunning(cloud_init_install):
                cloud_init_install.stop()
        time.sleep(1)
        migrate_tools.result_msg(msg='Leaving chroot jail.')


class DeviceData(object):
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
        self._img_info = dict()
        self._mountpoints = list()
        _logger.debug('Image file name: %s' % self._fn)

    def mount_img(self):
        """
        Loopback mount the image file on /dev/nbd.

        Returns
        -------
            str: mount point on success, None on failure, reraises an
            eventual exception.
        """
        _logger.debug('Entering mount')
        try:
            nbdpath = migrate_utils.mount_imgfn(self._fn)
            _logger.debug('%s successfully mounted' % nbdpath)
            return nbdpath
        except Exception as e:
            _logger.critical('  %s' % str(e))
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
                _logger.debug('%s successfully unmounted' % nbd)
                return True
            else:
                _logger.error('   Failed to unmount %s' % nbd, exc_info=True)
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
        try:
            with open(device, 'rb') as f:
                mbr = f.read(512)
            _logger.debug('%s mbr: %s' % (device, bytes_to_hex(mbr)))
            return mbr
        except Exception as e:
            _logger.error('   Failed to read MBR on %s: %s' % (device, str(e)))
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
        hexmbr = bytes_to_hex(mbr)
        mbrsig = hexmbr[-4:]
        if mbrsig.upper() == '55AA':
            mbrok = True
            _logger.debug('Is a valid MBR')
        else:
            _logger.critical('  Is not a valid MBR')
            return mbrok, partitiontable

        ind = 892
        for i in range(0, 4):
            part = dict()
            partentry = hexmbr[ind:ind + 32]
            part['entry'] = partentry
            ind += 32
            #
            # active partition: find partition with bootflag
            _logger.debug('boot? : %s' % partentry[0:2])
            if partentry[0:2] == bootflag:
                part['boot'] = True
            else:
                part['boot'] = False
            #
            # type
            typeflag = partentry[8:10].lower()
            _logger.debug('type? : %s' % typeflag)
            partition_types = get_config_data('partition_types')
            if typeflag in partition_types:
                part['type'] = partition_types[typeflag]
            else:
                part['type'] = 'unknown'

            partitiontable.append(part)

        _logger.debug('Partition table: %s' % partitiontable)
        return mbrok, partitiontable

    def get_partition_info(self, partition_name):
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
        _logger.debug('Collecting information on %s' % partition_name)
        blkid_args = ['-po', 'udev']
        blkid_args.append(partition_name)
        _logger.debug('blkid %s' % blkid_args)
        migrate_tools.result_msg(
            msg='Investigating partition %s' % partition_name)
        part_info = dict()
        blkidres = migrate_utils.exec_blkid(blkid_args)
        if blkidres is None:
            raise OciMigrateException('Failed to run blkid %s' % blkidres)
        else:
            _logger.debug('%s output: blkid\n %s'
                          % (blkid_args, blkidres.split()))
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
            migrate_tools.result_msg(msg='Partition type %s' % partition_type)
            if partition_type in get_config_data('filesystem_types'):
                _logger.debug('Partition %s contains filesystem %s'
                              % (partition_name, partition_type))
                part_info['supported'] = True
                part_info['usage'] = 'standard'
            elif partition_type in get_config_data('logical_vol_types'):
                _logger.debug('Partition %s contains a logical volume %s'
                              % (partition_name, partition_type))
                part_info['supported'] = True
                part_info['usage'] = 'standard'
            elif partition_type in get_config_data('partition_to_skip'):
                _logger.debug('Partition %s harmless: %s'
                              % (partition_name, partition_type))
                part_info['supported'] = False
                part_info['usage'] = 'na'
                migrate_tools.result_msg(msg='Partition type %s for %s is not '
                                             'supported but harmless, '
                                             'skipping.\n'
                                             % (partition_name, partition_type))
            else:
                _logger.debug('Partition %s unusable: %s'
                              % (partition_name, partition_type))
                part_info['supported'] = False
                part_info['usage'] = 'na'
                migrate_tools.error_msg('Partition type %s for %s is not '
                                        'supported, quitting.\n'
                                        % (partition_type, partition_name))
                raise OciMigrateException('Partition type %s for %s is not '
                                          'recognised and may break the '
                                          'operation.'
                                          % (partition_type, partition_name))
        else:
            # raise OciMigrateException('FS type missing from partition '
            #                           'information %s' % partition_name)
            part_info['supported'] = False
            part_info['usage'] = 'na'
            _logger.debug('No partition type specified, skipping')
            migrate_tools.result_msg(
                msg='No partition type found for %s, skipping.'
                    % partition_name)
        #
        # get label, if any
        partition_label = migrate_utils.exec_lsblk(['-n', '-o', 'LABEL',
                                                    partition_name])
        if len(partition_label.rstrip()) > 0:
            migrate_tools.result_msg(
                msg='Partition label: %s' % partition_label)
            part_info['label'] = partition_label.rstrip()
        else:
            _logger.debug('No label on %s.' % partition_name)
        #
        pause_msg('test partition info')
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
            self._devicename = self.mount_img()
            #
            # collect the image data.
            image_date_result = self.get_image_data()
            #
            # mount filesystems.
            if not self.mount_filesystems():
                raise OciMigrateException('Failed to mount filesystems')
            else:
                _logger.debug('Mounting file systems succeeded.')
            pause_msg('file systems mounted')
            #
            # collect os data.
            _ = self.collect_os_data()
            #
            # pause here for test reasons..
            pause_msg('pausing here for test reasons')
            #
            # update the network configuration.
            if reconfigure_network.update_network_config(
                    self._img_info['rootmnt'][1]):
                _logger.debug(
                    'Successfully upgraded the network configuration.')
            else:
                _logger.error('   Failed to update network configuration.')
                raise OciMigrateException(
                    'Failed to update network configuration.')
            # pause here for test reasons..
            pause_msg('pausing here for test reasons')
            #
            # update the image.
            _ = self.update_image()
            #
            # just for the matter of completeness:
            # get the oci configuration.
            ociconfig = migrate_utils.get_oci_config()
            self._img_info['oci_config'] = ociconfig
            return True
        except Exception as e:
            _logger.critical('  Image %s handling failed: %s'
                             % (self._img_info['img_name'], str(e)),
                             exc_info=False)
            return False
        finally:
            _, clmns = os.popen('stty size', 'r').read().split()
            cleanup = migrate_tools.ProgressBar(int(clmns), 0.2,
                                                progress_chars=['cleaning up'])
            cleanup.start()
            #
            # unmount partitions from remount
            _logger.debug('Unmount partitions.')
            if self.unmount_partitions():
                _logger.debug('Successfully unmounted.')
            else:
                migrate_tools.error_msg('Failed to release remounted '
                                        'filesystems, might prevent successful '
                                        'completions of %s.' % sys.argv[0])
            #
            # unmount filesystems
            _logger.debug('Unmount filesystems.')
            for mnt in self._mountpoints:
                _logger.debug('--- %s' % mnt)
                migrate_utils.unmount_part(mnt)
            #
            # release lvm
            _logger.debug('release volume groups')
            if 'volume_groups' in self._img_info:
                migrate_utils.unmount_lvm2(self._img_info['volume_groups'])
            else:
                _logger.debug('No volume groups defined.')
            #
            # release device and module
            if self._devicename:
                _logger.debug('Releasing %s' % str(self._devicename))
                self.umount_img(self._devicename)
                if migrate_utils.rm_nbd():
                    _logger.debug('Kernel module nbd removed.')
                else:
                    _logger.error('   Failed to remove kernel module nbd.')
            if migrate_tools.isthreadrunning(cleanup):
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
        _logger.debug('Collecting data on %s' % self._devicename)
        try:
            #
            # Master Boot Record:
            img_mbr = self.get_mbr(self._devicename)
            if img_mbr is None:
                raise OciMigrateException('Failed to get MBR from '
                                          'device file %s' % self._devicename)
            else:
                self._img_info['mbr'] = \
                    {'bin': img_mbr,
                     'hex': migrate_utils.show_hex_dump(img_mbr)}
                migrate_tools.result_msg(msg='Found MBR.', result=True)
            #
            # Partition Table from MBR:
            mbrok, parttable = self.get_partition_table(
                self._img_info['mbr']['bin'])
            if not mbrok:
                raise OciMigrateException(
                    'Failed to get partition table from MBR')
            else:
                self._img_info['mbr']['valid'] = mbrok
                self._img_info['mbr']['partition_table'] = parttable
                migrate_tools.result_msg(msg='Found partition table.',
                                         result=True)
            #
            # Device data
            parted_data = migrate_utils.exec_parted(self._devicename)
            if parted_data is None:
                raise OciMigrateException('Failed to collect parted %s '
                                          'device data.' % self._devicename)
            else:
                self._img_info['parted'] = parted_data
                migrate_tools.result_msg(msg='Got parted data')
                _logger.debug('partition data: %s'
                              % self._img_info['parted'])
            #
            # Partition info
            sfdisk_info = migrate_utils.exec_sfdisk(self._devicename)
            if sfdisk_info is None:
                raise OciMigrateException('Failed to collect sfdisk %s '
                                          'partition data.' % self._devicename)
            else:
                migrate_tools.result_msg(msg='Got sfdisk info')
                self._img_info['partitions'] = sfdisk_info
                _logger.debug('Partition info: %s' % sfdisk_info)
                _logger.debug('Partition info: %s'
                              % self._img_info['partitions'])
                for k, v in list(self._img_info['partitions'].items()):
                    _logger.debug('%s - %s' % (k, v))
                    v['usage'] = 'na'
                    v['supported'] = False
            #
            # Partition data
            parttemplate = self._devicename + 'p*'
            _logger.debug('Partition %s : %s'
                          % (parttemplate, glob(parttemplate)))
            migrate_tools.result_msg(msg='Partition data for device %s'
                                         % self._devicename)
            #
            # testing purposes
            pause_msg('verify blkid..')
            for partname in glob(parttemplate):
                _logger.debug('Get info on %s' % partname)
                self._img_info['partitions'][partname].update(
                    self.get_partition_info(partname))
            return True
        except Exception as e:
            #
            # need to release mount of image file and exit
            _logger.critical('  Initial partition data collection '
                             'failed: %s' % str(e), exc_info=True)
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
        self._img_info['volume_groups'] = dict()
        #
        # initialise list of mountpoints
        migrate_tools.result_msg(msg='Mounting partitions.')
        #
        # loop through identified partitions, identify the type, mount it if
        # it is a standard partition hosting a supported filesystem; if a
        # partition contains a LVM2 physical volume, add the partition to the
        # lvm list for later use.
        success = True
        pause_msg(self._img_info['partitions'])
        for devname, devdetail in list(self._img_info['partitions'].items()):
            _logger.debug('Device: %s' % devname)
            _logger.debug('Details:\n %s' % devdetail)
            migrate_tools.result_msg(msg='Partition %s' % devname)
            try:
                if 'ID_FS_TYPE' in devdetail:
                    if devdetail['ID_FS_TYPE'] in get_config_data(
                            'filesystem_types'):
                        _logger.debug('File system %s detected'
                                      % devdetail['ID_FS_TYPE'])
                        fs_mount_point = migrate_utils.mount_partition(devname)
                        if fs_mount_point is not None:
                            migrate_tools.result_msg(
                                msg='Partition %s with file '
                                    'system %s mounted on %s.'
                                    % (devname,
                                       devdetail['ID_FS_TYPE'],
                                       fs_mount_point),
                                result=True)
                            _logger.debug('%s mounted' % devname)
                            devdetail['mountpoint'] = fs_mount_point
                            self._mountpoints.append(fs_mount_point)
                        else:
                            _logger.critical('  Failed to mount %s'
                                             % devname)
                            success = False
                    elif devdetail['ID_FS_TYPE'] in get_config_data(
                            'logical_vol_types'):
                        _logger.debug('Logical volume %s detected'
                                      % devdetail['ID_FS_TYPE'])
                        migrate_tools.result_msg(msg='Logical volume %s'
                                                     % devdetail['ID_FS_TYPE'],
                                                 result=True)
                        volume_groups = migrate_utils.mount_lvm2(devname)
                        self._img_info['volume_groups'].update(volume_groups)
                    else:
                        _logger.debug('Skipping %s.' % devdetail['ID_FS_TYPE'])
                        migrate_tools.result_msg(msg='Skipping %s'
                                                     % devdetail['ID_FS_TYPE'])
                else:
                    _logger.debug('%s does not exist or has '
                                  'unrecognised type' % devname)
            except Exception as e:
                #
                # failed to mount a supported filesystem on a partition...
                # not quitting yet, trying to collect as much info a possible
                # in this stage.
                success = False
                _logger.critical('  Failed to mount partition %s: %s'
                                 % (devname, str(e)))
        #
        # loop through the volume group list, identify the logical volumes
        # and mount them if they host a supported file system.
        for vg, lv in list(self._img_info['volume_groups'].items()):
            _logger.debug('volume group %s' % vg)
            for part in lv:
                partname = '/dev/mapper/%s' % part[1]
                _logger.debug('Partition %s' % partname)
                migrate_tools.result_msg(msg='Partition: %s' % partname)
                #
                # for the sake of testing
                pause_msg('lv name test')
                devdetail = self.get_partition_info(partname)
                try:
                    if 'ID_FS_TYPE' in devdetail:
                        if devdetail['ID_FS_TYPE'] in get_config_data(
                                'filesystem_types'):
                            _logger.debug('file system %s detected'
                                          % devdetail['ID_FS_TYPE'])
                            fs_mount_point = migrate_utils.mount_partition(
                                partname)
                            if fs_mount_point is not None:
                                migrate_tools.result_msg(
                                    msg='Partition %s with file system %s '
                                        'mounted on %s.'
                                        % (partname, devdetail['ID_FS_TYPE'],
                                           fs_mount_point), result=True)
                                _logger.debug('%s mounted' % partname)
                                devdetail['mountpoint'] = fs_mount_point
                                self._mountpoints.append(fs_mount_point)
                            else:
                                _logger.critical('  Failed to mount %s'
                                                 % partname)
                                success = False
                        else:
                            _logger.debug('%s does not exist or has '
                                          'unrecognised type' % partname)
                    self._img_info['partitions'][partname] = devdetail
                except Exception as e:
                    success = False
                    _logger.critical('  Failed to mount logical '
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
        # self._img_info['remountlist'] = []
        rootfs = self._img_info['rootmnt'][1]
        _logger.debug('Mounting on %s' % rootfs)
        # Loop through partition list and create a sorted list of the
        # non-root partitions and mount those on the root partition.
        # The list is sorted to avoid overwriting subdirectory mounts like
        # /var, /var/log, /van/log/auto,.....
        mountlist = []
        for k, v in list(self._img_info['partitions'].items()):
            _logger.debug('remount?? %s' % k)
            _logger.debug('remount?? %s' % v)
            if 'ID_FS_TYPE' not in v:
                _logger.debug('%s is not in use' % k)
            else:
                if v['ID_FS_TYPE'] in get_config_data('filesystem_types'):
                    if v['usage'] not in ['root', 'na']:
                        mountlist.append((v['usage'], k, v['mountpoint']))
                    else:
                        _logger.debug('Partition %s not required.' % k)
                else:
                    _logger.debug('Type %s not a mountable file '
                                  'system type.' % v['ID_FS_TYPE'])
        mountlist.sort()
        _logger.debug('mountlist: %s' % mountlist)

        for part in mountlist:
            _logger.debug('Is %s a candidate?' % part[0])
            mountdir = rootfs + '/' + part[0]
            _logger.debug('Does mountpoint %s exist?' % mountdir)
            if os.path.isdir(mountdir):
                _logger.debug('Mounting %s on %s.' % (part[1], mountdir))
                try:
                    resultmnt = migrate_utils.mount_partition(part[1], mountdir)
                    if resultmnt is not None:
                        _logger.debug('Mounted %s successfully.' % resultmnt)
                        migrate_tools.result_msg(msg='Mounted %s on %s.'
                                                     % (part[1], mountdir),
                                                 result=True)
                        self._img_info['remountlist'].append(resultmnt)
                    else:
                        _logger.error('   Failed to mount %s.' % mountdir,
                                      exc_info=True)
                        raise OciMigrateException('Failed to mount %s'
                                                  % mountdir)
                except Exception as e:
                    _logger.error('   Failed to mount %s: %s.'
                                  % (mountdir, str(e)), exc_info=True)
                    # not sure where to go from here
            else:
                _logger.error('   Something wrong, %s does not exist.' %
                              mountdir)

        return True

    def unmount_partitions(self):
        """
        Unmount partitions mounted earlier and listed in image info dict as
        'remountlist'.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        ret = True
        if 'remountlist' in self._img_info:
            if len(self._img_info['remountlist']) <= 0:
                return ret

            self._img_info['remountlist'].sort()
            for part in self._img_info['remountlist']:
                _logger.debug('Releasing %s' % part)
                if migrate_utils.unmount_something(part):
                    _logger.debug('Successfully released %s.' % part)
                else:
                    _logger.error('   Failed to release %s, might prevent '
                                  'clean termination.' % part,
                                  exc_info=True)
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
        self._img_info['remountlist'] = list()
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
                self._img_info['osinformation'] = osrelease
                _logger.debug('OS type: %s' % osrelease['ID'])
            #
            # import os-type specific modules
            os_spec_mod = migrate_utils.find_os_specific(osrelease['ID'])
            _logger.debug('OS specification: %s' % os_spec_mod)
            if os_spec_mod is None:
                oscollectmesg += '\n  . OS type %s is not recognised.' \
                                 % osrelease['ID']
            else:
                self._img_info['ostype'] = \
                    importlib.import_module('oci_utils.migrate.' + os_spec_mod)
                _logger.debug('OS type: %s' % self._img_info['ostype'])
                self._img_info['ostype'].os_banner()
            #
            pause_msg('root and boot')
            #
            # root and boot
            root_partition, root_mount_point = self.identify_partitions()
            if root_partition is None:
                oscollectmesg += '\n  . Failed to locate root partition.'
            else:
                migrate_tools.result_msg(
                    msg='Root %s %s' % (root_partition, root_mount_point))
                self._img_info['rootmnt'] = [root_partition, root_mount_point]
                _logger.debug('root: %s' % self._img_info['rootmnt'])
            bootpart, bootmount = self.get_partition('/boot')
            if bootpart is None:
                migrate_tools.result_msg(
                    msg='/boot is not on a separate partition '
                        'or is missing. The latter case which '
                        'will cause failure.', result=True)
            else:
                migrate_tools.result_msg(
                    msg='Boot %s %s' % (bootpart, bootmount))
            self._img_info['bootmnt'] = [bootpart, bootmount]
            _logger.debug('boot: %s' % self._img_info['bootmnt'])
            #
            # remount image partitions on root partition
            if self.remount_partitions():
                _logger.debug('Essential partitions mounted.')
                pause_msg('Verify mounted partitions')
            else:
                raise OciMigrateException(
                    'Failed to mount essential partitions.')
            #
            if oscollectmesg:
                raise OciMigrateException(oscollectmesg)
            else:
                _logger.debug('OS data collected.')
            #
            # grub
            self._img_info['grubdata'] = self.get_grub_data(
                self._img_info['rootmnt'][1])
            #
        except Exception as e:
            _logger.critical('  Failed to collect os data: %s' % str(e),
                             exc_info=True)
            raise OciMigrateException('Failed to collect os data: %s' % str(e))
        return True

    def update_image(self):
        """
        Prepare the image for migration by installing the cloud-init package.

        Returns
        -------
            No return value, raises an exception on failure
        """
        try:
            cldata = dict()
            cldata['cloudconfig_file'] = get_config_data('cloudconfig_file')
            cldata['default_clouduser'] = get_config_data('default_clouduser')
            _logger.debug('Updating image.')
            updimg = UpdateImage(self._img_info, cldata)
            updimg.start()
            _logger.debug('Waiting for update to end.')
            updimg.wait4end()
        except Exception as e:
            _logger.error('   Failed: %s' % str(e), exc_info=True)
            raise OciMigrateException(str(e))
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
        thepartitions = self._img_info['partitions']
        for k, v in list(thepartitions.items()):
            if 'usage' in v:
                if v['usage'] == mnt:
                    _logger.debug('Found %s in %s' % (mnt, v['mountpoint']))
                    return k, v['mountpoint']
            else:
                _logger.debug('%s has no usage entry, skipping.' % k)
        _logger.debug('%s not found.' % mnt)
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
        fs_tab_file = 'fstab'
        _logger.debug('Looking for root and boot partition in %s'
                      % self._mountpoints)
        root_partition, root_mount_point, bootpart, bootmount = None, None, None, None
        try:
            for mnt in self._mountpoints:
                etcdir = mnt + '/etc'
                _logger.debug('Looking in partition %s' % mnt)
                fstab = migrate_utils.exec_search(fs_tab_file, rootdir=etcdir)
                if fstab is not None:
                    #
                    # found fstab, reading it
                    # self._img_info['fstab'] = self.get_fstab()
                    fstabdata = self.get_fstab(fstab)
                    self._img_info['fstab'] = fstabdata
                    for line in fstabdata:
                        _logger.debug('Checking %s' % line)
                        if line[1] in get_config_data('partition_to_skip'):
                            _logger.debug('Skipping %s' % line)
                        elif line[1] == '/':
                            _logger.debug('Root partition is %s.' % line[0])
                            root_partition, root_mount_point = self.find_partition(line[0])
                            if (root_partition, root_mount_point) == (None, None):
                                _logger.critical(
                                    '  Failed to locate root partition %s.' %
                                    line[0])
                                raise OciMigrateException(
                                    'Failed to locate root partition %s.' %
                                    line[0])
                            else:
                                self._img_info['partitions'][root_partition][
                                    'usage'] \
                                    = 'root'
                        else:
                            _logger.debug('Some other partition %s for %s.'
                                          % (line[0], line[1]))
                            part, mount = self.find_partition(line[0])
                            if (part, mount) == (None, None):
                                _logger.debug(
                                    'Partition %s not used or not present.'
                                    % line[0])
                                raise OciMigrateException(
                                    'Failed to locate a partition %s.'
                                    % line[0])
                            else:
                                self._img_info['partitions'][part]['usage'] = line[1]
                        migrate_tools.result_msg(msg='Identified partition %s'
                                                     % line[1], result=True)
                    migrate_tools.result_msg(
                        msg='Root partition is mounted on %s.'
                            % root_mount_point)
                    break
                else:
                    _logger.debug('fstab not found in %s' % etcdir)
        except Exception as e:
            _logger.critical('  Error in partition identification: %s'
                             % str(e))
            raise OciMigrateException('Error in partition identification: %s'
                                      % str(e))
        return root_partition, root_mount_point

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
        _logger.debug(partdata)
        # migrate_tools.result_msg('skip: ')
        if 'ID_FS_TYPE' in partdata:
            _logger.debug('Skip %s?' % partdata['ID_FS_TYPE'])
            if partdata['ID_FS_TYPE'] not in get_config_data(
                    'partition_to_skip'):
                _logger.debug('No skip')
                skip_part = False
            else:
                _logger.debug('Skip')
        else:
            _logger.debug('Skip anyway.')
        pause_msg('partition %s' % skip_part)
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
            _logger.debug('%s contains a UUID: %s'
                          % (uuidornameorlabel, uuid_x))
            for partition, partdata in list(
                    self._img_info['partitions'].items()):
                if self.skip_partition(partdata):
                    _logger.debug('Skipping %s' % partition)
                elif 'ID_FS_UUID' in list(partdata.keys()):
                    if partdata['ID_FS_UUID'] == uuid_x:
                        part = partition
                        mount = partdata['mountpoint']
                        _logger.debug('%s found in %s' % (uuid_x, partition))
                        break
                    else:
                        _logger.debug('%s not in %s' % (uuid_x, partition))
                else:
                    _logger.debug('%s : No ID_FS_UUID in partdata keys.'
                                  % partition)
            _logger.debug('break..UUID')
        elif 'LABEL' in uuidornameorlabel:
            label_x = re.split('\\bLABEL=\\b', uuidornameorlabel)[1]
            _logger.debug('%s contains a LABEL: %s'
                          % (uuidornameorlabel, label_x))
            for partition, partdata in list(
                    self._img_info['partitions'].items()):
                if self.skip_partition(partdata):
                    _logger.debug('Skipping %s' % partition)
                elif 'ID_FS_LABEL' in list(partdata.keys()):
                    if partdata['ID_FS_LABEL'] == label_x:
                        part = partition
                        mount = partdata['mountpoint']
                        _logger.debug('%s found in %s' % (label_x, partition))
                        break
                    else:
                        _logger.debug('%s not in %s' % (label_x, partition))
                else:
                    _logger.debug('%s: No ID_FS_LABEL in partdata keys.'
                                  % partition)
            _logger.debug('break..LABEL')
        elif 'mapper' in uuidornameorlabel:
            lv_x = re.split('\\bmapper/\\b', uuidornameorlabel)
            _logger.debug('%s contains a logical volune: %s'
                          % (uuidornameorlabel, lv_x))
            for partition, partdata in list(
                    self._img_info['partitions'].items()):
                if self.skip_partition(partdata):
                    _logger.debug('Skipping %s' % partition)
                elif partition == uuidornameorlabel:
                    part = partition
                    mount = partdata['mountpoint']
                    _logger.debug('%s found in %s' % (lv_x, partition))
                    break
            _logger.debug('break..LVM')
        else:
            _logger.error('   Unsupported fstab entry: %s' % uuidornameorlabel)
            part = 'na'
            mount = 'na'

        _logger.debug('part found: %s' % part)
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
        #
        # find grub.cfg, grub.conf, ...
        grubconflist = ['grub.cfg', 'grub.conf']
        grub_cfg_path = None
        for grubname in grubconflist:
            for grubroot in [loopdir + '/boot',
                             loopdir + '/grub',
                             loopdir + '/grub2']:
                _logger.debug('Looking for %s in %s' % (grubname, grubroot))
                grubconf = migrate_utils.exec_search(grubname, rootdir=grubroot)
                if grubconf is not None:
                    grub_cfg_path = grubconf
                    _logger.debug('Found grub config file: %s' % grub_cfg_path)
                    break
                else:
                    _logger.debug('No grub config file in %s' % grubroot)
        #
        # if no grub config file is found, need to quit.
        if grub_cfg_path is None:
            raise OciMigrateException(
                'No grub config file found in %s' % self._fn)
        else:
            migrate_tools.result_msg(msg='Grub config file: %s' % grub_cfg_path,
                                     result=True)
        #
        # investigate /boot for EFI/efi directory.
        # if 'EFI' in grub_cfg_path.split('/'):
        efiboot = migrate_utils.exec_search('EFI',
                                            rootdir=loopdir + '/boot',
                                            dirnames=True)
        if efiboot is not None:
            self._img_info['boot_type'] = 'UEFI'
        else:
            self._img_info['boot_type'] = 'BIOS'
        migrate_tools.result_msg(msg='Image boot type: %s' % self._img_info[
            'boot_type'])
        #
        # get grub config contents
        grubdata = list()
        grub2 = False
        grubentry = dict()
        _logger.debug('Initialised grub structure')
        try:
            #
            # check for grub2 data
            mentry = False
            with open(grub_cfg_path, 'r') as f:
                for ffsline in f:
                    fsline = ffsline.strip()
                    if len(fsline.split()) > 0:
                        _logger.debug('%s' % fsline)
                        if fsline.split()[0] == 'menuentry':
                            mentry = True
                            grub2 = True
                            if grubentry:
                                grubdata.append(grubentry)
                            grubentry = {'menuentry': [fsline]}
                            _logger.debug('grub line: %s' % fsline)
                        elif fsline.split()[0] == 'search':
                            if mentry:
                                grubentry['menuentry'].append(fsline)
                                _logger.debug('Grub line: %s'
                                              % grubentry['menuentry'])
                            else:
                                _logger.debug('Not a menuentry, '
                                              'skipping %s' % fsline)
                        else:
                            _logger.debug('Skipping %s' % fsline)
            if grubentry:
                grubdata.append(grubentry)
        except Exception as e:
            _logger.error('   Errors during reading %s: %s'
                          % (grub_cfg_path, str(e)))
            raise OciMigrateException('Errors during reading %s: %s'
                                      % (grub_cfg_path, str(e)))
        if grub2:
            _logger.debug('Found grub2 configuration file.')
            migrate_tools.result_msg(msg='Found grub2 configuration file',
                                     result=True)
        else:
            migrate_tools.result_msg(msg='Found grub configuration file',
                                     result=True)
            try:
                #
                # check for grub data
                with open(grub_cfg_path, 'r') as f:
                    for ffsline in f:
                        fsline = ffsline.strip()
                        if len(fsline.split()) > 0:
                            _logger.debug('%s' % fsline)
                            if fsline.split()[0] == 'title':
                                if grubentry:
                                    grubdata.append(grubentry)
                                grubentry = {'title': [fsline]}
                                _logger.debug('grub line: %s' % fsline)
                            elif fsline.split()[0] == 'kernel':
                                grubentry['title'].append(fsline)
                                _logger.debug('grub line: %s'
                                              % grubentry['title'])
                            else:
                                _logger.debug('skipping %s' % fsline)
                if grubentry:
                    grubdata.append(grubentry)
            except Exception as e:
                _logger.error('   Errors during reading %s: %s'
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
        _logger.debug('Collection os data, looking in %s'
                      % self._mountpoints)
        osdict = dict()
        #
        # hostnamectl is a systemd command, not available in OL/RHEL/CentOS 6
        try:
            for mnt in self._mountpoints:
                osdata = migrate_utils.exec_search('os-release', rootdir=mnt)
                if osdata is not None:
                    with open(osdata, 'r') as f:
                        osreleasedata = \
                            [line.strip()
                             for line in f.read().splitlines()
                             if '=' in line]
                    osdict = dict([re.sub(r'"', '', kv).split('=')
                                   for kv in osreleasedata])
                    break
                else:
                    _logger.debug('os-release not found in %s' % mnt)
        except Exception as e:
            _logger.error('   Failed to collect os data: %s' % str(e),
                          exc_info=True)
        _logger.debug('os data: %s' % osdict)
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
        # fstabfile = self._img_info['rootmnt'][1] + '/etc/fstab'
        _logger.debug('Fstabfile: %s' % fstabfile)
        try:
            with open(fstabfile, 'r') as f:
                for fsline in f:
                    if '#' not in fsline and len(fsline.split()) > 5:
                        # fsline[0] != '#' ????
                        fstabdata.append(fsline.split())
                        migrate_tools.result_msg(msg='%s' % fsline.split())
                    else:
                        _logger.debug('skipping %s' % fsline)
        except Exception as e:
            _logger.error('   Problem reading %s: %s' % (fstabfile, str(e)))
        return fstabdata

    def generic_prereq_check(self):
        """
        Verify the generic prequisites.
        Returns
        -------
            bool: True or False.
            str : The eventual fail message.
        """
        passed_requirement = True
        failmsg = ''
        #
        # BIOS boot
        if 'boot_type' in self._img_info:
            if self._img_info['boot_type'] in get_config_data(
                    'valid_boot_types'):
                _logger.debug('Boot type is %s, ok'
                              % self._img_info['boot_type'])
                migrate_tools.result_msg(msg='Boot type is %s, ok'
                                             % self._img_info['boot_type'],
                                         result=True)
            else:
                passed_requirement = False
                _logger.debug('Boot type %s is not a valid boot '
                              'type. ' % self._img_info['boot_type'])
                failmsg += '\n  - Boot type %s is not a valid boot ' \
                           'type. ' % self._img_info['boot_type']
        else:
            passed_requirement = False
            failmsg += '\n  - Boot type not found.'
        #
        # MBR
        if 'mbr' in self._img_info:
            if self._img_info['mbr']['valid']:
                _logger.debug('The image %s contains a '
                              'valid MBR.' % self._img_info['img_name'])
                migrate_tools.result_msg(
                    msg='The image %s contains a valid MBR.'
                        % self._img_info['img_name'],
                    result=True)
            else:
                passed_requirement = False
                _logger.debug('The image %s does not contain a '
                              'valid MBR.' % self._img_info['img_name'])
                failmsg += '\n  - The image %s does not contain a ' \
                           'valid MBR.' % self._img_info['img_name']
            #
            # 1 disk: considering only 1 image file, representing 1 virtual
            # disk,
            # implicitly.
            #
            # Bootable
            partitiontable = self._img_info['mbr']['partition_table']
            bootflag = False
            for i in range(0, len(partitiontable)):
                if partitiontable[i]['boot']:
                    bootflag = True
                    _logger.debug('The image %s is bootable'
                                  % self._img_info['img_name'])
                    migrate_tools.result_msg(msg='The image %s is bootable'
                                                 % self._img_info['img_name'],
                                             result=True)
            if not bootflag:
                passed_requirement = False
                _logger.error('   The image %s is not bootable'
                              % self._img_info['img_name'])
                failmsg += '\n  - The image %s is not bootable.' \
                           % self._img_info['img_name']
        else:
            passed_requirement = False
            failmsg += '\n  - MBR not found.'
        #
        # Everything needed to boot in this image? Compairing fstab with
        # partition data.
        if 'fstab' in self._img_info:
            fstabdata = self._img_info['fstab']
            partitiondata = self._img_info['partitions']

            fstab_pass = True
            for line in fstabdata:
                part_pass = False
                _logger.debug('Fstabline: %s' % line)
                if 'UUID' in line[0]:
                    uuid_x = re.split('\\bUUID=\\b', line[0])[1]
                    for _, part in list(partitiondata.items()):
                        _logger.debug('partition: %s' % part)
                        if 'ID_FS_UUID' in part:
                            if part['ID_FS_UUID'] == uuid_x:
                                part_pass = True
                                migrate_tools.result_msg(
                                    msg='Found %s in partition table.'
                                        % uuid_x, result=True)
                                break
                elif 'LABEL' in line[0]:
                    label_x = re.split('\\bLABEL=\\b', line[0])[1]
                    for _, part in list(partitiondata.items()):
                        _logger.debug('partition: %s' % part)
                        if 'ID_FS_LABEL' in part:
                            if part['ID_FS_LABEL'] == label_x:
                                part_pass = True
                                migrate_tools.result_msg(
                                    msg='Found %s in partition table.'
                                        % label_x, result=True)
                                break
                elif 'mapper' in line[0]:
                    lv_x = re.split('\\bmapper/\\b', line[0])[1]
                    for part, _ in list(partitiondata.items()):
                        _logger.debug('partition: %s' % part)
                        if lv_x in part:
                            part_pass = True
                            migrate_tools.result_msg(
                                msg='Found %s in partition table.'
                                    % lv_x, result=True)
                            break
                elif '/dev/' in line[0]:
                    _logger.critical('  Device name %s in fstab are '
                                     'not supported.' % line[0])
                else:
                    part_pass = True
                    migrate_tools.result_msg(msg='Unrecognised: %s, ignoring.'
                                                 % line[0], result=True)

                if not part_pass:
                    fstab_pass = False
                    break

            if not fstab_pass:
                passed_requirement = False
                failmsg += '\n  - fstab file refers to unsupported or ' \
                           'unreachable partitions.'
        else:
            passed_requirement = False
            failmsg += '\n  - fstab file not found.'
        #
        # boot using LVM or UUID
        if 'grubdata' in self._img_info:
            grubdata = self._img_info['grubdata']
            #
            # grub: 'root=UUID'
            # grub2: '--fs-uuid'
            grub_fail = 0
            grub_l = 0
            for entry in grubdata:
                for key in entry:
                    for le in entry[key]:
                        l_split = le.split()
                        if l_split[0] == 'search':
                            grub_l += 1
                            if '--fs-uuid' not in l_split:
                                _logger.error('   grub2 line ->%s<- does not '
                                              'specify boot partition '
                                              'via UUID.' % le)
                                grub_fail += 1
                            else:
                                migrate_tools.result_msg(
                                    msg='grub2 line ->%s<- specifies boot '
                                        'partition via UUID.' % le)
                        elif l_split[0] == 'kernel':
                            grub_l += 1
                            if len([a for a in l_split if any(b in a for b in
                                                              ['root=UUID=',
                                                               'root=/dev/mapper/'])]) == 0:
                                _logger.debug(
                                    'grub line ->%s<- does not specify boot '
                                    'partition via UUID nor LVM2.' % le)
                                grub_fail += 1
                            else:
                                migrate_tools.result_msg(
                                    msg='grub line ->%s<- specifies boot '
                                        'partition via UUID or LVM2.' % le,
                                    result=True)
                        else:
                            _logger.debug('skipping %s' % l_split)
            if grub_l == 0:
                passed_requirement = False
                failmsg += '\n  - No boot entry found in grub/gru2 config file.'
            elif grub_fail > 0:
                passed_requirement = False
                failmsg += '\n  - grub config file does not guarantee booting ' \
                           '' \
                           'using UUID or LVM2.'
            else:
                _logger.debug('Grub config file ok.')
        else:
            passed_requirement = False
            failmsg += '\n  - Grub config file not found.'
        #
        # OS
        if 'osinformation' in self._img_info:
            osdata = self._img_info['osinformation']
            os_pass = False
            os_name = 'notsupportedos'
            for k, v in list(osdata.items()):
                _logger.debug('%s %s' % (k, v))
                if k.upper() == 'NAME':
                    vu = v.upper().strip()
                    os_name = v
                    _logger.debug('OS name: %s' % vu)
                    if vu in get_config_data('valid_os'):
                        migrate_tools.result_msg(msg='OS is: %s: valid' % v,
                                                 result=True)
                        os_pass = True
                    else:
                        self._logger.error('   ->OS<- %s is not supported.' % v)
            if not os_pass:
                passed_requirement = False
                failmsg += '\n  - OS %s is not supported' % os_name
        else:
            passed_requirement = False
            failmsg += '\n  - OS release file not found.'

        return passed_requirement, failmsg
