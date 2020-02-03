# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module containing generic data and code with respect to the migration to the
Oracle Cloud Infrastructure.
"""
import configparser
import json
import logging
import os
import pkgutil
import re
import shutil
import subprocess
import sys
import time
import yaml
from functools import wraps
from glob import glob

from oci_utils.migrate import console_msg, read_yn
from oci_utils.migrate import get_config_data
from oci_utils.migrate import migrate_tools
from oci_utils.migrate import pause_msg
from oci_utils.migrate.exception import NoSuchCommand
from oci_utils.migrate.exception import OciMigrateException

_logger = logging.getLogger('oci-utils.migrate-utils')
ConfigParser = configparser.ConfigParser

gigabyte = 2**30
rmmod_max_count = 4
qemu_max_count = 2
#
# the root for loopback mounts of partitions and logical volumes.
loopback_root = '/mnt'
#
# the root of the migrate related packages.
module_home = 'oci_utils.migrate'


def state_loop(maxloop, intsec=1):
    """
    Decorator to allow a function to retry maxloop times with an interval of
    intsec before failing.

    Parameters
    ----------
    maxloop: int
        Maximum tries.
    intsec: int
        Interval in seconds.

    Returns
    -------
        Method return value.
    """
    def wrap(func):
        @wraps(func)
        def loop_func(*args, **kwargs):
            funcret = False
            for i in range(0, maxloop):
                _logger.debug('State loop %d' % i)
                try:
                    funcret = func(*args, **kwargs)
                    return funcret
                except Exception as e:
                    _logger.debug('Failed, sleeping for %d sec: %s'
                                  % (intsec, str(e)))
                    if i == maxloop - 1:
                        raise OciMigrateException('State Loop exhausted: %s'
                                                  % str(e))
                    time.sleep(intsec)
        return loop_func
    return wrap


def enter_chroot(newroot):
    """
    Execute the chroot command.

    Parameters
    ----------
        newroot: str
            Full path of new root directory.

    Returns
    -------
        file descriptor, str: The file descriptor of the current root on
        success, path to restore; raises an exception on failure.
    """
    root2return = -1
    try:
        #
        # change root
        root2return = os.open('/', os.O_RDONLY)
        os.chdir(newroot)
        os.chroot(newroot)
        _logger.debug('Changed root to %s.' % newroot)
    except Exception as e:
        _logger.error('Failed to change root to %s: %s' % (newroot, str(e)))
        #
        # need to return environment.
        if root2return > 0:
            os.fchdir(root2return)
            os.chroot('.')
            os.close(root2return)
        raise OciMigrateException('Failed to change root to %s: %s'
                                  % (newroot, str(e)))
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
        _logger.debug('Set path to %s' % newpath)
        return root2return, currentpath
    except Exception as e:
        _logger.error('Failed to set path to %s: %s' % (newpath, str(e)))
        raise OciMigrateException('Failed to set path to %s: %s'
                                  % (newpath, str(e)))


def leave_chroot(root2return):
    """
    Leave a chroot environment and return to another one.

    Parameters
    ----------
    root2return: file descriptor
        The file descriptor of the root to return to.

    Returns
    -------
        bool: True on success, raises exception on failure.
    """
    try:
        #
        # leave chroot
        os.fchdir(root2return)
        os.chroot('.')
        os.close(root2return)
        _logger.debug('Left change root environment.')
        return True
    except Exception as e:
        _logger.error('Failed to return from chroot: %s' % str(e))
        OciMigrateException('Failed to return from chroot: %s' % str(e))


def exec_search(file_name, rootdir='/', dirnames=False):
    """
    Find the filename in the rootdir tree.

    Parameters
    ----------
    file_name: str
        The filename to look for.
    rootdir: str
        The directory to start from, default is root.
    dirnames: bool
        If True, also consider directory names.

    Returns
    -------
        str: The full path of the filename if found, None otherwise.
    """
    _logger.debug('Looking for %s in %s' % (file_name, rootdir))
    migrate_tools.result_msg(msg='Looking for %s in %s, might take a while.'
                             % (file_name, rootdir))
    try:
        for path_name, directories, files in os.walk(rootdir):
            # _logger.debug('%s %s %s' % (path_name, directories, files))
            if file_name in files:
                _logger.debug('Found %s'
                              % os.path.join(rootdir, path_name, file_name))
                return os.path.join(rootdir, path_name, file_name)
            if dirnames and file_name in directories:
                _logger.debug('Found %s as directory.'
                              % os.path.join(rootdir, path_name, file_name))
                return os.path.join(rootdir, path_name, file_name)
    except Exception as e:
        _logger.error('Error while looking for %s: %s'
                      % (file_name, str(e)))
        raise OciMigrateException('Error while looking for %s: %s'
                                  % (file_name, str(e)))
    return None


@state_loop(rmmod_max_count)
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
    cmd = ['rmmod']
    cmd.append(module)
    try:
        rmmod_result = subprocess.check_call(cmd, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL,
                                             shell=False)
        if rmmod_result == 0:
            _logger.debug('Successfully removed %s' % module)
        else:
            _logger.error('Error removing %s, exit code %s, ignoring.'
                          % (cmd, str(rmmod_result)))
    except Exception as e:
        _logger.debug('Failed: %s, ignoring.' % str(e))
    #
    # ignoring eventual errors, which will be caused by module already removed.
    return True


@state_loop(qemu_max_count)
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
    pause_msg(cmd)
    try:
         return migrate_tools.run_call_cmd(cmd)
    except Exception as e:
        _logger.error('%s command failed: %s' % (cmd, str(e)))
        raise OciMigrateException('\n%s command failed: %s' % (cmd, str(e)))


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
    _logger.debug('Creating %s.' % dirname)
    try:
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        else:
            _logger.debug('Directory %s already exists' % dirname)
    except Exception as e:
        raise OciMigrateException(str(e))


@state_loop(qemu_max_count)
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
    _logger.debug('Removing directory tree.')
    try:
        shutil.rmtree(dirname)
        return True
    except Exception as e:
        raise OciMigrateException(str(e))


@state_loop(qemu_max_count)
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
    try:
        _logger.debug('running %s' % cmd)
        pause_msg('test nbd devs')
        blkid_res = migrate_tools.run_popen_cmd(cmd).decode('utf-8')
        _logger.debug('success\n%s' % blkid_res)
        return blkid_res
    except Exception as e:
        _logger.error('%s failed: %s' % (cmd, str(e)))
        return None
#        raise OciMigrateException('%s failed: %s' % (cmd, str(e)))


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
    pause_msg(cmd)
    try:
        _logger.debug('running %s' % cmd)
        lsblk_res = migrate_tools.run_popen_cmd(cmd).decode('utf-8')
        _logger.debug('success\n%s' % lsblk_res)
        return lsblk_res
    except Exception as e:
        _logger.error('%s failed: %s' % (cmd, str(e)))
        raise OciMigrateException('%s failed: %s' % (cmd, str(e)))


@state_loop(qemu_max_count)
def create_nbd():
    """
    Load nbd module

    Returns
    -------
        bool: True on succes, False on failure, raise an exception on call
        error.
    """
    cmd = ['modprobe', 'nbd', 'max_part=63']
    try:
        if migrate_tools.run_call_cmd(cmd) == 0:
            return True
        else:
            _logger.critical('Failed to execute %s' % cmd)
            raise OciMigrateException('\nFailed to execute %s' % cmd)
    except Exception as e:
        _logger.critical('Failed: %s' % str(e))
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
    if exec_rmmod(modname):
        return True
    else:
        return False


def get_free_nbd():
    """
    Find first free device name

    Returns
    -------
        str: The free nbd device on success, None otherwise.
    """
    devpath = '/sys/class/block/nbd*'
    try:
        for devname in glob(devpath):
            with open(devname + '/size', 'r') as f:
                sz = f.readline()
                nbdsz = int(sz)
                if nbdsz == 0:
                    freedev = devname.rsplit('/')[-1]
                    return '/dev/' + freedev
    except Exception as e:
        _logger.critical('Failed to screen nbd devices: %s' % str(e))
        raise OciMigrateException('\nFailed to locate a free nbd device, %s'
                                  % str(e))


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
    pause_msg(cmd)
    _logger.debug('%s' % cmd)
    try:
        result = migrate_tools.run_popen_cmd(cmd).decode('utf-8')
        _logger.debug('parted: %s' % result)
        devdata = dict()
        for devx in result.splitlines():
            if 'Model' in devx:
                devdata['Model'] = devx.split(':')[1]
            elif 'Disk' in devx:
                devdata['Disk'] = devx.split(':')[1]
            elif 'Partition Table' in devx:
                devdata['Partition Table'] = devx.split(':')[1]
            else:
                _logger.debug('Ignoring %s' % devx)
        _logger.debug(devdata)
        pause_msg(devdata)
        return devdata
    except Exception as e:
        _logger.error('Failed to collect parted %s device data: %s'
                      % (devname, str(e)))
        return None


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
    _logger.debug('%s' % cmd)
    pause_msg(cmd)
    try:
        result = migrate_tools.run_popen_cmd(cmd).decode('utf-8')
        partdata = dict()
        for devx in result.split('\n'):
            if devx.startswith(devname):
                key = devx.split(':')[0].strip()
                migrate_tools.result_msg(msg='sfdisk partition %s' % key)
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
                        _logger.debug('unrecognised item: %s' % val)
                partdata[key] = thispart
        _logger.debug(partdata)
        return partdata
    except Exception as e:
        _logger.error('Failed to collect sfdisk %s partition data: %s'
                      % (devname, str(e)))
        return None


@state_loop(3)
def mount_imgfn(imgname):
    """
    Link vm image with an nbd device.

    Parameters
    ----------
    imgname: str
        Full path of the image file.

    Returns
    -------
        str: Device name on success, raises an exception otherwise.
    """
    #
    # create nbd devices
    migrate_tools.result_msg(msg='Load nbd')
    if not create_nbd():
        raise OciMigrateException('Failed ot load nbd module')
    else:
        _logger.debug('nbd module loaded')
    #
    # find free nbd device
    migrate_tools.result_msg(msg='Find free nbd device')
    devpath = get_free_nbd()
    _logger.debug('Device %s is free.' % devpath)
    #
    # link img with first free nbd device
    migrate_tools.result_msg(msg='Mount image %s' % imgname, result=True)
    _, clmns = os.popen('stty size', 'r').read().split()
    try:
        mountwait = migrate_tools.ProgressBar(int(clmns), 0.2,
                                              progress_chars=['mounting image'])
        mountwait.start()
        qemucmd = ['-c', devpath, imgname]
        pause_msg(qemucmd)
        qemunbd_ret = exec_qemunbd(qemucmd)
        if qemunbd_ret == 0:
            time.sleep(5)
            _logger.debug('qemu-nbd %s succeeded' % qemucmd)
            return devpath
        else:
            _logger.critical('\nFailed to create nbd devices: %d'
                        % qemunbd_ret)
            raise Exception('Failed to create nbd devices: %d'
                            % qemunbd_ret)
    except NoSuchCommand:
        _logger.critical('qemu-nbd does not exist')
        raise NoSuchCommand('qemu-nbd does not exist')
    except Exception as e:
        _logger.critical('\nSomething wrong with creating nbd devices: %s'
                         % str(e))
        raise OciMigrateException('Unable to create nbd devices: %s' % str(e))
    finally:
        if migrate_tools.isthreadrunning(mountwait):
            mountwait.stop()


@state_loop(3)
def unmount_imgfn(devname):
    """
    Unlink a device.

    Parameters
    ----------
    devname: str
        The device name

    Returns
    -------
        bool: True on succes, raise an exception otherwise.
    """
    try:
        #
        # release device
        qemucmd = ['-d', devname]
        pause_msg(qemucmd)
        qemunbd_ret = exec_qemunbd(qemucmd)
        if qemunbd_ret == 0:
            _logger.debug('qemu-nbd %s succeeded: %d'
                          % (qemucmd, qemunbd_ret))
        else:
            raise Exception('%s returned %d' % (qemucmd, qemunbd_ret))
        #
        # clear lvm cache, if necessary.
        if exec_pvscan():
            _logger.debug('lvm cache updated')
        else:
            _logger.error('Failed to clear LVM cache.')
            raise OciMigrateException('Failed to clear LVM cache.')
        #
        # remove nbd module
        if not rm_nbd():
            raise OciMigrateException('Failed to remove nbd module.')
        else:
            _logger.debug('Successfully removed nbd module.')
    except Exception as e:
        _logger.critical('Something wrong with removing nbd devices: %s'
                         % str(e))
        raise OciMigrateException('\nSomething wrong with removing nbd '
                                  'devices: %s' % str(e))
    return True


@state_loop(3)
def mount_partition(devname, mountpoint=None):
    """
    Create the mountpoint /mnt/<last part of device specification> and mount a
    partition on on this mountpoint.

    Parameters
    ----------
    devname: str
        The full path of the device.
    mountpoint: str
        The mountpoint, will be generated if not provided.

    Returns
    -------
        str: The mounted partition on Success, None otherwise.
    """
    #
    # create mountpoint /mnt/<devname> if not specified.
    if mountpoint is None:
        mntpoint = loopback_root + '/' + devname.rsplit('/')[-1]
        _logger.debug('Loopback mountpoint: %s' % mntpoint)
        try:
            if exec_mkdir(mntpoint):
                _logger.debug('Mountpoint: %s created.' % mntpoint)
        except Exception as e:
            _logger.critical('Failed to create mountpoint %s: %s'
                             % (mntpoint, str(e)))
            raise OciMigrateException('Failed to create mountpoint %s: %s'
                                      % (mntpoint, str(e)))
    else:
        mntpoint = mountpoint
    #
    # actual mount
    cmd = ['mount', devname, mntpoint]
    pause_msg(cmd)
    _, clmns = os.popen('stty size', 'r').read().split()
    try:
        mountpart = migrate_tools.ProgressBar(int(clmns), 0.2,
                                              progress_chars=['mount %s' % devname])
        mountpart.start()
        _logger.debug('command: %s' % cmd)
        cmdret = migrate_tools.run_call_cmd(cmd)
        if cmdret == 0:
            _logger.debug('%s mounted on %s.' % (devname, mntpoint))
            return mntpoint
        else:
            raise Exception('Mount %s failed: %d' % (devname, cmdret))
    except Exception as e:
        #
        # mount failed, need to remove mountpoint.
        _logger.critical('failed to mount %s: %s' % (devname, str(e)))
        if mountpoint is None:
            if exec_rmdir(mntpoint):
                _logger.debug('%s removed' % mntpoint)
            else:
                _logger.critical('Failed to remove mountpoint %s' % mntpoint)
    finally:
        if migrate_tools.isthreadrunning(mountpart):
            mountpart.stop()

    return None


def find_os_specific(ostag):
    """
    Look for the os type specific code.

    Parameters
    ----------
    ostag: str
        The os type id.

    Returns
    -------
        str: The module name on success, None otherwise.
    """
    module = None
    package_name = module_home
    pkg = __import__(package_name)
    path = os.path.dirname(sys.modules.get(package_name).__file__)
    thismodule = os.path.splitext(
        os.path.basename(sys.modules[__name__].__file__))[0]
    _logger.debug('Path: %s' % path)
    _logger.debug('ostag: %s' % ostag)
    _logger.debug('This module: %s' % sys.modules[__name__].__file__)
    try:
        for _, module_name, _ in pkgutil.iter_modules([path]):
            #
            # find os_type_tag in files, contains a comma separted list of
            # supported os id's
            _logger.debug('module_name: %s' % module_name)
            if module_name != thismodule:
                modulefile = path + '/' + module_name + '.py'
                if os.path.isfile(modulefile):
                    with open(modulefile, 'r') as f:
                        for fline in f:
                            if '_os_type_tag_csl_tag_type_os_' in fline.strip():
                                _logger.debug('Found os_type_tag in %s.'
                                              % module_name)
                                _logger.debug('In line:\n  %s' % fline)
                                if ostag in \
                                        re.sub("[ ']", "", fline).split('=')[1].split(','):
                                    _logger.debug('Found ostag in %s.' % module_name)
                                    module = module_name
                                else:
                                    _logger.debug('ostag not found in %s.' % module_name)
                                break
                else:
                    _logger.debug('No file found for module %s' % module_name)
    except Exception as e:
        _logger.critical('Failed to locate the OS type specific module: %s'
                         % str(e))
    return module


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
    pseudodict = {'proc' : ['-t', 'proc', 'none', '%s/proc' % rootdir],
                  'dev'  : ['-o', 'bind', '/dev', '%s/dev' % rootdir],
                  'sys'  : ['-o', 'bind', '/sys', '%s/sys' % rootdir]}

    pseudomounts = []
    _logger.debug('Mounting: %s' % pseudodict)
    for dirs, cmd_par in list(pseudodict.items()):
        cmd = ['mount'] + cmd_par
        _logger.debug('Mounting %s' % dirs)
        pause_msg(cmd)
        try:
            _logger.debug('Command: %s' % cmd)
            cmdret = migrate_tools.run_call_cmd(cmd)
            _logger.debug('%s : %d' % (cmd, cmdret))
            if cmdret != 0:
                _logger.error('Failed to %s' % cmd )
                raise Exception('%s Failed: %d' % (cmd, cmdret))
            pseudomounts.append(cmd_par[3])
        except Exception as e:
            _logger.critical('Failed to %s: %s' % (cmd, str(e)))
            raise OciMigrateException('Failed to %s: %s' % (cmd, str(e)))
    return pseudomounts


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
    pause_msg(cmd)
    _logger.debug('Mounting %s' % mountpoint)
    try:
        _, clmns = os.popen('stty size', 'r').read().split()
        mountwait = migrate_tools.ProgressBar(int(clmns), 0.2,
                                              progress_chars=['mounting %s' % mountpoint])
        mountwait.start()
        _logger.debug('Command: %s' % cmd)
        cmdret = migrate_tools.run_call_cmd(cmd)
        _logger.debug('%s returned %d' % (cmd, cmdret))
        if cmdret == 0:
            return True
        else:
            raise Exception('%s failed: %d' % (cmd, cmdret))
    except Exception as e:
        _logger.error('Failed to %s: %s' % (cmd, str(e)))
        return False
    finally:
        if migrate_tools.isthreadrunning(mountwait):
            mountwait.stop()


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
    if os.path.ismount(mountpoint):
        _logger.debug('%s is a mountpoint.' % mountpoint)
    else:
        _logger.debug('%s is not a mountpoint, quitting' % mountpoint)
        return True
    #
    cmd = ['umount', mountpoint]
    pause_msg(cmd)
    try:
        _logger.debug('command: %s' % cmd)
        cmdret = migrate_tools.run_call_cmd(cmd)
        _logger.debug('%s : %d' % (cmd, cmdret))
        if cmdret != 0:
            raise Exception('%s failed: %d' % (cmd, cmdret))
    except Exception as e:
        _logger.error('Failed to %s: %s' % (cmd, str(e)))
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
    _logger.debug('Unmounting %s' % pseudomounts)
    res = True
    for mnt in pseudomounts:
        _logger.debug('Unmount %s' % mnt)
        umount_res = unmount_something(mnt)
        if umount_res:
            _logger.debug('%s successfully unmounted.' % mnt)
        else:
            _logger.error('Failed to unmount %s' % mnt)
            res = False
    return res


def exec_pvscan(devname=None):
    """
    Update the lvm cache.

    Returns
    -------
        bool: True on success, raises an exception on failure.
    """
    if devname is not None:
        cmd = ['pvscan', '--cache', devname]
    else:
        cmd = ['pvscan', '--cache']
    pause_msg(cmd)
    try:
        _logger.debug('command: %s' % cmd)
        cmdret = migrate_tools.run_call_cmd(cmd)
        _logger.debug('Physical volumes scanned on %s: %d' % (devname, cmdret))
        if cmdret != 0:
            _logger.error('Physical volume scan failed.')
            raise Exception('Physical volume scan failed.')
        return True
    except Exception as e:
        #
        # pvscan failed
        _logger.critical('Failed to scan %s for physical volumes: %s'
                         % (devname, str(e)))
        raise OciMigrateException('Failed to scan %s for physical '
                                  'volumes: %s' % (devname, str(e)))


def exec_vgscan():
    """
    Scan the system for (new) volume groups.

    Returns
    -------
        bool: True on success, raises an exeception on failure.
    """
    cmd = ['vgscan', '--verbose']
    pause_msg(cmd)
    try:
        _logger.debug('command: %s' % cmd)
        output = migrate_tools.run_popen_cmd(cmd).decode('utf-8')
        _logger.debug('Volume groups scanned: %s' % str(output))
        return True
    except Exception as e:
        #
        # vgscan failed
        _logger.critical('Failed to scan for volume groups: %s' % str(e))
        raise OciMigrateException('Failed to scan for volume groups: %s'
                                  % str(e))


def exec_lvscan():
    """
    Scan the system for (new) logical volumes.

    Returns
    -------
        dict:  inactive, supposed new, volume groups with list of logical
        volumes on success, raises an exeception on failure.
    """
    cmd = ['lvscan', '--verbose']
    pause_msg(cmd)
    try:
        _logger.debug('command: %s' % cmd)
        output = migrate_tools.run_popen_cmd(cmd).decode('utf-8')
        _logger.debug('Logical volumes scanned: %s' % str(output))
        new_vgs = dict()
        for lvdevdesc in output.splitlines():
            if 'inactive' in lvdevdesc:
                lvarr = re.sub(r"'", "", lvdevdesc).split()
                lvdev = lvarr[1]
                vgarr = re.sub(r"/", " ", lvdev).split()
                vgdev = vgarr[1]
                lvdev = vgarr[2]
                mapperdev = re.sub(r"-", "--", vgdev) \
                            + '-' \
                            + re.sub(r"-", "--", lvdev)
                _logger.debug('vg %s lv %s mapper %s'
                              % (vgdev, lvdev, mapperdev))
                if vgdev not in list(new_vgs.keys()):
                    new_vgs[vgdev] = [(lvdev, mapperdev)]
                else:
                    new_vgs[vgdev].append((lvdev, mapperdev))
                _logger.debug('vg: %s  lv: %s' % (vgdev, lvdev))
        _logger.debug('New logical volumes: %s' % new_vgs)
        return new_vgs
    except Exception as e:
        #
        # vgscan failed
        _logger.critical('Failed to scan for logical volumes: %s' % str(e))
        raise OciMigrateException('Failed to scan for logical volume: %s'
                                  % str(e))


def exec_vgchange(changecmd):
    """
    Execute vgchange command.

    Parameters
    ----------
    changecmd: list
        Parameters for the vgchange command.

    Returns
    -------
        <> : vgchange output.
    """
    cmd = ['vgchange'] + changecmd
    _logger.debug('vgchange command: %s' % cmd)
    pause_msg(cmd)
    try:
        output = migrate_tools.run_popen_cmd(cmd).decode('utf-8')
        _logger.debug('vgchange result: %s' % output)
        return output
    except Exception as e:
        _logger.critical('Failed to execute %s: %s' % (cmd, str(e)))
        raise OciMigrateException('Failed to execute %s: %s' % (cmd, str(e)))


@state_loop(2)
def mount_lvm2(devname):
    """
    Create the mountpoints /mnt/<last part of lvm partitions> and mount the
    partitions on those mountpoints, if possible.

    Parameters
    ----------
    devname: str
        The full path of the device

    Returns
    -------
        list: The list of mounted partitions.
        ?? need to collect lvm2 list this way??
    """
    try:
        _, clmns = os.popen('stty size', 'r').read().split()
        mountwait = migrate_tools.ProgressBar(int(clmns), 0.2,
                                              progress_chars=['mounting lvm'])
        mountwait.start()
        #
        # physical volumes
        if exec_pvscan(devname):
            _logger.debug('pvscan %s succeeded' % devname)
        else:
            _logger.critical('pvscan %s failed' % devname)
        #
        pause_msg('pvscan test')
        #
        # volume groups
        if exec_vgscan():
            _logger.debug('vgscan succeeded')
        else:
            _logger.critical('vgscan failed')
        #
        pause_msg('vgscan test')
        #
        # logical volumes
        vgs = exec_lvscan()
        if vgs is not None:
            _logger.debug('lvscan succeeded: %s' % vgs)
        else:
            _logger.critical('lvscan failed')
        #
        pause_msg('lvscan test')
        #
        # make available
        vgchangeargs = ['--activate', 'y']
        vgchangeres = exec_vgchange(vgchangeargs)
        _logger.debug('vgchange: %s' % vgchangeres)
        #
        pause_msg('vgchangeres test')
        vgfound = False
        if vgchangeres is not None:
            for resline in vgchangeres.splitlines():
                _logger.debug('vgchange line: %s' % resline)
                for vg in list(vgs.keys()):
                    if vg in resline:
                        _logger.debug('vgfound set to True')
                        vgfound = True
                    else:
                        _logger.debug('vg %s not in l' % vg)
            _logger.debug('vgchange: %s, %s' % (vgchangeres, vgfound))
            #
            # for the sake of testing
            pause_msg('vgchangeres test')
        else:
            _logger.critical('vgchange failed')
        return vgs
    except Exception as e:
        _logger.critical('Mount lvm %s failed: %s' % (devname, str(e)))
        raise OciMigrateException('Mount lvm %s failed: %s' % (devname, str(e)))
    finally:
        if migrate_tools.isthreadrunning(mountwait):
            mountwait.stop()


def get_oci_config(section='DEFAULT'):
    """
    Read the oci configuration file.

    Parameters
    ----------
    section: str
        The section from the oci configuration file. DEFAULT is the default.
        (todo: add command line option to use other user/sections)

    Returns
    -------
        dict: the contents of the configuration file as a dictionary.
    """
    _logger.debug('Reading the %s configuration file.'
                  % get_config_data('ociconfigfile'))
    oci_cli_configer = ConfigParser()
    try:
        rf = oci_cli_configer.read(get_config_data('ociconfigfile'))
        sectiondata = dict(oci_cli_configer.items(section))
        _logger.debug('OCI configuration: %s' % sectiondata)
        return sectiondata
    except Exception as e:
        _logger.error('Failed to read OCI configuration %s: %s.'
                      % (get_config_data('ociconfigfile'), str(e)))
        raise OciMigrateException('Failed to read OCI configuration %s: %s.' %
                                  (get_config_data('ociconfigfile'),
                                   str(e)))


def bucket_exists(bucketname):
    """
    Verify if bucketname exits.

    Parameters
    ----------
    bucketname: str
        The bucketname.

    Returns
    -------
        object: The bucket on success, raise an exception otherwise
    """
    _logger.debug('Test bucket %s.' % bucketname)
    path_name = os.getenv('PATH')
    _logger.debug('PATH is %s' % path_name)
    cmd = ['which', 'oci']
    try:
        ocipath = migrate_tools.run_popen_cmd(cmd).decode('utf-8')
        _logger.debug('oci path is %s' % ocipath)
    except Exception as e:
        _logger.error('Cannot find oci anymore: %s' % str(e))
        raise OciMigrateException('Unable to find oci cli, although it has '
                                  'been verified successfully earlier in '
                                  'this process.')
    cmd = ['oci', 'os', 'object', 'list', '--bucket-name', bucketname]
    pause_msg(cmd)
    try:
        bucketresult = migrate_tools.run_popen_cmd(cmd).decode('utf-8')
        _logger.debug('Result: \n%s' % bucketresult)
        return bucketresult
    except Exception as e:
        _logger.debug('Bucket %s does not exists or the authorisation is '
                      'missing: %s.' % (bucketname, str(e)))
        raise OciMigrateException('Bucket %s does not exists or the '
                                  'authorisation is missing: %s.'
                                  % (bucketname, str(e)))


def object_exists(bucket, object_name):
    """
    Verify if the object object_name already exists in the
    object storage.

    Parameters
    ----------
    bucket: object
        The bucket.
    object_name: str
        The object name.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('Testing if %s already exists.' % object_name)
    testresult_json = json.loads(bucket)
    _logger.debug('Result: \n%s', testresult_json)
    if 'data' in testresult_json:
        for res in testresult_json['data']:
            if str(res['name']) == object_name:
                _logger.debug('%s found' % object_name)
                return True
            else:
                _logger.debug('%s not found' % object_name)
    else:
        _logger.debug('Bucket %s is empty.' % bucket)
    return False


