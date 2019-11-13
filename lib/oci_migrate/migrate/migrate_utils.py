# #!/usr/bin/env python

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module containing generic data and code with respect to the migration to the
Oracle Cloud Infrastructure.
"""
import json
import logging
import os
import pkgutil
import re
import subprocess
import sys
import time
from functools import wraps
from glob import glob

import six
from oci_migrate.migrate import configdata
from oci_migrate.migrate import gen_tools
from oci_migrate.migrate.exception import NoSuchCommand
from oci_migrate.migrate.exception import OciMigrateException
from six.moves import configparser

logger = logging.getLogger('oci-image-migrate')
ConfigParser = configparser.ConfigParser

gigabyte = 2**30
rmmod_max_count = 4
qemu_max_count = 2
#
# the root for loopback mounts of partitions and logical volumes.
loopback_root = '/mnt'
#
# the root of the migrate related packages.
module_home = 'oci_migrate.migrate'

# global verboseflag


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
                logger.debug('State loop %d' % i)
                try:
                    funcret = func(*args, **kwargs)
                    return funcret
                except Exception as e:
                    logger.debug('Failed, sleeping for %d sec: %s'
                                 % (intsec, str(e)))
                    if i == maxloop - 1:
                        raise OciMigrateException('State Loop exhausted: %s'
                                                  % str(e))
                    time.sleep(intsec)
        return loop_func
    return wrap


def exec_df():
    """
    Run df command -- for testing purposes.

    Returns
    -------
        No return value.
    """
    cmd = ['df', '-h']
    df_res = gen_tools.run_popen_cmd(cmd)
    gen_tools.result_msg(mag='\n%s' % df_res)


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
        logger.debug('Changed root to %s.' % newroot)
    except Exception as e:
        logger.error('Failed to change root to %s: %s' % (newroot, str(e)))
        #
        # need to return env.
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
        logger.debug('Set path to %s' % newpath)
        return root2return, currentpath
    except Exception as e:
        logger.error('Failed to set path to %s: %s' % (newpath, str(e)))
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
        logger.debug('Left change root environment.')
        return True
    except Exception as e:
        logger.error('Failed to return from chroot: %s' % str(e))
        OciMigrateException('Failed to return from chroot: %s' % str(e))


def exec_find(thisfile, rootdir='/'):
    """
    find the filename in the rootdir tree.

    Parameters
    ----------
    thisfile: str
        The filename to look for.
    rootdir: str
        The directory to start from, default is root.

    Returns
    -------
        str: The full path of the filename if found, None otherwise.
    """
    logger.debug('Looking for %s in %s' % (thisfile, rootdir))
    gen_tools.result_msg(msg='Looking for %s in %s, might take a while.'
                             % (thisfile, rootdir))
    try:
        for thispath, directories, files in os.walk(rootdir):
            # logger.debug('%s %s %s' % (thispath, directories, files))
            if thisfile in files:
                logger.debug('Found %s'
                             % os.path.join(rootdir, thispath, thisfile))
                return os.path.join(rootdir, thispath, thisfile)
    except Exception as e:
        logger.error('Error while looking for %s: %s'
                     % (thisfile, str(e)))
        raise OciMigrateException('Error while looking for %s: %s'
                                  % (thisfile, str(e)))
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
        rmmod_result = subprocess.check_call(cmd, stdout=open(os.devnull, 'wb'),
                                             stderr=open(os.devnull, 'wb'),
                                             shell=False)
        if rmmod_result == 0:
            logger.debug('Successfully removed %s' % module)
        else:
            logger.error('Error removing %s, exit code %s, ignoring.'
                         % (cmd, str(rmmod_result)))
    except Exception as e:
        logger.error('Failed: %s, ignoring.' % str(e))
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
        int: 0 on success, non-zero return value otherwise.

    """
    cmd = ['qemu-nbd'] + qemunbd_args
    gen_tools.pause_msg(cmd)
    try:
        qemunbd_res = gen_tools.run_popen_cmd(cmd)
        logger.debug('success: %s' % qemunbd_res)
        return qemunbd_res
    except Exception as e:
        logger.error('%s command failed: %s' % (cmd, str(e)))
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
    cmd = ['mkdir', '-p']
    cmd.append(dirname)
    logger.debug('%s' % cmd)
    try:
        if gen_tools.run_call_cmd(cmd) == 0:
            return True
        return False
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
    cmd = ['rmdir']
    cmd.append(dirname)
    logger.debug('%s' % cmd)
    try:
        if gen_tools.run_call_cmd(cmd) == 0:
            return True
        return False
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
        logger.debug('running %s' % cmd)
        gen_tools.pause_msg('test nbd devs')
        blkid_res = gen_tools.run_popen_cmd(cmd)
        logger.debug('success\n%s' % blkid_res)
        return blkid_res
    except Exception as e:
        logger.error('%s failed: %s' % (cmd, str(e)))
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
    gen_tools.pause_msg(cmd)
    try:
        logger.debug('running %s' % cmd)
        lsblk_res = gen_tools.run_popen_cmd(cmd)
        logger.debug('success\n%s' % lsblk_res)
        return lsblk_res
    except Exception as e:
        logger.error('%s failed: %s' % (cmd, str(e)))
        raise OciMigrateException('%s failed: %s' % (cmd, str(e)))


