# oci-utils
#
# Copyright (c) 2019, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing migrate platform system tools.
"""
import ipaddress
import logging
import os
import re
import shutil
import string
import subprocess
import threading
import uuid
from glob import glob

from oci_utils.migrate import ProgressBar
from oci_utils.migrate import error_msg
from oci_utils.migrate import migrate_data
from oci_utils.migrate import pause_msg
from oci_utils.migrate import result_msg
from oci_utils.migrate import terminal_dimension
from oci_utils.migrate.decorators import state_loop
from oci_utils.migrate.exception import OciMigrateException

_logger = logging.getLogger('oci-utils.system_tools')


def backup_dir(directory_name):
    """
    Backup a directory as path/bck_directory_name_[current_time]

    Parameters
    ----------
    directory_name: str
        The full path of the directory.

    Returns
    -------
        str: path of backup directory on success, None otherwise.
    """
    _logger.debug('__ Backup %s', directory_name)
    try:
        if os.path.isdir(directory_name):
            backup_name = generate_backup_name(directory_name)
            shutil.copytree(directory_name, backup_name)
            _logger.debug('Backup of %s succeeded.', directory_name)
            return backup_name

        _logger.warning('%s is not a directory.', directory_name)
        return None
    except Exception as e:
        _logger.warning('Backup of %s failed: %s', directory_name, str(e))
        return None


def backup_file(file_name):
    """
    Backup a single file as path/bck_file_name_[current_time]

    Parameters
    ----------
    file_name: str
        The full path of the directory.

    Returns
    -------
        str: path of backup file on success, None otherwise.
    """
    _logger.debug('__Backup %s', file_name)
    try:
        if os.path.exists(file_name):
            if os.path.isdir(file_name):
                _logger.warning('%s is a directory.', file_name)
                return None
            backup_name = generate_backup_name(file_name)
            shutil.copyfile(file_name, backup_name)
            _logger.debug('Backup of %s succeeded.', file_name)
            return backup_name

        _logger.debug('%s does not exist.', file_name)
        return None
    except Exception as e:
        _logger.warning('Backup of %s failed: %s', file_name, str(e))
        return None


def enter_chroot(newroot):
    """
    Execute the chroot command.

    Parameters
    ----------
        newroot: str
            Full path of new root directory.

    Returns
    -------
        file descriptor, str, str: The file descriptor of the current root on
        success, path to restore, current working dir;
        raises an exception on failure.
    """
    _logger.debug('__ Entering chroot jail at %s.', newroot)
    root2return = -1
    current_dir = ''
    try:
        #
        # current working directory
        current_dir = os.getcwd()
        #
        # change root
        root2return = os.open('/', os.O_RDONLY)
        os.chdir(newroot)
        os.chroot(newroot)
        _logger.debug('Changed root to %s.', newroot)
    except Exception as e:
        _logger.error('  Failed to change root to %s: %s', newroot, str(e))
        #
        # need to return environment.
        if root2return > 0:
            os.fchdir(root2return)
            os.chroot('.')
            os.close(root2return)
        raise OciMigrateException('Failed to change root to %s:' % newroot) from e
    try:
        #
        # adjust PATH to make sure.
        currentpath = os.environ['PATH']
        newpath = currentpath.replace('/bin', '')\
            .replace('/usr/bin', '')\
            .replace('/sbin', '')\
            .replace('/usr/sbin', '')\
            .replace('/usr/local/sbin', '')\
            .replace('::', ':') \
            + ':/root/bin:/bin:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin'
        os.environ['PATH'] = newpath
        _logger.debug('Set path to %s', newpath)
        return root2return, currentpath, current_dir
    except Exception as e:
        _logger.error('  Failed to set path to %s: %s', newpath, str(e))
        raise OciMigrateException('Failed to set path to %s:' % newpath) from e


@state_loop(migrate_data.qemu_max_count)
def create_nbd():
    """
    Load nbd module

    Returns
    -------
        bool: True on succes, False on failure, raise an exception on call
        error.
    """
    cmd = ['modprobe', 'nbd', 'max_part=63']
    _logger.debug('__ Running %s', cmd)
    try:
        if run_call_cmd(cmd) == 0:
            return True

        _logger.critical('   Failed to execute %s', cmd)
        raise OciMigrateException('\nFailed to execute %s' % cmd)
    except Exception as e:
        _logger.critical('   Failed: %s', str(e))
        return False


@state_loop(migrate_data.qemu_max_count)
def exec_blkid(blkid_args):
    """
    Run a blkid command.

    Parameters
    ----------
    blkid_args: list
        The argument list for the blkid command.

    Returns
    -------
        dict: blkid return value on success, None otherwise.
    """
    cmd = ['blkid'] + blkid_args
    _logger.debug('__ Running %s', cmd)
    try:
        pause_msg('test nbd devs', pause_flag='_OCI_EXEC')
        blkid_res = run_popen_cmd(cmd, valid_return=frozenset([0,2]))['output'].decode('utf-8')
        _logger.debug('success\n%s', blkid_res)
        return blkid_res
    except Exception as e:
        _logger.error('  %s failed: %s', cmd, str(e))
        return None


def exec_exists(executable):
    """
    Verify if executable exists in path.

    Parameters
    ----------
    executable: str
        The file to be tested.

    Returns
    -------
        str: full path on success, None otherwise.

    """
    _logger.debug('__ which %s', executable)
    return shutil.which(executable)


def exec_ldconfig():
    """
    Executes ldconfig to update the shared library cache.

    Returns
    -------
    int: 0 on success, raises an exception otherwise.
    """
    cmd = ['ldconfig']
    _logger.debug('__ Running %s', cmd)
    try:
        pause_msg('running ldconfig', pause_flag='_OCI_EXEC')
        return run_call_cmd(cmd)
    except Exception as e:
        _logger.error('  %s command failed: %s', cmd, str(e))
        raise OciMigrateException('\n%s command failed:' % cmd) from e


def exec_lsblk(lsblk_args):
    """
    Run an lsblk command.

    Parameters
    ----------
    lsblk_args: list
        The argument list for the blkid command.

    Returns
    -------
       dict: blkid return value on success, None otherwise.
    """
    cmd = ['lsblk'] + lsblk_args
    _logger.debug('__ Running %s', cmd)
    pause_msg(cmd, pause_flag='_OCI_EXEC')
    try:
        lsblk_res = run_popen_cmd(cmd)['output'].decode('utf-8')
        _logger.debug('Success\n%s', lsblk_res)
        return lsblk_res
    except Exception as e:
        _logger.error('  %s failed: %s', cmd, str(e))
        raise OciMigrateException('%s failed:' % cmd) from e


def exec_lvscan(lvscan_args):
    """
    Scan the system for logical volumes.

    Parameters
    ----------
        lvscan_args: list
            list of strings, arguments for lvscan
    Returns
    -------
        list:  A list of strings, the output of lvscan --verbose on success,
               raises an exeception on failure.
    """
    cmd = ['lvscan'] + lvscan_args
    _logger.debug('__ Running: %s', cmd)
    pause_msg(cmd, pause_flag='_OCI_LVM')
    try:
        _logger.debug('command: %s', cmd)
        output = run_popen_cmd(cmd)['output'].decode('utf-8')
        _logger.debug('Logical volumes scanned:\n%s', str(output))

        return output.splitlines()
    except Exception as e:
        #
        # lvscan failed
        _logger.critical('   Failed to scan for logical volumes: %s', str(e))
        raise OciMigrateException('Failed to scan for logical volume:') from e


def exec_mkdir(dirname):
    """
    Create a directory.

    Parameters
    ----------
    dirname: str
        The full path of the directory.

    Returns
    -------
        bool:
           True on success, False otherwise.
    """
    _logger.debug('__ Creating %s.', dirname)
    try:
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        else:
            _logger.debug('Directory %s already exists', dirname)
        return True
    except Exception as e:
        raise OciMigrateException('') from e


def mount_pseudo(rootdir):
    """
    Remount proc, sys and dev.

    Parameters
    ----------
    rootdir: str
        The mountpoint of the root partition.

    Returns
    -------
        list: The list of new mountpoints on success, None otherwise.
    """
    pseudodict = {'proc': ['-t', 'proc', 'none', '%s/proc' % rootdir],
                  'dev': ['-o', 'bind', '/dev', '%s/dev' % rootdir],
                  'sys': ['-o', 'bind', '/sys', '%s/sys' % rootdir]}

    pseudomounts = []
    _logger.debug('__ Mounting: %s', pseudodict)
    for dirs, cmd_par in list(pseudodict.items()):
        cmd = ['mount'] + cmd_par
        _logger.debug('Mounting %s', dirs)
        pause_msg(cmd, pause_flag='_OCI_MOUNT')
        try:
            _logger.debug('Command: %s', cmd)
            cmdret = run_call_cmd(cmd)
            _logger.debug('%s : %d', cmd, cmdret)
            if cmdret != 0:
                _logger.error('  Failed to %s', cmd)
                raise Exception('%s Failed: %d' % (cmd, cmdret))
            pseudomounts.append(cmd_par[3])
        except Exception as e:
            _logger.critical('   Failed to %s: %s', cmd, str(e))
            raise OciMigrateException('Failed to %s:' % cmd) from e
    return pseudomounts


def exec_parted(devname):
    """
    Collect data about the device on the image using the parted utility.

    Parameters
    ----------
    devname: str
        The device name.

    Returns
    -------
        dict: The device data from parted utility on success, None otherwise.
    """
    cmd = ['parted', devname, 'print']
    _logger.debug('__ Running %s', cmd)
    pause_msg(cmd, pause_flag='_OCI_EXEC')
    try:
        result = run_popen_cmd(cmd)['output'].decode('utf-8')
        _logger.debug('parted: %s', result)
        device_data = dict()
        device_data['Partition List'] = list()
        for devx in result.splitlines():
            _logger.debug('%s - %d', devx, len(devx))
            if 'Model' in devx:
                device_data['Model'] = devx.split(':')[1]
                _logger.debug('Model %s', device_data['Model'])
            elif 'Disk Flags' in devx:
                device_data['Disk Flags'] = devx.split(':')[1]
                _logger.debug('Disk Flags %s', device_data['Disk Flags'])
            elif 'Disk' in devx:
                device_data['Disk'] = devx.split(':')[1]
                _logger.debug('Disk %s', device_data['Disk'])
            elif 'Partition Table' in devx:
                device_data['Partition Table'] = devx.split(':')[1]
                _logger.debug('Partition Table %s', device_data['Partition Table'])
            elif devx.split():
                if devx.split()[0].isdigit():
                    device_data['Partition List'].append(devx.split())
                    _logger.debug('Partition: %s', devx.split())
                else:
                    _logger.debug('Ignoring %s', devx)
            else:
                _logger.debug('Ignoring %s', devx)
        _logger.debug(device_data)
        pause_msg(device_data, pause_flag='_OCI_EXEC')
        return device_data
    except Exception as e:
        _logger.error('  Failed to collect parted %s device data: %s', devname, str(e))
        return None


def exec_pvscan(pvscan_args, devname=None):
    """
    Update the lvm cache.

    Parameters
    ----------
        pvscan_args: list
            List of strings, arguments for pvscan
        devname: str
            Device name to scan.

    Returns
    -------
        bool: True on success, raises an exception on failure.
    """
    _logger.debug('__ Running pvscan %s', pvscan_args)
    cmd = ['pvscan'] + pvscan_args
    if devname is not None:
        cmd.append(devname)
    pause_msg(cmd, pause_flag='_OCI_LVM')
    try:
        _logger.debug('command: %s', cmd)
        cmdret = run_call_cmd(cmd)
        _logger.debug('Physical volumes scanned on %s: %d', devname, cmdret)
        if cmdret != 0:
            _logger.error('  Physical volume scan failed.')
            raise Exception('Physical volume scan failed.')
        return True
    except Exception as e:
        #
        # pvscan failed
        _logger.critical('   Failed to scan %s for physical volumes: %s', devname, str(e))
        raise OciMigrateException('Failed to scan %s for physical volumes:' % devname) from e


@state_loop(migrate_data.qemu_max_count)
def exec_qemunbd(qemunbd_args):
    """
    Execute a qemu-nbd command.

    Parameters
    ----------
    qemunbd_args: list
        The list of arguments for qemu-nbd.

    Returns
    -------
        int: 0 on success, raise exception otherwise.

    """
    cmd = ['qemu-nbd'] + qemunbd_args
    _logger.debug('__ Running %s', cmd)
    pause_msg(cmd, pause_flag='_OCI_EXEC')
    try:
        return run_call_cmd(cmd)
    except Exception as e:
        _logger.error('  %s command failed: %s', cmd, str(e))
        raise OciMigrateException('\n%s command failed:' % cmd) from e


def exec_rename(some_name, to_name=None):
    """
    Renames a file, symbolic link or directory to path/bck_filename_current_time.

    Parameters
    ----------
    some_name: str
        Full path of the original file.
    to_name: str
        Full path of the destination file, if specified, using default otherwise.

    Returns
    -------
        str: the path of the renamed file on success, None otherwise.
    """
    if not bool(to_name):
        to_name = generate_backup_name(some_name)
    _logger.debug('__ Rename %s to %s', some_name, to_name)
    #
    try:
        #
        # delete to_ if already exists
        #
        # if file, symlink or directory
        if os.path.exists(to_name):
            _logger.debug('%s already exists', to_name)
            if os.path.isfile(to_name):
                os.remove(to_name)
            elif os.path.isdir(to_name):
                os.rmdir(to_name)
            elif os.path.islink(to_name):
                if os.unlink(to_name):
                    _logger.debug('Removed symbolic link %s', to_name)
                else:
                    _logger.error('   Failed to remove symbolic link %s', to_name)
            else:
                _logger.error('   Failed to remove %s.', to_name)
        else:
            _logger.debug('%s does not exists', to_name)
        #
        # rename
        if os.path.exists(some_name) or os.path.islink(some_name):
            _logger.debug('%s exists and is a file or symbolic link.', some_name)
            os.rename(some_name, to_name)
            _logger.debug('Renamed %s to %s.', some_name, to_name)
            return to_name

        _logger.debug('   %s does not exists', some_name)
    except Exception as e:
        _logger.error('   Failed to rename %s to %s: %s', some_name, to_name, str(e))
        raise OciMigrateException('Failed to rename %s to %s' % (some_name, to_name)) from e
    return None


@state_loop(migrate_data.qemu_max_count)
def exec_rmdir(dirname):
    """
    Create a directory.

    Parameters
    ----------
    dirname: str
        The full path of the directory.

    Returns
    -------
        bool:
           True on success, raises an exception otherwise.
    """
    _logger.debug('__ Removing directory tree %s.', dirname)
    try:
        shutil.rmtree(dirname)
        return True
    except Exception as e:
        raise OciMigrateException('') from e


@state_loop(migrate_data.rmmod_max_count)
def exec_rmmod(module):
    """
    Removes a module.

    Parameters
    ----------
    module: str
        The module name.

    Returns
    -------
        bool: True
    """
    _logger.debug('__ Remove module %s', module)
    cmd = ['rmmod']
    cmd.append(module)
    try:
        rmmod_result = subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
        if rmmod_result == 0:
            _logger.debug('Successfully removed %s', module)
        else:
            _logger.error('  Error removing %s, exit code %s, ignoring.', cmd, str(rmmod_result))
    except Exception as e:
        _logger.debug('Failed: %s, ignoring.', str(e))
    #
    # ignoring eventual errors, which will be caused by module already removed.
    return True


def exec_sfdisk(devname):
    """
    Collect the data about the partitions on the image file mounted on the
    device devname using the sfdisk utility.

    Parameters
    ----------
    devname: str
        The device.

    Returns
    -------
        dict: The partition data with sfdisk results on success, None otherwise.
    """
    cmd = ['sfdisk', '-d', devname]
    _logger.debug('__ Running %s', cmd)
    pause_msg(cmd, pause_flag='_OCI_EXEC')
    try:
        result = run_popen_cmd(cmd)['output'].decode('utf-8')
        partdata = dict()
        for devx in result.splitlines():
            if devx.startswith(devname):
                key = devx.split(':')[0].strip()
                result_msg(msg='sfdisk partition %s' % key, result=False)
                thispart = {'start': 0, 'size': 0, 'Id': 0, 'bootable': False}
                val = devx.split(':')[1].split(',')
                for it in val:
                    if 'start' in it:
                        x = it.split('=')[1]
                        thispart['start'] = int(x)
                    elif 'size' in it:
                        x = it.split('=')[1]
                        thispart['size'] = int(x)
                    elif 'Id' in it:
                        x = it.split('=')[1]
                        thispart['Id'] = x.strip()
                    elif 'bootable' in it:
                        thispart['bootable'] = True
                    else:
                        _logger.debug('unrecognised item: %s', val)
                partdata[key] = thispart
        _logger.debug(partdata)
        return partdata
    except Exception as e:
        _logger.error('  Failed to collect sfdisk %s partition data: %s', devname, str(e))
        return None


def exec_vgchange(changecmd):
    """
    Execute vgchange command.

    Parameters
    ----------
    changecmd: list
        Parameters for the vgchange command.

    Returns
    -------
        str: vgchange output.
    """
    cmd = ['vgchange'] + changecmd
    _logger.debug('__ Running %s', cmd)
    pause_msg(cmd, pause_flag='_OCI_LVM')
    try:
        output = run_popen_cmd(cmd)['output'].decode('utf-8')
        _logger.debug('vgchange result:\n%s', output)
        return output
    except Exception as e:
        _logger.critical('   Failed to execute %s: %s', cmd, str(e))
        raise OciMigrateException('Failed to execute %s:' % cmd) from e


def exec_rename_volume_groups(vg_list, direction):
    """
    Rename a list of volume groups.

    Parameters
    ----------
    vg_list: list
        list of lists [original name, new name]
    direction: str
        if FORWARD, rename original name to new name, if BACKWARD from new name
        to original name.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('__ Rename volume group %s.', vg_list)
    result = True
    #
    for vg_names in vg_list:
        if direction == 'FORWARD':
            cmd = ['vgrename', vg_names[0], vg_names[1]]
        elif direction == 'BACKWARD':
            cmd = ['vgrename', vg_names[1], vg_names[0]]
        else:
            _logger.debug('Invalid argument %s', direction)
            return False
        #
        pause_msg(cmd, pause_flag='_OCI_LVM')
        try:
            _logger.debug('command: %s', cmd)
            output = run_popen_cmd(cmd)['output'].decode('utf-8')
            if 'successfully renamed' in output:
                _logger.debug('%s succeeded', cmd)
            else:
                _logger.debug('%s failed', cmd)
                result = False
        except Exception as e:
            _logger.debug('Execution of vgrename failed: %s', str(e))
            result = False
    return result


