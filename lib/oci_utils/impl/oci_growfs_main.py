#
# Copyright (c) 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Script for expanding a filesystem to its configured size.
"""

import argparse
import logging
import os
import re
import subprocess
import sys
import termios
import tty

from oci_utils import is_root_user, find_exec_in_path
from oci_utils.lsblk import lsblk_partition_data

lc_all = 'en_US.UTF8'
_logger = logging.getLogger("oci-utils.oci-network-config")
valid_file_system_types = ['ext4', 'xfs']
na = '--'


def parse_args():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args())

    Returns
    -------
        The command line namespace
    """
    parser = argparse.ArgumentParser(prog='oci-growfs',
                                     description='Utility for expanding the root¶¶ filesystem to its configured size.',
                                     add_help=False)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-y', '--yes',
                       action='store_true',
                       dest='all_yes',
                       help='Answer y to all questions.'
                       )
    group.add_argument('-n', '--no',
                       action='store_true',
                       dest='all_no',
                       help='Answer n to all questions.'
                       )
    parser.add_argument('-m', '--mountpoint',
                        action='store',
                        default='/',
                        # help='The mountpoint of the filesystem to be expanded, the default is the root filesystem.')
                        help=argparse.SUPPRESS
                        )
    parser.add_argument('-h', '--help',
                        action='help',
                        help='Display this help'
                        )
    args = parser.parse_args()
    return args