@state_loop(qemu_max_count)
def create_nbd():
    """
    Load nbd module

    Returns
    -------
        bool: True on succes, False on failure.
    """
    cmd = ['modprobe', 'nbd', 'max_part=63']
    try:
        if gen_tools.run_call_cmd(cmd) == 0:
            return True
        else:
            logger.critical('Failed to execute %s' % cmd)
            raise OciMigrateException('\nFailed to execute %s' % cmd)
    except Exception as e:
        logger.critical('Failed: %s' % str(e))
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
        logger.critical('Failed to screen nbd devices: %s' % str(e))
        raise OciMigrateException('\nFailed to locate a free nbd device, %s'
                                  % str(e))


def get_nameserver():
    """
    Find out if a nameserver is defined.

    Returns
    -------
        str: The name server address on success, None otherwise.
    """
    cmd = ['nslookup', 'www.oracle.com']
    nameserver = None
    try:
        result = gen_tools.run_popen_cmd(cmd)
        logger.debug('ns data: %s' % result)
        for resx in result.splitlines():
            if 'Server' in resx:
                nameserver = resx.split(':')[1]
                break
        return nameserver
    except Exception as e:
        logger.error('Failed to identify nameserver: %s' % str(e))
        raise OciMigrateException('Failed to identify nameserver: %s' % str(e))


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
    gen_tools.pause_msg(cmd)
    logger.debug('%s' % cmd)
    try:
        result = gen_tools.run_popen_cmd(cmd)
        logger.debug('parted: %s' % result)
        devdata = dict()
        for devx in result.splitlines():
            if 'Model' in devx:
                devdata['Model'] = devx.split(':')[1]
            elif 'Disk' in devx:
                devdata['Disk'] = devx.split(':')[1]
            elif 'Partition Table' in devx:
                devdata['Partition Table'] = devx.split(':')[1]
            else:
                logger.debug('Ignoring %s' % devx)
        logger.debug(devdata)
        gen_tools.pause_msg(devdata)
        return devdata
    except Exception as e:
        logger.error('Failed to collect parted %s device data: %s'
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
    logger.debug('%s' % cmd)
    gen_tools.pause_msg(cmd)
    try:
        result = gen_tools.run_popen_cmd(cmd)
        partdata = dict()
        for devx in result.split('\n'):
            if devx.startswith(devname):
                key = devx.split(':')[0].strip()
                gen_tools.result_msg(msg='sfdisk partition %s' % key)
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
                        logger.debug('unrecognised item: %s' % val)
                partdata[key] = thispart
        logger.debug(partdata)
        return partdata
    except Exception as e:
        logger.error('Failed to collect sfdisk %s partition data: %s'
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
    gen_tools.result_msg(msg='Load nbd')
    if not create_nbd():
        raise OciMigrateException('Failed ot load nbd module')
    else:
        logger.debug('nbd module loaded')
    #
    # find free nbd device
    gen_tools.result_msg(msg='Find free nbd device')
    devpath = get_free_nbd()
    logger.debug('Device %s is free.' % devpath)
    #
    # link img with first free nbd device
    gen_tools.result_msg(msg='Mount image %s' % imgname, result=True)
    try:
        qemucmd = ['-c', devpath, imgname]
        gen_tools.pause_msg(qemucmd)
        z = exec_qemunbd(qemucmd)
        gen_tools.thissleep(4, 'Mounting %s ' % imgname)
        logger.debug('qemu-nbd %s succeeded' % qemucmd)
        return devpath
    except NoSuchCommand:
        logger.critical('qemu-nbd does not exist')
        raise NoSuchCommand('qemu-nbd does not exist')
    except Exception as e:
        logger.critical('\nSomething wrong with creating nbd devices: %s'
                        % str(e))
        raise OciMigrateException('Unable to create nbd devices: %s' % str(e))


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
        gen_tools.pause_msg(qemucmd)
        z = exec_qemunbd(qemucmd)
        logger.debug('qemu-nbd %s succeeded: %s' % (qemucmd, str(z)))
        #
        # clear lvm cache, if necessary.
        if exec_pvscan():
            logger.debug('lvm cache updated')
        else:
            logger.error('Failed to clear LVM cache.')
            raise OciMigrateException('Failed to clear LVM cache.')
        #
        # remove nbd module
        if not rm_nbd():
            raise OciMigrateException('Failed to remove nbd module.')
        else:
            logger.debug('Successfully removed nbd module.')
    except Exception as e:
        logger.critical('Something wrong with removing nbd '
                        'devices: %s' % str(e))
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
        logger.debug('Loopback mountpoint: %s' % mntpoint)
        try:
            if exec_mkdir(mntpoint):
                logger.debug('Mountpoint: %s created.' % mntpoint)
        except Exception as e:
            logger.critical('Failed to create mountpoint %s: %s'
                            % (mntpoint, str(e)))
            raise OciMigrateException('Failed to create mountpoint %s: %s'
                                      % (mntpoint, str(e)))
    else:
        mntpoint = mountpoint
    #
    # actual mount
    cmd = ['mount', devname, mntpoint]
    gen_tools.pause_msg(cmd)
    try:
        logger.debug('command: %s' % cmd)
        output = gen_tools.run_popen_cmd(cmd)
        logger.debug('%s mounted on %s: %s' % (devname, mntpoint, str(output)))
        return mntpoint
    except Exception as e:
        #
        # mount failed, need to remove mountpoint.
        logger.critical('failed to mount %s: %s' % (devname, str(e)))
        if mountpoint is None:
            if exec_rmdir(mntpoint):
                logger.debug('%s removed' % mntpoint)
            else:
                logger.critical('Failed to remove mountpoint %s' % mntpoint)
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
    logger.debug('Path: %s' % path)
    logger.debug('ostag: %s' % ostag)
    logger.debug('This module: %s' % sys.modules[__name__].__file__)
    try:
        for _, module_name, _ in pkgutil.iter_modules([path]):
            #
            # find os_type_tag in files, contains a comma separted list of
            # supported os id's
            logger.debug('module_name: %s' % module_name)
            if module_name != thismodule:
                modulefile = path + '/' + module_name + '.py'
                if os.path.isfile(modulefile):
                    with open(modulefile, 'rb') as f:
                        for l in f:
                            if '_os_type_tag_csl_tag_type_os_' in l.strip():
                                logger.debug('Found os_type_tag in %s.'
                                             % module_name)
                                logger.debug('In line:\n  %s' % l)
                                if ostag in re.sub("[ ']", "", l).split('=')[1].split(','):
                                    logger.debug('Found ostag in %s.'
                                                 % module_name)
                                    module = module_name
                                else:
                                    logger.debug('ostag not found in %s.'
                                                 % module_name)
                                break
                else:
                    logger.debug('No file found for module %s' % module_name)
    except Exception as e:
        logger.critical('Failed to locate the OS type specific module: %s'
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
    logger.debug('Mounting: %s' % pseudodict)
    for dirs, cmd_par in six.iteritems(pseudodict):
        cmd = ['mount'] + cmd_par
        logger.debug('Mounting %s' % dirs)
        gen_tools.pause_msg(cmd)
        try:
            logger.debug('Command: %s' % cmd)
            output = gen_tools.run_popen_cmd(cmd)
            logger.debug('%s : %s' % (cmd, str(output)))
            pseudomounts.append(cmd_par[3])
        except Exception as e:
            logger.critical('Failed to %s: %s' % (cmd, str(e)))
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
    gen_tools.pause_msg(cmd)
    logger.debug('Mounting %s' % mountpoint)
    try:
        logger.debug('Command: %s' % cmd)
        output = gen_tools.run_popen_cmd(cmd)
        logger.debug('%s success: %s' % (cmd, str(output)))
        return True
    except Exception as e:
        logger.error('Failed to %s: %s' % (cmd, str(e)))
        return False


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
        logger.debug('%s is a mountpoint.' % mountpoint)
    else:
        logger.debug('%s is not a mountpoint, quitting' % mountpoint)
        return True
    #
    cmd = ['umount', mountpoint]
    gen_tools.pause_msg(cmd)
    try:
        logger.debug('command: %s' % cmd)
        output = gen_tools.run_popen_cmd(cmd)
        logger.debug('%s : %s' % (cmd, str(output)))
    except Exception as e:
        logger.error('Failed to %s: %s' % (cmd, str(e)))
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
    logger.debug('Unmounting %s' % pseudomounts)
    res = True
    for mnt in pseudomounts:
        logger.debug('Unmount %s' % mnt)
        umount_res = unmount_something(mnt)
        if umount_res:
            logger.debug('%s successfully unmounted.' % mnt)
        else:
            logger.error('Failed to unmount %s' % mnt)
            res = False
    return res


def exec_pvscan(devname=None):
    """
    Update the lvm cache.

    Returns
    -------
        bool: True on success, raises an exeception on failure.
    """
    if devname is not None:
        cmd = ['pvscan', '--cache', devname]
    else:
        cmd = ['pvscan', '--cache']
    gen_tools.pause_msg(cmd)
    try:
        logger.debug('command: %s' % cmd)
        output = gen_tools.run_popen_cmd(cmd)
        logger.debug('Physical volumes scanned on %s: %s'
                     % (devname, str(output)))
        return True
    except Exception as e:
        #
        # pvscan failed
        logger.critical('Failed to scan %s for physical '
                        'volumes: %s' % (devname, str(e)))
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
    gen_tools.pause_msg(cmd)
    try:
        logger.debug('command: %s' % cmd)
        output = gen_tools.run_popen_cmd(cmd)
        logger.debug('Volume groups scanned: %s' % str(output))
        return True
    except Exception as e:
        #
        # vgscan failed
        logger.critical('Failed to scan for volume groups: %s' % str(e))
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
    gen_tools.pause_msg(cmd)
    try:
        logger.debug('command: %s' % cmd)
        output = gen_tools.run_popen_cmd(cmd)
        logger.debug('Logical volumes scanned: %s' % str(output))
        new_vgs = dict()
        for lvdevdesc in output.splitlines():
            if 'inactive' in lvdevdesc:
                lvarr = re.sub(r"'", "", lvdevdesc).split()
                lvdev = lvarr[1]
                vgarr = re.sub(r"/", " ", lvdev).split()
                vgdev = vgarr[1]
                lvdev = vgarr[2]
                # mapperdev = re.sub(r"-", "--", vgdev) + '-' + vgarr[2]
                mapperdev = re.sub(r"-", "--", vgdev) \
                            + '-' \
                            + re.sub(r"-", "--", lvdev)
                logger.debug('vg %s lv %s mapper %s'
                             % (vgdev, lvdev, mapperdev))
                if vgdev not in new_vgs.keys():
                    new_vgs[vgdev] = [(lvdev, mapperdev)]
                else:
                    new_vgs[vgdev].append((lvdev, mapperdev))
                logger.debug('vg: %s  lv: %s' % (vgdev, lvdev))
        logger.debug('New logical volumes: %s' % new_vgs)
        return new_vgs
    except Exception as e:
        #
        # vgscan failed
        logger.critical('Failed to scan for logical volumes: %s' % str(e))
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

    """
    cmd = ['vgchange'] + changecmd
    logger.debug('vgchange command: %s' % cmd)
    gen_tools.pause_msg(cmd)
    try:
        output = gen_tools.run_popen_cmd(cmd)
        logger.debug('vgchange result: %s' % output)
        return output
    except Exception as e:
        logger.critical('Failed to execute %s: %s' % (cmd, str(e)))
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
    logger.debug('Device %s contains an lvm2' % devname)

    try:
        #
        # physical volumes
        if exec_pvscan(devname):
            logger.debug('pvscan %s succeeded' % devname)
        else:
            logger.critical('pvscan %s failed' % devname)
        #
        # for the sake of testing
        # gen_tools.pause_msg('pvscan test')
        #
        # volume groups
        if exec_vgscan():
            logger.debug('vgscan succeeded')
        else:
            logger.critical('vgscan failed')
        #
        # for the sake of testing
        # gen_tools.pause_msg('vgscan test')
        #
        # logical volumes
        vgs = exec_lvscan()
        if vgs is not None:
            logger.debug('lvscan succeeded: %s' % vgs)
        else:
            logger.critical('lvscan failed')
        #
        # for the sake of testing
        # gen_tools.pause_msg('lvscan test')
        #
        # make available
        vgchangeargs = ['--activate', 'y']
        vgchangeres = exec_vgchange(vgchangeargs)
        logger.debug('vgchange: %s' % vgchangeres)
        #
        # for the sake of testing
        # gen_tools.pause_msg('vgchangeres test')
        vgfound = False
        if vgchangeres is not None:
            for l in vgchangeres.splitlines():
                logger.debug('vgchange line: %s' % l)
                for vg in vgs.keys():
                    if vg in l:
                        logger.debug('vgfound set to True')
                        vgfound = True
                    else:
                        logger.debug('vg %s not in l' % vg)
            logger.debug('vgchange: %s, %s' % (vgchangeres, vgfound))
            #
            # for the sake of testing
            # gen_tools.pause_msg('vgchangeres test')
        else:
            logger.critical('vgchange failed')
        return vgs
    except Exception as e:
        logger.critical('Mount lvm %s failed: %s' % (devname, str(e)))
        raise OciMigrateException('Mount lvm %s failed: %s' % (devname, str(e)))


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
    logger.debug('Reading the %s configuration file.' % configdata.ociconfigfile)
    thisparser = ConfigParser()
    try:
        rf = thisparser.read(configdata.ociconfigfile)
        sectiondata = dict(thisparser.items(section))
        logger.debug('OCI configuration: %s' % sectiondata)
        return sectiondata
    except Exception as e:
        logger.error('Failed to read OCI configuration %s: %s.' %
                     (configdata.ociconfigfile, str(e)))
        raise OciMigrateException('Failed to read OCI configuration %s: %s.' %
                                  (configdata.ociconfigfile, str(e)))


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
    logger.debug('Test bucket %s.' % bucketname)
    thispath = os.getenv('PATH')
    logger.debug('PATH is %s' % thispath)
    cmd = ['which', 'oci']
    try:
        ocipath = gen_tools.run_popen_cmd(cmd)
        logger.debug('oci path is %s' % ocipath)
    except Exception as e:
        logger.error('Cannot find oci anymore: %s' % str(e))

    cmd = ['oci', 'os', 'object', 'list', '--bucket-name', bucketname]
    try:
        bucketresult = gen_tools.run_popen_cmd(cmd)
        logger.debug('Result: \n%s' % bucketresult)
        return bucketresult
    except Exception as e:
        logger.critical('Bucket %s does not exists or the authorisation is '
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
    logger.debug('Testing if %s already exists.' % object_name)
    testresult_json = json.loads(bucket)
    logger.debug('Result: \n%s', testresult_json)
    for res in testresult_json['data']:
        if str(res['name']) == object_name:
            return True
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
    logger.debug('Uploading %s to %s as %s.' % (imgname, bucketname, ociname))
    cmd = ['oci', 'os', 'object', 'put', '--bucket-name',
           bucketname, '--file', imgname, '--name', ociname, '--no-multipart']
    gen_tools.pause_msg(cmd)
    try:
        uploadresult = gen_tools.run_popen_cmd(cmd)
        logger.debug('Successfully uploaded %s to %s as %s: %s.'
                     % (imgname, bucketname, ociname, uploadresult))
    except Exception as e:
        logger.critical('Failed to upload %s to object storage %s as %s: %s.'
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
        for vg_name in vg.keys():
            vgchangeres = exec_vgchange(['--activate', 'n', vg_name])
            logger.debug('vgchange: %s' % vgchangeres)
        #
        # remove physical volume: clear cache, if necessary
        if exec_pvscan():
            logger.debug('pvscan clear succeeded')
        else:
            logger.error('pvscan failed')
    except Exception as e:
        logger.error('Failed to release lvms %s: %s' % vg, str(e))
        gen_tools.error_msg('Failed to release lvms %s: %s' % vg, str(e))
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
    gen_tools.pause_msg(cmd)
    try:
        logger.debug('command: %s' % cmd)
        if gen_tools.run_call_cmd(cmd) == 0:
            logger.debug('%s unmounted from %s' % (devname, mntpoint))
            #
            # remove mountpoint
            if exec_rmdir(mntpoint):
                logger.debug('%s removed' % mntpoint)
                return True
            else:
                logger.critical('Failed to remove mountpoint %s' % mntpoint)
                raise OciMigrateException('Failed to remove mountpoint %s'
                                          % mntpoint)
        else:
            logger.critical('Failed to unmount %s' % devname)
    except Exception as e:
        logger.critical('Failed to unmount %s: %s' % (devname, str(e)))
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
    gen_tools.result_msg(msg='\n  %30s\n  %30s' % (head, '-'*30), result=True)


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
    for k, v in sorted(six.iteritems(imgobj.img_info)):
        gen_tools.result_msg(msg='  %30s' % k, result=True)

    logger.debug('show data')
    print('\n  %25s\n  %s' % ('Image data:', '-'*60))
    #
    # name
    fnname = '  missing'
    print_header('Image file path.')
    if 'img_name' in imgobj.img_info:
        fnname = imgobj.img_info['img_name']
    gen_tools.result_msg(msg='  %30s' % fnname, result=True)
    #
    # type
    imgtype = '  missing'
    print_header('Image type.')
    if 'img_type' in imgobj.img_info:
        imgtype = imgobj.img_info['img_type']
    gen_tools.result_msg(msg='  %30s' % imgtype, result=True)
    #
    # size
    imgsizes = '    physical: missing data\n    logical:  missing data'
    print_header('Image size:')
    if 'img_size' in imgobj.img_info:
        imgsizes = '    physical: %8.2f GB\n      logical:  %8.2f GB' \
                   % (imgobj.img_info['img_size']['physical'],
                      imgobj.img_info['img_size']['logical'])
    gen_tools.result_msg(msg='%s' % imgsizes, result=True)
    #
    # header
    if 'img_header' in imgobj.img_info:
        try:
            imgobj.show_header()
        except Exception as e:
            gen_tools.result_msg(msg='Failed to show the image hadear: %s'
                                     % str(e), result=True)
    else:
        gen_tools.result_msg(msg='\n  Image header data missing.', result=True)
    #
    # mbr
    mbr = '  missing'
    print_header('Master Boot Record.')
    if 'mbr' in imgobj.img_info:
        if 'hex' in imgobj.img_info['mbr']:
            mbr = imgobj.img_info['mbr']['hex']
        gen_tools.result_msg(msg='%s' % mbr, result=True)
    #
    # partition table
        print_header('Partiton Table.')
        parttabmissing = '  Partition table data is missing.'
        if 'partition_table' in imgobj.img_info['mbr']:
            show_partition_table(imgobj.img_info['mbr']['partition_table'])
        else:
            gen_tools.result_msg(msg=parttabmissing, result=True)
    #
    # parted data
    print_header('Parted data.')
    parteddata = '  Parted data is missing.'
    if 'parted' in imgobj.img_info:
        show_parted_data(imgobj.img_info['parted'])
    else:
        gen_tools.result_msg(msg='%s' % parteddata, result=True)
    #
    # partition data
    print_header('Partition Data.')
    partdata = '  Partition data is missing.'
    if 'partitions' in imgobj.img_info:
        show_partition_data(imgobj.img_info['partitions'])
    else:
        gen_tools.result_msg(msg='%s' % partdata, result=True)
    #
    # grub config data
    print_header('Grub configuration data.')
    grubdat = '  Grub configuration data is missing.'
    if 'grubdata' in imgobj.img_info:
        show_grub_data(imgobj.img_info['grubdata'])
    else:
        gen_tools.result_msg(msg='%s' % grubdat, result=True)
    #
    # logical volume data
    print_header('Logical Volume data.')
    lvmdata = '  Logical Volume data is missing.'
    if 'volume_groups' in imgobj.img_info:
        if imgobj.img_info['volume_groups']:
            show_lvm2_data(imgobj.img_info['volume_groups'])
    else:
        gen_tools.result_msg(msg=lvmdata, result=True)
    #
    # various data:
    print_header('Various data.')
    if 'bootmnt' in imgobj.img_info:
        gen_tools.result_msg(msg='  %30s: %s mounted on %s'
                                 % ('boot', imgobj.img_info['bootmnt'][0],
                                    imgobj.img_info['bootmnt'][1]),
                             result=True)
    if 'rootmnt' in imgobj.img_info:
        gen_tools.result_msg(msg='  %30s: %s mounted on %s'
                                 % ('root', imgobj.img_info['rootmnt'][0],
                                    imgobj.img_info['rootmnt'][1]),
                             result=True)
    if 'boot_type' in imgobj.img_info:
        gen_tools.result_msg(msg='  %30s: %-30s'
                                 % ('boot type:', imgobj.img_info['boot_type']),
                             result=True)
    #
    # fstab
    print_header('fstab data.')
    fstabmiss = '  fstab data is missing.'
    if 'fstab' in imgobj.img_info:
        show_fstab(imgobj.img_info['fstab'])
    else:
        gen_tools.result_msg(msg=fstabmiss, result=True)
    #
    # network
    # print_header('Network configuration data.')
    # networkmissing = '  Network configuration data is missing.'
    # if 'network' in imgobj.img_info:
    #     show_network_data(imgobj.img_info['network'])
    # else:
    #     gen_tools.result_msg(msg=networkmissing, result=True)
    #
    # os release data
    print_header('Operating System information.')
    osinfomissing = '  Operation System information is missing.'
    if 'osinformation' in imgobj.img_info:
        for k in sorted(imgobj.img_info['osinformation']):
            gen_tools.result_msg(msg='  %30s : %-30s'
                                     % (k, imgobj.img_info['osinformation'][k]),
                                 result=True)
    else:
        gen_tools.result_msg(msg=osinfomissing, result=True)
    #
    # oci configuration
    print_header('OCI client configuration.')
    ociconfmissing = '  OCI client configuration not found.'
    if 'oci_config' in imgobj.img_info:
        for k in sorted(imgobj.img_info['oci_config']):
            gen_tools.result_msg(msg='  %30s : %-30s'
                                     % (k, imgobj.img_info['oci_config'][k]),
                                 result=True)
    else:
        gen_tools.result_msg(msg=ociconfmissing, result=True)


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
    gen_tools.result_msg(msg='  %2s %5s %16s %32s'
                             % ('nb', 'boot', 'type', 'data'), result=True)
    gen_tools.result_msg(msg='  %2s %5s %16s %32s'
                             % ('-'*2, '-'*5, '-'*16, '-'*32), result=True)
    for i in range(0, 4):
        if table[i]['boot']:
            bootflag = 'YES'
        else:
            bootflag = ' NO'
        gen_tools.result_msg(msg='  %02d %5s %16s %32s'
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
    gen_tools.result_msg(msg='\n  %30s\n  %30s'
                             % ('Image header:', '-'*30), result=True)
    for k, v in sorted(headerdata):
        gen_tools.result_msg(msg='  %30s : %s' % (k, v), result=True)


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
        gen_tools.result_msg(
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
        logger.debug('%s' % entry)
        for grubkey in entry:
            # print entry[grubkey]
            for l in entry[grubkey]:
                gen_tools.result_msg(msg=l, result=True)
            gen_tools.result_msg(msg='\n', result=True)


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
    for k, v in sorted(six.iteritems(parted_dict)):
        gen_tools.result_msg(msg='%30s : %s' % (k, v), result=True)
    gen_tools.result_msg(msg='\n', result=True)


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
    for k, v in sorted(six.iteritems(lvm2_data)):
        gen_tools.result_msg(msg='\n  Volume Group: %s:' % k, result=True)
        for t in v:
            gen_tools.result_msg(msg='%40s : %-30s' % (t[0], t[1]), result=True)
    gen_tools.result_msg(msg='\n', result=True)


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
    for k, v in sorted(six.iteritems(partition_dict)):
        gen_tools.result_msg(msg='%30s :\n%s'
                                 % ('partition %s' % k, '-'*60), result=True)
        for x, y in sorted(six.iteritems(v)):
            gen_tools.result_msg(msg='%30s : %s' % (x, y), result=True)
        gen_tools.result_msg(msg='\n', result=True)
    gen_tools.result_msg(msg='\n', result=True)


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
    for nic, nicdata in sorted(six.iteritems(networkdata)):
        gen_tools.result_msg(msg='  %20s:' % nic, result=True)
        for k, v in sorted(six.iteritems(nicdata)):
            gen_tools.result_msg(msg='  %30s = %s' % (k, v), result=True)


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
        logger.error('exception: %s' % str(e))
    return hexdata