def exec_vgs_noheadings():
    """
    List the local volume group and generates a new (temporary) name as
    a hex UUID.

    Returns
    -------
        list: list of lists [original volume group name, new volume group name].
    """
    cmd = ['vgs', '--noheadings']
    _logger.debug('__ Executing %s.', cmd)
    pause_msg(cmd, pause_flag='_OCI_LVM')
    vg_list = list()
    try:
        vgs_response = run_popen_cmd(cmd)['output']
        output = vgs_response.decode('utf-8').splitlines() if bool(vgs_response) else b''
        if bool(output):
            for vg_record in output:
                if len(vg_record) > 0:
                    vg_list.append([vg_record.split()[0], uuid.uuid4().hex])
            _logger.debug('Volume groups found: %s', vg_list)
        return vg_list
    except Exception as e:
        _logger.critical('   Failed to list current volume groups: %s', str(e))


def exec_vgscan(vgscan_args):
    """
    Scan the system for (new) volume groups.

    Parameters
    ----------
        vgscan_args: list
            list of strings, arguments for vgscan
    Returns
    -------
        bool: True on success, raises an exeception on failure.
    """
    cmd = ['vgscan'] + vgscan_args
    _logger.debug('__ Executing %s', cmd)
    pause_msg(cmd, pause_flag='_OCI_LVM')
    try:
        output = run_popen_cmd(cmd)['output'].decode('utf-8')
        _logger.debug('Volume groups scanned:\n%s', str(output))
        return True
    except Exception as e:
        #
        # vgscan failed
        _logger.critical('   Failed to scan for volume groups: %s', str(e))
        raise OciMigrateException('Failed to scan for volume groups:') from e