def _getch():
    """
    Read a single keypress from stdin.

    Returns
    -------
        The resulting character.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def _read_yn(prompt, yn=True, waitenter=False, suppose_yes=False, suppose_no=False, default_yn=False):
    """
    Read yes or no form stdin, No being the default.

    Parameters
    ----------
        prompt: str
            The message.
        yn: bool
            Add (y/N) to the prompt if True.
        waitenter: bool
            Wait for the enter key pressed if True, proceed immediately
            otherwise.
        suppose_yes: bool
            if True, consider the answer is yes.
        suppose_no: bool
            if True, consider the answer is no.
        default_yn: bool
            The default answer.
    Returns
    -------
        bool: True on yes, False otherwise.
    """
    yn_prompt = prompt + ' '
    #
    # if yes is supposed, write prompt and return True.
    if suppose_yes:
        _ = sys.stdout.write(yn_prompt)
        sys.stdout.flush()
        return True
    if suppose_no:
        _ = sys.stdout.write(yn_prompt)
        sys.stdout.flush()
        return False
    #
    # add y/N to prompt if necessary.
    if yn:
        if default_yn:
            yn_prompt += ' [Y/n]'
            yn = 'Y'
        else:
            yn_prompt += ' [y/N] '
            yn = 'N'
    #
    # if wait is set, wait for return key.
    if waitenter:
        resp_len = 0
        while resp_len == 0:
            resp = input(yn_prompt).lstrip()
            resp_len = len(resp)
        yn_i = list(resp)[0].rstrip()
    #
    # if wait is not set, proceed on any key pressed.
    else:
        _ = sys.stdout.write(yn_prompt)
        sys.stdout.flush()
        yn_i = _getch().rstrip()

    sys.stdout.write('\n')
    if bool(yn_i):
        yn = yn_i
    return bool(yn.upper() == 'Y')


def show_data_tree(tree_root, depth):
    """
    Shows data in dict, list or tuple.

    Parameters
    ----------
    tree_root: structure
        the data structure.
    depth: int
        depth.

    Returns
    -------
        No return value.
    """
    if isinstance(tree_root, dict):
        print('')
        for key, value in tree_root.items():
            print('%s%s' % ('  '*depth, key.ljust(12, ' ')), end='')
            show_data_tree(value, depth+1)
    elif isinstance(tree_root, list):
        print('')
        for value in tree_root:
            show_data_tree(value, depth+1)
    elif isinstance(tree_root, tuple):
        print('%s' % '  ' * depth, end='')
        for value in tree_root:
            print('%s' % value, end='')
    else:
        print('%s' % tree_root)


class MountPoint:
    """ Class to expand the space for a mountpoint.
    """
    def __init__(self, mountpoint):
        """
        Initialise the DiskPartition instance.

        Parameters
        ----------
        mountpoint: str
            The mountpoint.
        """
        #
        # the mountpoint
        self.mountpoint = mountpoint
        #
        # physical partition name or logical volume dm, filesystem type, total size
        self.source, self.filesystem_type, self.source_size = self._get_filesystem_data()
        #

        if bool(self.source):
            self.partition_data = lsblk_partition_data(self.source)
            #
            # partition type (physical or lvm)
            self.type = self.partition_data['type']
            #
            # partition size in GB
            self.size = self.partition_data['size']
        else:
            self.partition_data = None
            self.type = None
            self.size = None
        #
        if self.type == 'part':
            #
            # physical device
            self.physical_device = [self.source]
            #
            # physical volume
            self.physical_volume = [self._get_device_from_partition()]
            #
            # partition number
            self.partition_number = [self._get_partition_number(self.source)]
        if self.type == 'lvm':
            #
            # volume group name
            self.volume_group = self._get_volume_group()
            #
            # volume path
            self.volume_path = self._get_volume_path()
            #
            # physical device
            self.physical_device = self._get_physical_devices_from_volume_group()
            #
            # physiscal volume
            self.physical_volume = self._get_device_of_physical_device()
            #
            # partition number
            self.partition_number = [self._get_partition_number(device) for device in self.physical_device]
        else:
            self.volume_group = na
            self.volume_path = na
            # self.physical_device = na
            # self.physical_volume = na
        self.device = self._get_device_from_partition()

    @staticmethod
    def show_line(tag, data):
        """
        Write a line of data if the data is not '--'

        Parameters
        ----------
        tag: str
            data tag.
        data: str
            the data

        Returns
        -------
            No return value.
        """
        if data != na:
            print('%20s: %s' % (tag, data))

    def show_data(self):
        """
        Write the data structure of the object.

        Returns
        -------
            No return value.
        """
        header = 'Mountpoint Data'
        print('%-20s\n%s' % (header, '-'*len(header)))
        self.show_line('mountpoint', self.mountpoint)
        self.show_line('source', self.source)
        self.show_line('filesystem type', self.filesystem_type)
        self.show_line('source size', self.source_size)
        self.show_line('type', self.type)
        self.show_line('size', self.size)
        self.show_line('physical devices', self.physical_device)
        self.show_line('physical volumes', self.physical_volume)
        self.show_line('partition number', self.partition_number)
        self.show_line('volume group name', self.volume_group)
        self.show_line('volume group path', self.volume_path)

        # self.show_line('device', self.device)
        # self.show_line('volume group', self.volume_group)
        # self.show_line('physical devices', self.physical_volumes)
        print('')

    def _get_filesystem_data(self):
        """
        Collect data on a mounted filesystem.

        Returns
        -------
            tuple: the device, the file system
        """
        cmd = [find_exec_in_path('findmnt'),
               '--canonicalize',
               '--noheadings',
               '--output',
               'SOURCE,FSTYPE,SIZE',
               self.mountpoint]
        _logger.debug('Running %s', cmd)
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()
            _logger.debug('Filesystem %s data: %s', self.mountpoint, output)
            return output[0].split()[0], output[0].split()[1], output[0].split()[2]
        except Exception as e:
            _logger.debug('Failed to get data on filesystem %s: %s', self.mountpoint, str(e),
                          stack_info=True,
                          exc_info=True)
            _logger.error('Failed to get data on filesystem %s', self.mountpoint)
            return None, None, None

    @staticmethod
    def _get_partition_number(partition):
        """
        Get the partition number.

        Parameters
        ----------
        partition: str
            The partition.

        Returns
        -------
            str: the partition number, None on failure.
        """
        _PARTITION_PATTERN = re.compile(r'(\d+)$', flags=re.UNICODE)
        try:
            part_number = _PARTITION_PATTERN.search(partition).group(1)
            _logger.debug('Partition number: %s', part_number)
            return part_number
        except Exception as e:
            _logger.debug('Failed to determine partition number of %s: %s', partition, str(e),
                          stack_info=True, exc_info=True)
            _logger.error('Failed to determine partition number of %s', partition)
            return None

    def _get_device_from_partition(self):
        """
        Get the device name from the partition name.

        Returns
        -------
            str: the device name, None on failure.
        """
        if not bool(self.source):
            _logger.error('There is no partition mounted on %s', self.mountpoint)
            return None
        try:
            ph_device = re.sub(r'\d+$', '', self.source)
            _logger.debug('Physical device: %s', ph_device)
            return ph_device
        except Exception as e:
            _logger.debug('Failed to determine device for %s: %s', self.source, str(e),
                          stack_info=True, exc_info=True)
            _logger.error('Failed to determine device for %s', self.source)
            return None

    @staticmethod
    def partition_growfs(device, partition_number, dry_run=True):
        """
        Expand a partition.

        Parameters
        ----------
        device: str
            The device name.
        partition_number: str
            The partition number.
        dry_run: bool
            Flag, execute a dry run if True, expand if False.

        Returns
        -------
            list: the growpart output.
        """
        cmd = [find_exec_in_path('growpart'), device, partition_number, '--verbose']
        if dry_run:
            cmd.append('--dry-run')
            msg = 'dry run'
        else:
            msg = 'expand'
        _logger.debug('Running %s', cmd)
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, error = process.communicate()
            return_code = process.returncode
            _logger.debug('growpart %s: %s (%s - %s)', msg, return_code, output.decode('utf-8'), error.decode('utf-8'))
            if return_code == 0:
                _logger.info('Partition %s expansion "%s" succeeded.', msg, device+partition_number)
            return output.decode('utf-8'), error.decode('utf-8')
        except Exception as e:
            _logger.debug('Failed to execute grow partition %s on  %s: %s', msg, device+partition_number, str(e),
                          stack_info=True, exc_info=True)
            _logger.error('Failed to execute grow partition %s on  %s', msg, device+partition_number)
            return None, None

    def _resize_ext4(self):
        """
        Expand an ext4 filesystem till partition borders.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        cmd = [find_exec_in_path('resize2fs'), self.source]
        _logger.debug('Running %s', cmd)
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()
            _logger.debug('resize2fs output: %s', output)
            return True
        except Exception as e:
            _logger.debug('Failed to execute resize2fs %s: %s', self.source, str(e), stack_info=True, exc_info=True)
            _logger.error('Failed to execute resize2fs %s', self.source)
            return False

    def _resize_xfs(self):
        """
        Expand an xfs filesystem till partition borders.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        cmd = [find_exec_in_path('xfs_growfs'), self.source]
        _logger.debug('Running %s', cmd)
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()
            _logger.debug('xfs_growfs output: %s', output)
            return True
        except Exception as e:
            _logger.debug('Failed to execute xfs_growfs %s: %s', self.source, str(e), stack_info=True, exc_info=True)
            _logger.error('Failed to execute xfs_growfs %s', self.source)
            return False

    def _get_volume_group(self):
        """
        Get the volume group name for a 'partition'

        Returns
        -------
            str: the volume group name on success, '--' otherwise
        """
        cmd = [find_exec_in_path('lvs'),
               '--noheadings',
               '--options',
               'vg_name',
               '--select',
               'lv_dm_path=%s' % self.source]
        _logger.debug('Running %s', cmd)
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()
            _logger.debug('lvs output: %s', output)
            volume_group = output[0].strip()
            _logger.info('Volume Group: %s', volume_group)
            return volume_group
        except Exception as e:
            _logger.debug('Failed to find volume group for %s: %s', self.device, str(e),
                          stack_info=True, exc_info=True)
            # return False
            return na

    def _get_volume_path(self):
        """
        Get the volume group path for a 'partition'

        Returns
        -------
            str: the volume group name on success, '--' otherwise
        """
        cmd = [find_exec_in_path('lvs'),
               '--noheadings',
               '--options',
               'lv_path',
               '--select',
               'lv_dm_path=%s' % self.source]
        _logger.debug('Running %s', cmd)
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()
            _logger.debug('lvs output: %s', output)
            volume_path = output[0].strip()
            _logger.info('Volume Path: %s', volume_path)
            return volume_path
        except Exception as e:
            _logger.debug('Failed to find volume path for %s: %s', self.device, str(e),
                          stack_info=True, exc_info=True)
            # return False
            return na

    def _get_physical_devices_from_volume_group(self):
        """
        Get the physical devices for a volume group.

        Returns
        -------
            list: list of physical devices on success, '--' otherwise.
        """
        cmd = [find_exec_in_path('pvs'),
               '--noheadings',
               '--options',
               'pv_name',
               '--select',
               'vg_name=%s' % self.volume_group]
        _logger.debug('Running %s', cmd)
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()
            physical_devices = [p.strip() for p in output]
            _logger.debug('pvs output: %s', physical_devices)
            return physical_devices
        except Exception as e:
            _logger.debug('Failed to find physical volumes for volume group %s: %s', self.volume_group, str(e),
                          stack_info=True, exc_info=True)
            return na

    def _get_device_of_physical_device(self):
        """
        Get the physical volumes for a list of devices.

        Returns
        -------
            list: physical volumes.
        """
        devices = list()
        try:
            for vol in self.physical_device:
                cmd = [find_exec_in_path('pvs'), '--noheadings', '--options', 'devices', '--select', 'pv_name=%s' % vol]
                _logger.debug('Running %s', cmd)
                output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()
                for dev in output:
                    devices.append(re.sub(r'\d+$', '', re.sub(r'\(.*?\)', '', dev.strip())))
            _logger.debug('pvs output: %s', devices)
            return devices
        except Exception as e:
            _logger.debug('Failed to find physical volumes for volume group %s', str(e),
                          stack_info=True, exc_info=True)
            return na

    def extend_filesystem(self):
        """
        Expand a filesystem on a partition.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        if self.filesystem_type == 'ext4':
            resize_fs = self._resize_ext4()
        elif self.filesystem_type == 'xfs':
            resize_fs = self._resize_xfs()
        else:
            _logger.error('Unsupported file system type: %s', self.filesystem_type)
            return False

        if resize_fs is True:
            _logger.info('Resizing filesystem at  %s succeeded.', self.mountpoint)
        else:
            _logger.info('Resizing filesystem at  %s failed.', self.mountpoint)
        return True

    @staticmethod
    def extend_physical_volume(physical_volume):
        """
        Extend a physical volume.

        Parameters
        ----------
        physical_volume: str
            The physical volume.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        cmd = [find_exec_in_path('pvresize'), physical_volume]
        _logger.debug('Running %s', cmd)
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()
            _logger.debug('Extended physical volume %s: %s', physical_volume, output)
            if 'changed' in output[0]:
                _logger.info('Extending %s succeeded.', physical_volume)
                return True
            _logger.error('Failed to extend physical volume %s.', physical_volume)
            return False
        except Exception as e:
            _logger.error('Failed to extend physical volume %s.', physical_volume)
            _logger.debug('Failed to extend physical volume %s: %s.', physical_volume, str(e))
            return False

    @staticmethod
    def extend_logical_volume(logical_volume):
        """
        Extend a logical volume.

        Parameters
        ----------
        logical_volume: str
            The logical volume.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        cmd = [find_exec_in_path('lvextend'), '-l', '+100%FREE', '--resize', logical_volume]
        _logger.debug('Running %s', cmd)
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()
            _logger.debug('Extended logical volume %s: %s', logical_volume, output)
            return True
        except Exception as e:
            _logger.error('Failed to extend logical volume %s.', logical_volume)
            _logger.debug('Failed to extend logical volume %s: %s.', logical_volume, str(e))
            return False


