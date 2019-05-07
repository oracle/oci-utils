#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module containing generic data and code with respect to the migration to the
Oracle Cloud Infrastructure.
"""
import logging
import os
import subprocess
import sys
import time
import re
from functools import wraps
from glob import glob

logger = logging.getLogger('oci-image-migrate')

gigabyte = 2**30
rmmod_max_count = 4
qemu_max_count = 2
loopback_root = '/ociloop'

loopback_root = '/mnt'
global verboseflag


class OciMigrateException(Exception):
    """ Exceptions for the Image Migrate to OCI context.
    """
    __args = None

    def __init__(self, message=None):
        """
        Initialisation of the Oci Migrate Exception.

        Parameters
        ----------
        message: str
            The exception message.
        """
        if message is None:
            message = 'An exception occured, no further information'
        super(OciMigrateException, self).__init__(message)


class NoSuchCommand(OciMigrateException):
    """ Exception for command not found.
    """
    def __init__(self, command):
        """
        Initialisation of the No Such Command' exception.

        Parameters
        ----------
        command: str
            The missing command, exec or script.
        """
        super(NoSuchCommand, self).__init__('Command %s not found' % command)


def pause_gt(msg=None):
    """
    GT pause function.

    Parameters
    ----------
    msg: str
        Eventual pause message.

    Returns
    -------
        No return value.
    """
    logger.debug('GT %s' % msg)
    ban0 = '\n  Press a key to continue'
    if msg is not None:
        ban0 = '\n  %s' % msg + ban0
    yn = raw_input(ban0)


def progmsg(msg=None):
    """
    GT debug message

    Parameters
    ----------
    msg: str
        Eventual message.

    Returns
    -------
        No return value
    """
    if not verboseflag:
        return
    logger.debug('GT %s' % msg)
    if msg is not None:
        print '  GT  %s' % msg
    else:
        print '  GT  just mentioning I am here.'
    time.sleep(1)


def thissleep(secs, msg=None):
    """
    Sleep for secs seconds.

    Parameters
    ----------
    secs: float
        Time to sleep.
    msg: str
        Eventual message to comment on sleep.

    Returns
    -------
        No return value.
    """
    secint = 0.3
    sectot = 0.0
    if msg is not None:
        sys.stdout.write('\n  %s' % msg)
    while True:
        sys.stdout.write('.')
        sys.stdout.flush()
        time.sleep(secint)
        sectot += secint
        if sectot > secs:
            break
    print '\n'


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
                    print 'counter %d' % i
                    logger.debug('Failed, sleeping for %d sec: %s' % (intsec, str(e)))
                    if i == maxloop - 1:
                        #print 'State Loop exhausted: %s' % str(e)
                        raise OciMigrateException('State Loop exhausted: %s' % str(e))
                    time.sleep(intsec)
        return loop_func
    return wrap


def exec_exists(executable):
    """
    Verify if executable exists in path.

    Parameters
    ----------
    executable: str
        The file to be tested.

    Returns
    -------
        bool:
            True on success, False otherwise.

    """
    return subprocess.call(['which', executable], stdout=open(os.devnull, 'wb'), stderr=open(os.devnull, 'wb'), shell=False) == 0


def exec_find(thisfile, rootdir= '/'):
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
    progmsg('Looking for %s, might take a while.' % thisfile)
    try:
        for thispath, directories, files in os.walk(rootdir):
            if thisfile in files:
                logger.debug('Found %s' % os.path.join(rootdir, thispath, thisfile))
                return os.path.join(rootdir, thispath, thisfile)
    except Exception as e:
        logger.error('Error while looking for %s: %s' % (thisfile, str(e)))
    return None


def run_call_cmd(command):
    """
    Execute an os command with as only return True or False.

    Parameters
    ----------
    command: list
        The os command and its arguments.

    Returns
    -------
        int: The return value from the command.
    """
    logger.debug('%s' % command)
    if exec_exists(command[0]):
        logger.debug('running %s' % command)
        try:
            return subprocess.check_call(command, stdout=open(os.devnull, 'wb'), stderr=open(os.devnull, 'wb'), shell=False)
        except subprocess.CalledProcessError as chkcallerr:
            logger.error('Subprocess error encountered while running %s: %s' % (command, str(chkcallerr)))
            raise OciMigrateException('Subprocess error encountered while running %s: %s' % (command, str(chkcallerr)))
        except OSError as oserr:
            logger.error('OS error encountered while running %s: %s' % (command, str(oserr)))
            raise OciMigrateException('OS error encountered while running %s: %s' % (command, str(oserr)))
        except Exception as e:
            logger.error('Error encountered while running %s: %s' % (command, str(e)))
            raise OciMigrateException('Error encountered while running %s: %s' % (command, str(e)))
    else:
        logger.critical('%s not found.' % command[0])
        raise NoSuchCommand(command[0])


def run_popen_cmd(command):
    """
    Execute an os command and collect stdout and stderr.

    Parameters
    ----------
    command: list
        The os command and its arguments.

    Returns
    -------
        <type>: The output of the command on success, raises an exception on
        failure.
    """
    logger.debug('%s command' % command)
    if exec_exists(command[0]):
        logger.debug('running %s' % command)
        try:
            thisproc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, error = thisproc.communicate()
            retcode = thisproc.returncode
            logger.debug('return code for %s: %s' % (command, retcode))
            if retcode != 0:
                if error:
                    logger.error('Error occured while running %s: %s - %s' % (command, retcode, error))
                raise OciMigrateException('Error encountered while running %s: %s - %s' % (command, retcode, error))
            if output:
                return output
        except OSError as oserr:
            raise OciMigrateException('OS error encountered while running %s: %s' % (command, str(oserr)))
        except Exception as e:
            raise OciMigrateException('Error encountered while running %s: %s' % (command, str(e)))
    else:
        logger.critical('%s not found.' % command[0])
        raise NoSuchCommand(command[0])


def exec_modprobe(modprobe_args):
    """
    Runs a modprobe command.

    Parameters
    ----------
    modprobe_args: list
        The modprobe argument list.

    Returns
    -------
        bool:
            True on success, False on failure.
    """
    cmd = ['modprobe'] + modprobe_args
    try:
        if run_call_cmd(cmd) == 0:
            return True
        else:
            logger.critical('Failed to execute %s' % cmd)
    except Exception as e:
        logger.critical('Failed: %s' % str(e))
    return False


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
        bool:
            True on success, False on failure.
    """
    cmd = ['rmmod']
    cmd.append(module)
    try:
        if run_call_cmd(cmd) == 0:
            return True
        else:
            logger.critical('Failed to execute %s' % cmd)
    except Exception as e:
        logger.error('Failed: %s' % str(e))
    return False


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
        int: 0 on success

    """
    try:
        qemunbd_res = run_popen_cmd(['qemu-nbd'] + qemunbd_args)
        logger.debug('success: %s' %  qemunbd_res)
        return qemunbd_res
    except Exception as e:
        logger.error('qemu-nbd command failed: %s' % str(e))
        raise OciMigrateException(str(e))


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
        if run_call_cmd(cmd) == 0:
            return True
        return False
    except:
        raise


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
        if run_call_cmd(cmd) == 0:
            return True
        return False
    except:
        raise


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
        blkid_res = run_popen_cmd(cmd)
        logger.debug('success\n%s' % blkid_res)
        return blkid_res
    except Exception as e:
        logger.error('%s failed: %s' % (cmd, str(e)))
        raise OciMigrateException('%s failed: %s' % (cmd, str(e)))


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
    try:
        logger.debug('running %s' % cmd)
        lsblk_res = run_popen_cmd(cmd)
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
    cmd = ['nbd', 'max_part=63']
    if exec_modprobe(cmd):
        return True
    else:
        return False

state_loop(3)
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
    return None


def exec_parted(devname):
    """
    Collect data about the device on the image using the parted utility.

    Parameters
    ----------
    devname: str
        The device name.

    Returns
    -------
        dict: the device data from parted utility/
    """
    cmd = ['parted', devname, 'print']
    logger.debug('%s' % cmd)
    try:
        result = run_popen_cmd(cmd)
        devdata = dict()
        #print result.splitlines()
        for devx in result.split('\n'):
            if 'Model' in devx:
                devdata['Model'] = devx.split(':')[1]
            elif 'Disk' in devx:
                devdata['Disk'] = devx.split(':')[1]
            elif 'Partition Table' in devx:
                devdata['Partition Table'] = devx.split(':')[1]
            else:
                logger.debug('Ignoring %s' % devx)
        return devdata
    except Exception as e:
        logger.error('Failed to collect parted %s device data: %s' % (devname, str(e)))
        raise OciMigrateException('Failed to collect parted %s device data: %s' % (devname, str(e)))


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
        dict: The partition data with sfdisk results.
    """
    cmd = ['sfdisk', '-d', devname]
    logger.debug('%s' % cmd)
    try:
        result = run_popen_cmd(cmd)
        partdata = dict()
        for devx in result.split('\n'):
            if devx.startswith(devname):
                key = devx.split(':')[0].strip()
                progmsg('sfdisk partition %s' % key)
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
        logger.error('Failed to collect sfdisk %s partition data: %s' % (devname, str(e)))
        raise OciMigrateException('Failed to collect sfdisk %s partition data: %s' % (devname, str(e)))