def generate_backup_name(full_path):
    """
    Generate a name for a file or directory path, as <path>/bck_<file>_timestamp.

    Parameters
    ----------
    full_path: str
        full path of file or directory.

    Returns
    -------
        str: full path of backup file or directory.
    """
    _logger.debug('__ Backup for %s', full_path)
    return os.path.split(full_path)[0] \
           + '/bck_' \
           + os.path.split(full_path)[1] \
           + '_' \
           + migrate_data.current_time


def get_free_nbd():
    """
    Find first free device name

    Returns
    -------
        str: The free nbd device on success, None otherwise.
    """
    _logger.debug('__ Get free nb device.')
    devpath = '/sys/class/block/nbd*'
    try:
        for devname in glob(devpath):
            with open(devname + '/size', 'r') as f:
                sz = f.readline()
                nbdsz = int(sz)
                if nbdsz == 0:
                    freedev = devname.rsplit('/')[-1]
                    return '/dev/' + freedev
        _logger.critical('   Failed to locate a free nbd devide.')
        raise OciMigrateException('\nFailed to locate a free nbd devide.')
    except Exception as e:
        _logger.critical('   Failed to screen nbd devices: %s', str(e))
        raise OciMigrateException('\nFailed to screen nbd devices:') from e


def get_grubby_kernels(boot_loader_entries):
    """
    Get the version of the kernels defined in the boot loader entries directory.

    Parameters
    ----------
    boot_loader_entries: str
        The boot loader entries directory.

    Returns
    -------
        list: list of kernels.
    """
    _logger.debug('__ Get the kernel versions from %s', boot_loader_entries)
    kernels_list = list()
    for _, _, files in os.walk(boot_loader_entries):
        for name in files:
            with open(os.path.join(boot_loader_entries, name)) as bootloaderentry:
                bl_lines = bootloaderentry.readlines()
            for bline in bl_lines:
                if 'vmlinuz' in bline:
                    kernels_list.append(bline.split('-', 1)[1].strip())
                    break
    return kernels_list