def main():
    """
    Main

    Returns
    -------
        int
            0 on success, 1 otherwise.
    """
    #
    # set locale
    os.environ['LC_ALL'] = "%s" % lc_all
    #
    # root privileges are required.
    if not is_root_user():
        _logger.error('This program needs to be run with root privileges')
        sys.exit(1)
    #
    # the command line.
    args = parse_args()
    _logger.debug('Command Line: %s', args)
    #
    # yes or no; mutual exclusive, is handled by argparse.
    # suppose_yes = True if args.all_yes else False
    suppose_yes = bool(args.all_yes)
    # suppose_no = True if args.all_no else False
    suppose_no = bool(args.all_no)
    #
    # the mountpoint
    growfs_data = MountPoint(args.mountpoint)
    if not bool(growfs_data.source):
        _logger.error('No valid mountpoint found.')
        sys.exit(1)
    growfs_data.show_data()
    #
    #
    expanded_partitions = 0
    expanded_devices = 0
    for dev in range(len(growfs_data.partition_number)):
        preview_output, preview_error = growfs_data.partition_growfs(growfs_data.physical_volume[dev],
                                                                     growfs_data.partition_number[dev],
                                                                     dry_run=True)
        if preview_output is None:
            _logger.error('Failed to determine partition extension possibilities on %s%s.',
                          growfs_data.physical_volume[dev], growfs_data.partition_number[dev])
            sys.exit(1)

        # show_data_tree(preview_error, 0)
        show_data_tree(preview_output, 0)
        if 'NOCHANGE' not in preview_output:
            if _read_yn('Expanding partition %s%s: Confirm? ' % (growfs_data.physical_volume[dev],
                                                                 growfs_data.partition_number[dev]),
                        yn=True, waitenter=True, suppose_yes=suppose_yes, suppose_no=suppose_no, default_yn=False):
                run_output, run_error = growfs_data.partition_growfs(growfs_data.physical_volume[dev],
                                                                     growfs_data.partition_number[dev],
                                                                     dry_run=False)
                show_data_tree(run_error, 0)
                show_data_tree(run_output, 0)
                if 'CHANGED' in run_output:
                    expanded_partitions += 1
                    if growfs_data.type == 'lvm':
                        if bool(growfs_data.extend_physical_volume(growfs_data.physical_device[dev])):
                            _logger.info('Device %s extended successfully.', growfs_data.physical_device[dev])
                            expanded_devices += 1
                        else:
                            _logger.error('Failed to extend %s.', growfs_data.physical_device[dev])
                    else:
                        _logger.debug('type is not lvm.')
                else:
                    _logger.error('Failed to expand %s%s', growfs_data.physical_volume[dev],
                                  growfs_data.partition_number[dev])
            else:
                _logger.debug('Not touching %s%s.', growfs_data.physical_volume[dev],
                              growfs_data.partition_number[dev])
        else:
            _logger.info('Unable to expand %s%s.\n', growfs_data.physical_volume[dev],
                         growfs_data.partition_number[dev])
    _logger.debug('expanded partitions: %d\nexpanded devices: %d', expanded_partitions, expanded_devices)
    #
    # if not partition could be expanded, leave here.
    if expanded_partitions == 0:
        _logger.info('No partitions expanded, exit.\n')
        return 0
    #
    # partitions expanded, if standard partitions, expand filesystem, if lvm, expand logical volume.
    if growfs_data.type == 'lvm':
        #
        # if no physical devices were expanded, leave here.
        if expanded_devices == 0:
            _logger.info('No physical devices expanded, exit.')
            return 0
        #
        # expand the logical volume and the file system
        if bool(growfs_data.extend_logical_volume(growfs_data.volume_path)):
            _logger.info('Logical volume %s extended successfully.', growfs_data.volume_path)
        else:
            _logger.error('Failed to extend logical volume %s.', growfs_data.volume_path)
    elif growfs_data.filesystem_type in valid_file_system_types:
        #
        # expand the filesystem on the expanded device.
        if bool(growfs_data.extend_filesystem()):
            _logger.info('File system %s on %s extended successfully.', growfs_data.filesystem_type, growfs_data.source)
        else:
            _logger.error('Failed to extend file system %s on %s.', growfs_data.filesystem_type, growfs_data.source)
    else:
        _logger.error('Invalid type: %s', growfs_data.filesystem_type)

    return 0


if __name__ == "__main__":
    sys.exit(main())