def set_default_user(cfgfile, username):
    """
    Update the default user name in the cloud.cfg file.
    Paramaters:
    ----------
        cfgfile: str
            full path of the cloud init config file, yaml format.
        username: str
            name of the default cloud user.

    Returns:
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('Updating cloud.cfg file %s, setting default username to '
                  '%s.' % (cfgfile, username))
    if os.path.isfile(cfgfile):
        _logger.debug('Copy %s %s' % (cfgfile, os.path.split(cfgfile)[0]
                                      + '/bck_'
                                      + os.path.split(cfgfile)[1]
                                      + '_'
                                      + migrate_tools.current_time))
        shutil.copy(cfgfile, os.path.split(cfgfile)[0]
                    + '/bck_'
                    + os.path.split(cfgfile)[1]
                    + '_'
                    + migrate_tools.current_time)
        with open(cfgfile, 'r') as f:
            cloudcfg = yaml.load(f, Loader=yaml.SafeLoader)
        if type(cloudcfg) is dict:
            if 'system_info' in list(cloudcfg.keys()) \
                    and 'default_user' in list(cloudcfg['system_info'].keys()) \
                    and 'name' in list(cloudcfg['system_info']['default_user'].keys()):
                cloudcfg['system_info']['default_user']['name'] = username
                with open(cfgfile, 'w') as f:
                    yaml.dump(cloudcfg, f, width=50)
                _logger.debug('Cloud configuration file %s successfully updated.' % cfgfile)
                return True
            else:
                _logger.debug('No default username found in cloud config file.')
        else:
            _logger.error('Invalid cloud config file.')
    else:
        _logger.error('Cloud config file %s does not exist.' % cfgfile)
    return False


def upload_image(imgname, bucketname, ociname):
    """
    Upload the validated and updated image imgname to the OCI object storage
    bucketname as ociname.

    Parameters
    ----------
    imgname: str
        The on-premise custom image.
    bucketname: str
        The OCI object storage name.
    ociname:
        The OCI image name.

    Returns
    -------
        bool: True on success, raises an exception otherwise.
    """
    _logger.debug('Uploading %s to %s as %s.' % (imgname, bucketname, ociname))
    cmd = ['oci', 'os', 'object', 'put', '--bucket-name',
           bucketname, '--file', imgname, '--name', ociname]
    pause_msg(cmd)
    try:
        uploadresult = migrate_tools.run_popen_cmd(cmd).decode('utf-8')
        _logger.debug('Successfully uploaded %s to %s as %s: %s.'
                     % (imgname, bucketname, ociname, uploadresult))
    except Exception as e:
        _logger.critical('Failed to upload %s to object storage %s as %s: %s.'
                         % (imgname, bucketname, ociname, str(e)))
        raise OciMigrateException('Failed to upload %s to object storage %s '
                                  'as %s: %s.'
                                  % (imgname, bucketname, ociname, str(e)))


def unmount_lvm2(vg):
    """
    Remove logical volume data from system.

    Parameters
    ----------
    vg: dict
        Volume group with list of logical volumes.

    Returns
    -------
        bool: True on Success, exception otherwise.
    """
    try:
        #
        # make unavailable
        # for vg_name in vg.keys():
        for vg_name in list(vg.keys()):
            vgchangeres = exec_vgchange(['--activate', 'n', vg_name])
            _logger.debug('vgchange: %s' % vgchangeres)
        #
        # remove physical volume: clear cache, if necessary
        if exec_pvscan():
            _logger.debug('pvscan clear succeeded')
        else:
            _logger.error('pvscan failed')
    except Exception as e:
        _logger.error('Failed to release lvms %s: %s' % vg, str(e))
        migrate_tools.error_msg('Failed to release lvms %s: %s' % vg, str(e))
        # raise OciMigrateException('Exception raised during release
        # lvms %s: %s' % (vg, str(e)))


@state_loop(5, 2)
def unmount_part(devname):
    """
    Unmount a partition from mountpoint from /mnt/<last part of device
    specification> and remove the mountpoint.

    Parameters
    ----------
    devname: str
        The full path of the device.

    Returns
    -------
        bool
            True on success, False otherwise.
    """
    mntpoint = loopback_root + '/' + devname.rsplit('/')[-1]
    cmd = ['umount', mntpoint]
    pause_msg(cmd)
    try:
        _logger.debug('command: %s' % cmd)
        cmdret = migrate_tools.run_call_cmd(cmd)
        if cmdret == 0:
            _logger.debug('%s unmounted from %s' % (devname, mntpoint))
            #
            # remove mountpoint
            if exec_rmdir(mntpoint):
                _logger.debug('%s removed' % mntpoint)
                return True
            else:
                _logger.critical('Failed to remove mountpoint %s' % mntpoint)
                raise OciMigrateException('Failed to remove mountpoint %s'
                                          % mntpoint)
        else:
            _logger.critical('Failed to unmount %s: %d' % (devname, cmdret))
            console_msg('Failed to unmount %s, error code %d.\n '
                        'Please verify before continuing.'
                        % (devname, cmdret))
            read_yn('Continue?')
    except Exception as e:
        _logger.critical('Failed to unmount %s: %s' % (devname, str(e)))
    return False


def print_header(head):
    """
    Display header for image data component.

    Parameters
    ----------
    head: str
        The header

    Returns
    -------
        No return value.
    """
    migrate_tools.result_msg(msg='\n  %30s\n  %30s' % (head, '-'*30), result=True)


def show_image_data(imgobj):
    """
    Show the collected data about the image.

    Parameters
    ----------
    imgobj: object
        The data about the image.

    Returns
    -------
        No return value.
    """
    print_header('Components collected.')
    for k, v in sorted(imgobj._img_info.items()):
        migrate_tools.result_msg(msg='  %30s' % k, result=True)

    _logger.debug('show data')
    print('\n  %25s\n  %s' % ('Image data:', '-'*60))
    #
    # name
    fnname = '  missing'
    print_header('Image file path.')
    if 'img_name' in imgobj._img_info:
        fnname = imgobj._img_info['img_name']
    migrate_tools.result_msg(msg='  %30s' % fnname, result=True)
    #
    # type
    imgtype = '  missing'
    print_header('Image type.')
    if 'img_type' in imgobj._img_info:
        imgtype = imgobj._img_info['img_type']
    migrate_tools.result_msg(msg='  %30s' % imgtype, result=True)
    #
    # size
    imgsizes = '    physical: missing data\n    logical:  missing data'
    print_header('Image size:')
    if 'img_size' in imgobj._img_info:
        imgsizes = '    physical: %8.2f GB\n      logical:  %8.2f GB' \
                   % (imgobj._img_info['img_size']['physical'],
                      imgobj._img_info['img_size']['logical'])
    migrate_tools.result_msg(msg='%s' % imgsizes, result=True)
    #
    # header
    if 'img_header' in imgobj._img_info:
        try:
            imgobj.show_header()
        except Exception as e:
            migrate_tools.result_msg(msg='Failed to show the image hadear: %s'
                                     % str(e), result=True)
    else:
        migrate_tools.result_msg(msg='\n  Image header data missing.', result=True)
    #
    # mbr
    mbr = '  missing'
    print_header('Master Boot Record.')
    if 'mbr' in imgobj._img_info:
        if 'hex' in imgobj._img_info['mbr']:
            mbr = imgobj._img_info['mbr']['hex']
        migrate_tools.result_msg(msg='%s' % mbr, result=True)
    #
    # partition table
        print_header('Partiton Table.')
        parttabmissing = '  Partition table data is missing.'
        if 'partition_table' in imgobj._img_info['mbr']:
            show_partition_table(imgobj._img_info['mbr']['partition_table'])
        else:
            migrate_tools.result_msg(msg=parttabmissing, result=True)
    #
    # parted data
    print_header('Parted data.')
    parteddata = '  Parted data is missing.'
    if 'parted' in imgobj._img_info:
        show_parted_data(imgobj._img_info['parted'])
    else:
        migrate_tools.result_msg(msg='%s' % parteddata, result=True)
    #
    # partition data
    print_header('Partition Data.')
    partdata = '  Partition data is missing.'
    if 'partitions' in imgobj._img_info:
        show_partition_data(imgobj._img_info['partitions'])
    else:
        migrate_tools.result_msg(msg='%s' % partdata, result=True)
    #
    # grub config data
    print_header('Grub configuration data.')
    grubdat = '  Grub configuration data is missing.'
    if 'grubdata' in imgobj._img_info:
        show_grub_data(imgobj._img_info['grubdata'])
    else:
        migrate_tools.result_msg(msg='%s' % grubdat, result=True)
    #
    # logical volume data
    print_header('Logical Volume data.')
    lvmdata = '  Logical Volume data is missing.'
    if 'volume_groups' in imgobj._img_info:
        if imgobj._img_info['volume_groups']:
            show_lvm2_data(imgobj._img_info['volume_groups'])
    else:
        migrate_tools.result_msg(msg=lvmdata, result=True)
    #
    # various data:
    print_header('Various data.')
    if 'bootmnt' in imgobj._img_info:
        migrate_tools.result_msg(msg='  %30s: %s mounted on %s'
                                 % ('boot', imgobj._img_info['bootmnt'][0],
                                    imgobj._img_info['bootmnt'][1]),
                                 result=True)
    if 'rootmnt' in imgobj._img_info:
        migrate_tools.result_msg(msg='  %30s: %s mounted on %s'
                                 % ('root', imgobj._img_info['rootmnt'][0],
                                    imgobj._img_info['rootmnt'][1]),
                                 result=True)
    if 'boot_type' in imgobj._img_info:
        migrate_tools.result_msg(msg='  %30s: %-30s'
                                 % ('boot type:', imgobj._img_info['boot_type']),
                                 result=True)
    #
    # fstab
    print_header('fstab data.')
    fstabmiss = '  fstab data is missing.'
    if 'fstab' in imgobj._img_info:
        show_fstab(imgobj._img_info['fstab'])
    else:
        migrate_tools.result_msg(msg=fstabmiss, result=True)
    #
    # network
    # print_header('Network configuration data.')
    # networkmissing = '  Network configuration data is missing.'
    # if 'network' in imgobj._img_info:
    #     show_network_data(imgobj._img_info['network'])
    # else:
    #     migrate_tools.result_msg(msg=networkmissing, result=True)
    #
    # os release data
    print_header('Operating System information.')
    osinfomissing = '  Operation System information is missing.'
    if 'osinformation' in imgobj._img_info:
        for k in sorted(imgobj._img_info['osinformation']):
            migrate_tools.result_msg(msg='  %30s : %-30s'
                                     % (k, imgobj._img_info['osinformation'][k]),
                                     result=True)
    else:
        migrate_tools.result_msg(msg=osinfomissing, result=True)
    #
    # oci configuration
    print_header('OCI client configuration.')
    ociconfmissing = '  OCI client configuration not found.'
    if 'oci_config' in imgobj._img_info:
        for k in sorted(imgobj._img_info['oci_config']):
            migrate_tools.result_msg(msg='  %30s : %-30s'
                                     % (k, imgobj._img_info['oci_config'][k]),
                                     result=True)
    else:
        migrate_tools.result_msg(msg=ociconfmissing, result=True)


def show_partition_table(table):
    """
    Show the relevant data of the partition table.

    Parameters
    ----------
    table: list of dict.
        The partition table data.

    Returns
    -------
        No return value.
    """
    migrate_tools.result_msg(msg='  %2s %5s %16s %32s'
                             % ('nb', 'boot', 'type', 'data'), result=True)
    migrate_tools.result_msg(msg='  %2s %5s %16s %32s'
                             % ('-'*2, '-'*5, '-'*16, '-'*32), result=True)
    for i in range(0, 4):
        if table[i]['boot']:
            bootflag = 'YES'
        else:
            bootflag = ' NO'
        migrate_tools.result_msg(msg='  %02d %5s %16s %32s'
                                 % (i, bootflag,
                                    table[i]['type'],
                                    table[i]['entry']),
                                 result=True)


def show_img_header(headerdata):
    """
    Show the header data.

    Parameters
    ----------
    headerdata: dict
        Dictionary containing data extracted from the image header; contents
        is dependent form image type.

    Returns
    -------
        No return value.
    """
    migrate_tools.result_msg(msg='\n  %30s\n  %30s'
                             % ('Image header:', '-'*30), result=True)
    for k, v in sorted(headerdata):
        migrate_tools.result_msg(msg='  %30s : %s' % (k, v), result=True)


def show_fstab(fstabdata):
    """
    Show the relevant data in the fstab file.

    Parameters
    ----------
    fstabdata: list of lists, one list per fstab line.

    Returns
    -------
        No return value.
    """
    for line in fstabdata:
        migrate_tools.result_msg(
            msg='%60s %20s %8s %20s %2s %2s'
                % (line[0], line[1], line[2], line[3], line[4], line[5]),
            result=True)


def show_grub_data(grublist):
    """
    Show the relevant data in the grub config file.

    Parameters
    ----------
    grublist: list of dictionaries, 1 per boot section, containing grub
    lines as list.

    Returns
    -------
        No return value.
    """
    for entry in grublist:
        _logger.debug('%s' % entry)
        for grubkey in entry:
            # print entry[grubkey]
            for grubline in entry[grubkey]:
                migrate_tools.result_msg(msg=grubline, result=True)
            migrate_tools.result_msg(msg='\n', result=True)


def show_parted_data(parted_dict):
    """
    Show the data collected by the parted command.

    Parameters
    ----------
    parted_dict: dict
        The data.

    Returns
    -------
        No return value.
    """
    for k, v in sorted(parted_dict.items()):
        migrate_tools.result_msg(msg='%30s : %s' % (k, v), result=True)
    migrate_tools.result_msg(msg='\n', result=True)


def show_lvm2_data(lvm2_data):
    """
    Show the collected lvm2 data.

    Parameters
    ----------
    lvm2_data: dict
        Dictionary containing the recognised volume groups and logical volumes.

    Returns
    -------
        No return value.
    """
    for k, v in sorted(lvm2_data.items()):
        migrate_tools.result_msg(msg='\n  Volume Group: %s:' % k, result=True)
        for t in v:
            migrate_tools.result_msg(msg='%40s : %-30s' % (t[0], t[1]), result=True)
    migrate_tools.result_msg(msg='\n', result=True)


def show_partition_data(partition_dict):
    """
    Show the collected data on the partitions of the image file.

    Parameters
    ----------
    partition_dict: dict
        The data.

    Returns
    -------
        No return value
    """
    for k, v in sorted(partition_dict.items()):
        migrate_tools.result_msg(msg='%30s :\n%s'
                                 % ('partition %s' % k, '-'*60), result=True)
        for x, y in sorted(v.items()):
            migrate_tools.result_msg(msg='%30s : %s' % (x, y), result=True)
        migrate_tools.result_msg(msg='\n', result=True)
    migrate_tools.result_msg(msg='\n', result=True)


def show_network_data(networkdata):
    """
    Show the collected data on the network interfaces.

    Parameters
    ----------
    networkdata: dict
        Dictionary of dictionaries containing the network configuration data.

    Returns
    -------
        No return value.
    """
    for nic, nicdata in sorted(networkdata.items()):
        migrate_tools.result_msg(msg='  %20s:' % nic, result=True)
        for k, v in sorted(nicdata.items()):
            migrate_tools.result_msg(msg='  %30s = %s' % (k, v), result=True)


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
        _logger.error('exception: %s' % str(e))
    return hexdata