def get_grubby_default_kernel(grubenv_path):
    """
    Get the kernel booted by default in a loader entries env.

    Parameters
    ----------
    grubenv_path: str
        The full path of the grubenv file.

    Returns
    -------
        str: the kernel version.
    """
    _logger.debug('__ Get the default kernel from %s', grubenv_path)
    with open(grubenv_path, 'r') as gf:
        gf_lines = gf.readlines()
    for gf_line in gf_lines:
        if 'saved_entry' in gf_line:
            return(gf_line.split('-', 1)[1].strip())
    return None


def get_grub2_kernels(grub_config_file):
    """
    Get the versions of the kernels defined in the grub2 config file.
    Parameters
    ----------
    grub_config_file: str
        Full path of the grub config file.

    Returns
    -------
        list: list of kernel versions.
    """
    _logger.debug('__ Get the kernel versions from %s', grub_config_file)
    kernels_list = list()
    menu_flag = False
    with open(grub_config_file, 'r') as grub_file:
        for grub_line in grub_file:
            gl = ' '.join(grub_line.split()).split()
            if bool(gl):
                if gl[0] == 'menuentry':
                    menu_flag = True
                if menu_flag:
                    if 'linux' in gl[0]:
                        menu_flag = False
                        for it in gl:
                            if 'vmlinuz' in it:
                                kernel_version = it.split('-', 1)[1]
                                kernels_list.append(kernel_version)
    return kernels_list