state_loop(3)
def mount_imgfn(imgname):
    """
    Link vm image with a device.

    Parameters
    ----------
    imgname: str
        Full path of the image file.

    Returns
    -------
        str: device on success, None otherwise.
    """
    # create nbd devices
    progmsg('load nbd')
    if not create_nbd():
        logger.critical('Failed ot load nbd module')
        raise OciMigrateException('Failed to load nbd module')
    else:
        logger.debug('nbd module loaded')
    #
    # link img with first free nbd device
    # thissleep(5)
    # yn = raw_input('\n D type a key to continue')
    progmsg('find free nbd device')
    devpath = get_free_nbd()
    if devpath is None:
        logger.critical('Failed to find a free nbd device.')
        raise OciMigrateException('Failed to find a free nbd device')
    else:
        logger.debug('Device %s is free.' % devpath)

    progmsg('mount image %s' % imgname)
    try:
        qemucmd = ['-c', devpath, imgname]
        try:
            z = exec_qemunbd(qemucmd)
            thissleep(4, 'Mounting %s ' % imgname)
            logger.debug('qemu-nbd %s succeeded' % qemucmd)
            return devpath
        except Exception as e:
            logger.critical('Failed to create nbd devices %s: %s' % (imgname, str(e)))
            raise OciMigrateException(str(e))
    except NoSuchCommand:
        logger.critical('qemu-nbd does not exist')
        raise NoSuchCommand('qemu-nbd does not exist')
    except Exception as e:
        logger.critical('Something wrong with creating nbd devices: %s' % str(e))
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
        bool: True on succes, False otherwise.
    """
    try:
        #
        # release device
        qemucmd = ['-d', devname]
        z = exec_qemunbd(qemucmd)
        logger.debug('qemu-nbd %s succeeded: %s' % (qemucmd, str(z)))
        #
        # clear lvm cache
        if exec_pvscan():
            logger.debug('lvm cache updated')
        else:
            raise OciMigrateException('Failed to clear LVM cache.')
        if rm_nbd():
            logger.debug('rmmod nbd succeeded')
        else:
            raise OciMigrateException('Failed to remove nbd module.')
        #else:
        #    logger.critical('Failed to run qemu-nbd %s' % (qemucmd))
        #    raise OciMigrateException('Failed to run qemu-nbd %s' % (qemucmd))
    except Exception as e:
        logger.critical('Something wrong with removing nbd devices: %s' % str(e))
        raise OciMigrateException('Something wrong with removing nbd devices: %s' % str(e))
    return True


@state_loop(3)
def mount_part(devname):
    """
    Create the mountpoint /mnt/<last part of device specification> and mount a
    partition on on this mountpoint.

    Parameters
    ----------
    devname: str
        The full path of the device.

    Returns
    -------
        str: The mounted partition on Success, None otherwise.
    """
    #
    # create mountpoint /mnt/<devname>
    mntpoint = loopback_root + '/' + devname.rsplit('/')[-1]
    logger.debug('Loopback mountpoint: %s' % mntpoint)
    if exec_mkdir(mntpoint):
        logger.debug('mountpoint: %s created.' % mntpoint)
        #
        # actual mount
        cmd = ['mount', devname, mntpoint]
        try:
            logger.debug('command: %s' % cmd)
            output = run_popen_cmd(cmd)
            logger.debug('%s mounted on %s: %s' % (devname, mntpoint, str(output)))
            return mntpoint
        except Exception as e:
            #
            # mount failed, need to remove mountpoint.
            logger.critical('failed to mount %s: %s' % (devname, str(e)))
            if exec_rmdir(mntpoint):
                logger.debug('%s removed' % mntpoint)
            else:
                logger.critical('Failed to remove mountpoint %s' % mntpoint)
                raise OciMigrateException('Failed to remove mountpoint %s' % mntpoint)
    else:
        raise OciMigrateException('Failed to create mountpoint %s' % mntpoint)
    return None

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
    try:
        logger.debug('command: %s' % cmd)
        output = run_popen_cmd(cmd)
        logger.debug('Physical volumes scanned on %s: %s'% (devname, str(output)))
        return True
    except Exception as e:
        #
        # pvscan failed
        logger.critical('Failed to scan %s for physical volumes: %s' % (devname, str(e)))
        raise OciMigrateException('Failed to scan %s for physical volumes: %s' % (devname, str(e)))


def exec_vgscan():
    """
    Scan the system for (new) volume groups.

    Returns
    -------
        bool: True on success, raises an exeception on failure.
    """
    cmd =  ['vgscan', '--verbose']
    try:
        logger.debug('command: %s' % cmd)
        output = run_popen_cmd(cmd)
        logger.debug('Volume groups scanned: %s'% str(output))
        return True
    except Exception as e:
        #
        # vgscan failed
        logger.critical('Failed to scan for volume groups: %s' % str(e))
        raise OciMigrateException('Failed to scan for volume groups: %s' % str(e))


def exec_lvscan():
    """
    Scan the system for (new) logical volumes.

    Returns
    -------
        dict:  inactive, supposed new, volume groups with list of logical volumes on success,
        raises an exeception on failure.
    """
    cmd =  ['lvscan', '--verbose']
    try:
        logger.debug('command: %s' % cmd)
        output = run_popen_cmd(cmd)
        logger.debug('Logical volumes scanned: %s'% str(output))
        new_vgs = dict()
        for lvdevdesc in output.splitlines():
            new_lvs = []
            if 'inactive' in lvdevdesc:
                lvarr = re.sub(r"'", "", lvdevdesc).split()
                lvdev = lvarr[1]
                vgarr = re.sub(r"/", " ", lvdev).split()
                vgdev = vgarr[1]
                mapperdev = re.sub(r"-", "--", vgdev) + '-' + vgarr[2];
                logger.debug('vg %s lv %s mapper %s' % (vgdev, lvdev, mapperdev))
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
        raise OciMigrateException('Failed to scan for logical volume: %s' % str(e))


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
    try:
        output = run_popen_cmd(cmd)
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
    logger.debug('device %s contains an lvm2' % devname)
    lvmdata = []

    try:
        #
        # physical volumes
        if exec_pvscan(devname):
            logger.debug('pvscan %s succeeded' % devname)
        else:
            logger.critical('pvscan %s failed' % devname)
        #
        # volume groups
        if exec_vgscan():
            logger.debug('vgscan succeeded')
        else:
            logger.critical('vgscan failed')
        #
        # logical volumes
        vgs = exec_lvscan()
        if vgs is not None:
            logger.debug('lvscan succeeded')
        else:
            logger.critical('lvscan failed')
        #
        # make available
        vgchangeargs = ['--activate', 'y']
        vgchangeres = exec_vgchange(vgchangeargs)
        logger.debug('vgchange: %s' % vgchangeres)
        vgfound = False
        if vgchangeres is not None:
            for l in vgchangeres.splitlines():
                logger.debug('vgchange line: %s' % l)
                for vg in vgs.keys():
                    if vg in l:
                        vgfound = True
            logger.debug('vgchange: %s, %s' % (vgchangeres, vgfound))
        else:
            logger.critical('vgchange failed')
        return vgs
    except Exception as e:
        logger.critical('Mount lvm %s failed: %s' % (devname, str(e)))
        raise OciMigrateException('Mount lvm %s failed: %s' % (devname, str(e)))
    return lvmdata

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
            raise OciMigrateException('Exception raised during release lvms %s: %s' % (vg, str(e)))


@state_loop(5,2)
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
    try:
        logger.debug('command: %s' % cmd)
        if run_call_cmd(cmd) == 0:
            logger.debug('%s unmounted from %s' % (devname, mntpoint))
            #
            # remove mountpoint
            if exec_rmdir(mntpoint):
                logger.debug('%s removed' % mntpoint)
                return True
            else:
                logger.critical('Failed to remove mountpoint %s' % mntpoint)
                raise OciMigrateException('Failed to remove mountpoint %s' % mntpoint)
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
    print '\n  %30s\n  %30s' % (head, '-'*30)


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
    for k,v in sorted(imgobj.img_info.iteritems()):
        print '  %30s' % k

    logger.debug('show data')
    print '\n  %25s\n  %s' % ('Image data:', '-'*60)
    #
    # name
    fnname = 'missing'
    print_header('Image file path.')
    if 'img_name' in imgobj.img_info:
        fnname = imgobj.img_info['img_name']
    print '  %30s' % fnname
    #
    # type
    imgtype = 'missing'
    print_header('Image type.')
    if 'img_type' in imgobj.img_info:
        imgtype = imgobj.img_info['img_type']
    print '  %30s' % imgtype
    #
    # size
    imgsizes = '    physical: missing data\n    logical:  missing data'
    print_header('Image size:')
    if 'img_size' in imgobj.img_info:
        imgsizes = '    physical: %8.2f GB\n    logical:  %8.2f GB' % (imgobj.img_info['img_size']['physical'], imgobj.img_info['img_size']['logical'])
    print '%s' % imgsizes
    #
    # header
    if 'img_header' in imgobj.img_info:
        try:
            imgobj.show_header()
        except Exception as e:
            print 'Failed to show the image hadear: %s' % str(e)
    else:
        print '\n  Image header data missing.'
    #
    # mbr
    mbr = 'missing'
    print_header('Master Boot Record.')
    if 'mbr' in imgobj.img_info:
        mbr = imgobj.img_info['mbr']['hex']
    print '%s' % mbr
    #
    # partition table
    print_header('Partiton Table.')
    parttabmissing = '  Partition table data is missing.'
    if 'partition_table' in imgobj.img_info['mbr']:
        show_partition_table(imgobj.img_info['mbr']['partition_table'])
    else:
        print parttabmissing
    #
    # parted data
    print_header('Parted data.')
    parteddata = '  Parted data is missing.'
    if 'parted' in imgobj.img_info:
        show_parted_data(imgobj.img_info['parted'])
    else:
        print '%s' % parteddata
    #
    # partition data
    print_header('Partition Data.')
    partdata = 'Partition data is missing.'
    if 'partitions' in imgobj.img_info:
        show_partition_data(imgobj.img_info['partitions'])
    else:
        print '%s' % partdata
    #
    # grub config data
    print_header('Grub configuration data.')
    grubdat = '  Grub configuration data is missing.'
    if 'grubdata' in imgobj.img_info:
        show_grub_data(imgobj.img_info['grubdata'])
    else:
        print '%s' % grubdat
    #
    # logical volume data
    print_header('Logical Volume data.')
    lvmdata = ' Logical Volume data is missing.'
    if 'volume_groups' in imgobj.img_info:
        if imgobj.img_info['volume_groups']:
            show_lvm2_data(imgobj.img_info['volume_groups'])
    else:
        print lvmdata
    #
    # various data:
    print_header('Various data.')
    print '  %30s: %s mounted on %s' % ('boot', imgobj.img_info['bootmnt'][0], imgobj.img_info['bootmnt'][1])
    print '  %30s: %s mounted on %s' % ('root', imgobj.img_info['rootmnt'][0], imgobj.img_info['rootmnt'][1])
    print '  %30s: %-30s' % ('boot type:', imgobj.img_info['boot_type'])
    #
    # fstab
    print_header('fstab data.')
    fstabmiss = 'fstab data is missing.'
    if 'fstab' in imgobj.img_info:
        show_fstab(imgobj.img_info['fstab'])
    else:
        print fstabmiss
    #
    # network
    print_header('Network configuration data.')
    networkmissing = 'Network configuration data is missing.'
    if 'network' in imgobj.img_info:
        show_network_data(imgobj.img_info['network'])
    else:
        print networkmissing
    #
    # os release data
    print_header('Operating System information.')
    osinfomissing = 'Operation System information is missing.'
    if 'osinformation' in imgobj.img_info:
        for k in sorted(imgobj.img_info['osinformation']):
            print '  %30s : %-30s' % (k, imgobj.img_info['osinformation'][k])


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
    print '  %2s %5s %16s %32s' % ('nb', 'boot', 'type', 'data')
    print '  %2s %5s %16s %32s' % ('-'*2, '-'*5, '-'*16, '-'*32)
    for i in range(0,4):
        if table[i]['boot']:
            bootflag = 'YES'
        else:
            bootflag = ' NO'
        print '  %02d %5s %16s %32s' % (i, bootflag, table[i]['type'], table[i]['entry'] )


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
    print '\n  %30s\n  %30s' % ('Image header:', '-'*30)
    for k, v in sorted(headerdata):
        print '  %30s : % %s' % k,v


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
        print '%60s %20s %8s %20s %2s %2s' % (line[0], line[1], line[2], line[3], line[4], line[5])


def show_grub_data(grublist):
    """
    Show the relevant data in the grub config file.

    Parameters
    ----------
    grublist: list of dictionaries, 1 per boot section, containing grub lines as list.

    Returns
    -------
        No return value.
    """
    for entry in grublist:
        logger.debug('%s' % entry)
        for grubkey in entry:
            # print entry[grubkey]
            for l in entry[grubkey]:
                print l
            print '\n'
        #        print '  %12s' % k
        #        for i in v:
        #            print ' %s' % i,
        #        print '\n'


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
    for k, v in sorted(parted_dict.iteritems()):
        print '%30s : %s' % (k,v)
    print '\n'


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
    for k, v in sorted(lvm2_data.iteritems()):
        print '\n  Volume Group: %s:' % k
        for t in v:
            print '%40s : %-30s' % (t[0], t[1])
    print '\n'


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
    for k, v in sorted(partition_dict.iteritems()):
        print '%30s :\n%s' % ('partition %s' % k, '-'*60)
        for x, y in sorted(v.iteritems()):
            print '%30s : %s' % (x, y)
        print '\n'
    print '\n'


def show_network_data(networkdata):
    """
    Show the collected data on the network interfaces.

    Parameters
    ----------
    networkdata: list
        List of dictionaries containing the network configuration data.

    Returns
    -------
        No return value.
    """
    for nw in sorted(networkdata):
        #print '  %20s:' % nw
        for k,v in nw.iteritems():
            print '\n  %20s:' % k
            for x, y in sorted(v.iteritems()):
                print '  %30s = %s' % (x, y)
            #print '  %30s = %s' % (k,v)


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
            readable = ''.join([chr(i) if 32 <= i <= 127 else '.' for i in bytearray(x)])
            hexdata += '%08x : %s : %s :\n' % (addr*16, line, readable)
            y = m[blocklen:]
            m = y
            addr += 1
            ll -= blocklen
    except Exception as e:
        print 'exception: %s' % str(e)
    return hexdata