def get_grub_default_kernel(grub_config_file):
    """
    Get the kernel version booted by default from the grub config file.

    Parameters
    ----------
    grub_config_file: str
        Full path of the grub config file.

    Returns
    -------
        str: kernel version.
    """
    _logger.debug('__ Get the default kernel from %s', grub_config_file)

    def find_default_boot(grub_filename):
        with open(grub_filename, 'r') as grub_fd:
            for grub_ln in grub_fd:
                grub_line_list = grub_ln.translate({ord(c): None for c in string.whitespace}).split('=')
                if grub_line_list[0] == 'default':
                    return int(grub_line_list[1])
        #
        # there should be always a default boot.
        return None

    default_kernel_nb = find_default_boot(grub_config_file)
    if default_kernel_nb is None:
        # todo:
        #   locate default and installed kernels in all the flavors of grub2 and EFI
        # _logger.critical('No default boot found.')
        # raise OciMigrateException('No default boot found.')
        #
        # not so fatal, only if boot device is not by lvm, by label or by uuid
        default_kernel_nb = 0
        kernelversion = 'not found'
        return kernelversion
    kernel_cnt = 0
    with open(grub_config_file, 'r') as grub_config_fd:
        for grub_line in grub_config_fd:
            gl = ' '.join(grub_line.split()).split()
            if bool(gl):
                if gl[0] == 'kernel':
                    if kernel_cnt == default_kernel_nb:
                        for it in gl:
                            if 'vmlinuz' in it:
                                kernelversion = it.split('-', 1)[1]
                                return kernelversion
                    kernel_cnt += 1


def get_grub_kernels(grub_config_file):
    """
    Get the versions of the kernels defined in the grub config file.
    Parameters
    ----------
    grub_config_file: str
        Full path of the grub config file.

    Returns
    -------
        list: list of kernel versions.
    """
    _logger.debug('__ Get the kernel versions from %s', grub_config_file)
    kernel_list = list()
    with open(grub_config_file, 'r') as grub_config_fd:
        for grub_line in grub_config_fd:
            gl = ' '.join(grub_line.split()).split()
            if bool(gl):
                if gl[0] == 'kernel':
                    for it in gl:
                        if 'vmlinuz' in it:
                            kernelversion = it.split('-', 1)[1]
                            kernel_list.append(kernelversion)
    return kernel_list


def get_nameserver():
    """
    Get the nameserver definitions, store the result in migrate_data.nameserver.

    Returns
    -------
    bool: True on success, False otherwise.
    """
    def dig_ns():
        """
        Look for a nameserver definition in the output of the dig command.

        Returns
        -------
            list: list of ipv4 nameservers.
        """
        dig = 'dig'
        dig_list = list()
        if exec_exists(dig):
            cmd = [dig]
            try:
                dig_output = run_popen_cmd(cmd)['output'].decode('utf-8').splitlines()
                for dig_item in dig_output:
                    if 'SERVER' in dig_item:
                        dig_list.append(re.search(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", dig_item).group())
                        _logger.debug('Found ns %s', dig_list[-1])
            except Exception as e:
                _logger.warning('   Failed to identify nameserver using dig: %s\n', str(e))
        else:
            _logger.debug('dig utility not found, install bind-utils.')
        return dig_list

    def nmcli_ns():
        """
        Look for a nameserver definition in the output of the nmcli command.

        Returns
        -------
            list: list of ipv4 nameservers.
        """
        nmcli = 'nmcli'
        nmcli_list = list()
        if exec_exists(nmcli):
            cmd = [nmcli, 'dev', 'show']
            try:
                nm_list = run_popen_cmd(cmd)['output'].decode('utf-8').splitlines()
                for nm_item in nm_list:
                    if 'DNS' in nm_item.split(':')[0]:
                        nmcli_list.append(nm_item.split(':')[1].lstrip().rstrip())
                        _logger.debug('Found ns %s', nmcli_list[-1])
            except Exception as e:
                _logger.warning('   Failed to identify nameserver using nmcli: %s\n', str(e))
        else:
            _logger.debug('nmcli not running.')
        return nmcli_list

    def resolv_ns():
        """
        Look for nameserver definition in resolv.conf.

        Returns
        -------
            list: list of ipv4 nameservers.
        """
        resolv_list = list()
        try:
            with open('/etc/resolv.conf', 'rb') as f:
                resolvconf_lines = f.read().decode('utf-8').splitlines()
            for nm_item in resolvconf_lines:
                ip = re.search(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", nm_item)
                if ip is not None:
                    resolv_list.append(nm_item.split(' ')[1].lstrip().rstrip())
                    _logger.debug('Found ns %s', resolv_list[-1])
        except Exception as e:
            _logger.warning('Failed to find nameserver in resolv.conf: %s.', str(e))
        return resolv_list

    # global nameserver
    _logger.debug("__ Collecting nameservers.")

    dns_list = dig_ns() + nmcli_ns() + resolv_ns()
    _logger.debug('Found nameservers: %s', dns_list)
    #
    # Verify if found one.
    if bool(dns_list):
        for ip_ad in dns_list:
            try:
                if ipaddress.ip_address(ip_ad).version == 4:
                    migrate_data.nameserver = dns_list[0]
                    break
            except ValueError as v:
                _logger.debug('%s', str(v))
            except Exception as e:
                _logger.debug('%s', str(e))
        _logger.debug('Nameserver set to %s', migrate_data.nameserver)
        return True
    return False


def is_thread_running(thread_id):
    """
    Verify if thread is active.

    Parameters
    ----------
    thread_id: thread
        The thread to test.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('__ Testing threadid %s.', thread_id)
    return bool(thread_id in threading.enumerate())


def is_root():
    """
    Verify is operator is the root user.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    return bool(os.getuid() == 0)


def leave_chroot(root2return, dir2return):
    """
    Leave a chroot environment and return to another one.

    Parameters
    ----------
    root2return: file descriptor
        The file descriptor of the root to return to.
    dir2return: str
        The original working dir to return to.

    Returns
    -------
        bool: True on success, raises exception on failure.
    """
    _logger.debug('__ Leaving chroot jail.')
    try:
        #
        # leave chroot
        os.fchdir(root2return)
        os.chroot('.')
        os.close(root2return)
        _logger.debug('Left change root environment.')
        #
        # return to working directory
        os.chdir(dir2return)
        return True
    except Exception as e:
        _logger.error('  Failed to return from chroot: %s', str(e))
        raise OciMigrateException('Failed to return from chroot: %s' % str(e))


def mount_fs(mountpoint):
    """
    Mount a filesystem specified in fstab, by mountpoint only.

    Parameters
    ----------
    mountpoint: str
        The mountpoint.

    Returns
    -------
        bool: True on success, False otherwise
    """
    cmd = ['mount', mountpoint]
    pause_msg(cmd, pause_flag='_OCI_MOUNT')
    _logger.debug('__ Mounting %s', mountpoint)
    try:
        _, nbcols = terminal_dimension()
        mountwait = ProgressBar(nbcols, 0.2, progress_chars=['mounting %s' % mountpoint])
        mountwait.start()
        _logger.debug('Command: %s', cmd)
        cmdret = run_call_cmd(cmd)
        _logger.debug('%s returned %d', cmd, cmdret)
        if cmdret == 0:
            return True

        raise Exception('%s failed: %d' % (cmd, cmdret))
    except Exception as e:
        _logger.error('  Failed to %s: %s', cmd, str(e))
        return False
    finally:
        if is_thread_running(mountwait):
            mountwait.stop()


def reset_vg_list(vg_list):
    """
    Update the local volume group list

    Parameters
    ----------
    vg_list: list (of lists)
        The volume group rename list.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('__ Updating the vg list.')
    for vg_l in vg_list:
        _logger.debug('Updating %s to %s.', vg_l[1], vg_l[0])
        vg_l[1] = vg_l[0]
    return True


def restore_nameserver():
    """
    Restore nameserver configuration.

    Returns
    -------
    bool: True on success, False otherwise.
    """
    _logger.debug('__ Restore nameserver data.')
    # global resolv_conf_path
    resolvpath = '/etc/resolv.conf'
    try:
        #
        # save used one
        if os.path.isfile(resolvpath):
            if not bool(exec_rename(resolvpath, resolvpath + '_temp_' + migrate_data.current_time)):
                _logger.debug('Failed to rename %s to %s, no harm done.',
                              resolvpath, resolvpath + '_temp_' + migrate_data.current_time)
        else:
            _logger.debug('No %s found.', resolvpath)
        #
        # restore original one
        if os.path.isfile(migrate_data.resolv_conf_path):
            if bool(exec_rename(migrate_data.resolv_conf_path, resolvpath)):
                _logger.debug('Successfully restored %s', resolvpath)
            else:
                _logger.debug('Failed to restore %s.', resolvpath)
                raise OciMigrateException('Failed to restore nameserver config.')
        else:
            _logger.debug('No %s found.', migrate_data.resolv_conf_path)
        return True
    except Exception as e:
        error_msg('Continuing but might cause issues installing cloud-init: %s' % str(e))
        return False


@state_loop(3)
def rm_nbd():
    """
    Unload kernel module nbd.

    Returns
    -------
        bool: True on succes, False on failure.
    """
    modname = 'nbd'
    return bool(exec_rmmod(modname))


def run_call_cmd(command):
    """
    Execute an os command which does not return data.

    Parameters
    ----------
        command: list
            The os command and its arguments.

    Returns
    -------
        int: The return value.
    """
    _logger.debug('__ Executing %s', command)
    assert (len(command) > 0), 'empty command list'
    try:
        return subprocess.call(command, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except OSError as oserr:
        raise OciMigrateException('OS error encountered while running %s:' % command) from oserr
    except subprocess.CalledProcessError as e:
        raise OciMigrateException('Error encountered while running %s:' % command) from e


def run_popen_cmd(command, valid_return=frozenset([0])):
    """
    Execute an os command and collect stdout and stderr.

    Parameters
    ----------
    command: list
        The os command and its arguments.
    valid_return: frozenset
        A set of valid return codes, default = [0]
    Returns
    -------
        dict: {'output': output,
               'error': error,
               'return_code: return_code}
        raises an exception on failure.
    """
    _logger.debug('__ Executing %s.', command)
    output_dict = dict()
    if exec_exists(command[0]) is not None:
        _logger.debug('running %s', command)
        try:
            ext_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, error = ext_process.communicate()
            return_code = ext_process.returncode
            output_dict['output'] = output
            output_dict['error'] = error
            output_dict['return_code'] = return_code
            #if return_code != 0:
            #    if bool(error):
            #        _logger.debug('Error occurred while running %s: %s - %s',
            #                      command, return_code, error.decode('utf-8'), exc_info=True)
            #    raise OciMigrateException('Error encountered while running %s: %s - %s'
            #                              % (command, return_code, error.decode('utf-8')))
            if not bool(output):
                _logger.debug('%s did not return output.', command)
            if bool(error):
                # not necessarily fatal
                _logger.debug('%s returned message %s.', command, error.decode('utf-8'))
            _logger.debug('%s returned code %s', command, str(return_code))
            if return_code not in valid_return:
                raise OciMigrateException('Error encountered while running %s: %s - %s'
                                          % (command, return_code, error.decode('utf-8')))
            return output_dict
        except OSError as os_error:
            raise OciMigrateException('OS error encountered while running %s:' % command) from os_error
        except Exception as e:
            raise OciMigrateException('Error encountered while running %s:' % command) from e
    else:
        _logger.critical('   %s not found.', command[0])
        raise OciMigrateException('%s does not exist' % command[0])


def set_nameserver():
    """
    Setting temporary nameserver.

    Returns
    -------
    bool: True on success, False otherwise.
    """
    # global resolv_conf_path
    _logger.debug('__ Set nameserver.')
    #
    # rename eventual existing resolv.conf
    resolvpath = '/etc/resolv.conf'
    try:
        #
        # save current
        if os.path.isfile(resolvpath) or os.path.islink(resolvpath) or os.path.isdir(resolvpath):
            migrate_data.resolv_conf_path = exec_rename(resolvpath)
            if not bool(migrate_data.resolv_conf_path):
                _logger.debug('Failed to save current nameserver configuration.')
        else:
            _logger.error('   No %s found', resolvpath)
        #
        # write new
        with open(resolvpath, 'w') as f:
            f.writelines('nameserver %s\n' % migrate_data.nameserver)
        return True
    except Exception as e:
        error_msg('Failed to set nameserver: %s\n continuing but might cause issues installing cloud-init.' % str(e))
        return False


def show_hex_dump(bindata):
    """
    Show hex and readable version of binary data.

    Parameters
    ----------
    bindata: binary data.

    Returns
    -------
        str: hexdump format
    """
    blocklen = 16
    ll = len(bindata)
    m = bindata
    hexdata = ''
    addr = 0
    try:
        while ll > 0:
            x = m[0:blocklen]
            line = ' '.join(['%02x' % i for i in bytearray(x)])
            line = line[0:23] + ' ' + line[23:]
            readable = ''.join([chr(i) if 32 <= i <= 127
                                else '.' for i in bytearray(x)])
            hexdata += '%08x : %s : %s :\n' % (addr*16, line, readable)
            y = m[blocklen:]
            m = y
            addr += 1
            ll -= blocklen
    except Exception as e:
        _logger.error('  Exception: %s', str(e))
    return hexdata


@state_loop(3)
def unmount_something(mountpoint):
    """
    Unmount.

    Parameters
    ----------
    mountpoint: str
        The mountpoint.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('__ Unmount %s.', mountpoint)
    if os.path.ismount(mountpoint):
        _logger.debug('%s is a mountpoint.', mountpoint)
    else:
        _logger.debug('%s is not a mountpoint, quitting', mountpoint)
        return True
    #
    cmd = ['umount', mountpoint]
    pause_msg(cmd, pause_flag='_OCI_MOUNT')
    try:
        _logger.debug('command: %s', cmd)
        cmdret = run_call_cmd(cmd)
        _logger.debug('%s : %d', cmd, cmdret)
        if cmdret != 0:
            raise Exception('%s failed: %d' % (cmd, cmdret))
    except Exception as e:
        _logger.error('  Failed to %s: %s', cmd, str(e))
        return False
    return True


def unmount_pseudo(pseudomounts):
    """
    Unmount the pseudodevices.

    Parameters
    ----------
    pseudomounts: list
        The list of pseudodevices

    Returns
    -------
        True on success, False otherwise.
    """
    _logger.debug('__ Unmount %s', pseudomounts)
    res = True
    pseudomounts.sort(reverse=True)
    for mnt in pseudomounts:
        _logger.debug('Unmount %s', mnt)
        umount_res = unmount_something(mnt)
        if umount_res:
            _logger.debug('%s successfully unmounted.', mnt)
        else:
            _logger.error('  Failed to unmount %s', mnt)
            res = False
    return res
