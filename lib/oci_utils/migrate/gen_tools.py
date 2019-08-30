#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing generic operation methods.
"""
import logging
import os
import stat
import subprocess
import sys
import termios
import time
import tty
import threading
from datetime import datetime
from oci_utils.migrate.exception import NoSuchCommand
from oci_utils.migrate.exception import OciMigrateException

logger = logging.getLogger('oci-image-migrate')
debugflag = False
verboseflag = False
thistime = datetime.now().strftime('%Y%m%d%H%M')
resultfilename = '/tmp/oci_image_migrate_' + thistime
nameserver = '8.8.8.8'


def getch():
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


def read_yn(prompt, yn=True):
    """
    Read yes or no form stdin, No being the default.

    Parameters
    ----------
        prompt: str
            The message.
        yn: bool
            Add (y/N) to the prompt if True.
    Returns
    -------
        bool: True on yes, False otherwise.
    """
    thisprmpt = prompt + ' '
    if yn:
        thisprmpt += ' (y/N) '
    sys.stdout.write(thisprmpt)
    yn = getch()
    sys.stdout.write('\n')
    if yn.upper() == 'Y':
        return True
    else:
        return False


def pause_msg(msg=None):
    """
    pause function.

    Parameters
    ----------
    msg: str
        Eventual pause message.

    Returns
    -------
        No return value.
    """
    logger.debug('%s' % msg)
    ban0 = '\n  Press a key to continue'
    if msg is not None:
        ban0 = '\n  %s' % msg + ban0
    _ = read_yn(ban0, False)


def error_msg(msg=None):
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
    logger.error('%s' % msg)
    if msg is not None:
        msg = '  *** ERROR *** %s' % msg
    else:
        msg = '  *** ERROR *** Unidentified error.'
    sys.stderr.write('%s' % msg)
    sys.stderr.flush()
    result_msg(msg=msg)
    time.sleep(1)


def exit_msg(msg, exitcode=1):
    """
    Post a message on stdout and exit.

    Parameters
    ----------
    msg: str
        The exit message.
    exitcode: int
        The exit code, default is 1.

    Returns
    -------
        No return value.
    """
    logger.critical('%s' % msg)
    sys.stderr.write('\n  %s\n' % msg)
    exit(exitcode)


def result_msg(msg, flags='ab', result=False):
    """
    Write information to the log file, the result file and the console if the
    result flag is set.

    Parameters
    ----------
    msg: str
        The message.
    flags: str
        The flags for the open file command.
    result: bool
        Flag, write to console if True.

    Returns
    -------
        No return value.
    """
    logger.debug('%s' % msg)
    try:
        with open(resultfilename, flags) as f:
            f.write('%s\n' % msg)
    except Exception as e:
        logger.error('Failed to write to %s: %s' % (resultfilename, str(e)))
    if result:
        if msg is not None:
            print('  %s' % msg)
        else:
            print('  Just mentioning I am here.')


def is_root():
    """
    Verify is operator is the root user.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    if os.getuid() == 0:
        return True
    else:
        return False


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
    print('\n')


def dir_exists(dirpath):
    """
    Verify if the path exists and is a directory.

    Parameters
    ----------
    dirpath: str
        The full path of the directory.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    logger.info('Directory full path name: %s' % dirpath)
    #
    # path exists
    if os.path.exists(dirpath):
        logger.debug('Path %s exists' % dirpath)
    else:
        logger.debug('Path %s does not exist.' % dirpath)
        return False
    #
    # is a directory
    image_st = os.stat(dirpath)[stat.ST_MODE]
    if stat.S_ISDIR(image_st):
        logger.debug('Path %s is directory.' % dirpath)
    else:
        logger.debug('Path %s is not a directory.' % dirpath)
        return False
    return True


def file_exists(filepath):
    """
    Verify if the file exists and is a regular file.

    Parameters
    ----------
    filepath: str
        The full path of the file.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    logger.info('File full path name: %s' % filepath)
    #
    # file exists
    if os.path.exists(filepath):
        logger.debug('File %s exists' % filepath)
    else:
        logger.debug('File %s does not exist.' % filepath)
        return False
    #
    # is a regular file
    image_st = os.stat(filepath)[stat.ST_MODE]
    if stat.S_ISREG(image_st):
        logger.debug('File %s is regular file' % filepath)
    else:
        logger.debug('File %s is not a regular file.' % filepath)
        return False
    return True


def link_exists(linkpath):
    """
    Verify if the linkpath exists and is a symbolic link.

    Parameters
    ----------
    linkpath: str
        The full path of the link.

    Returns
    -------
        bool: True on success, false otherwise.
    """
    logger.info('Link full path name: %s' % linkpath)
    if os.path.islink(linkpath):
        logger.debug('%s is a symbolic link' % linkpath)
        return True
    else:
        logger.debug('%s does not exist or is not a symbolic link.' % linkpath)
        return False


def get_magic_data(image):
    """
    Perform elementary on the file.

    Parameters
    ----------
    image: str
        Full path of the image file.

    Returns
    -------
        str: Magic string on success, None otherwise.
    """
    magic_hex = None
    #
    # is readable
    try:
        with open(image, 'rb') as f:
            magic = f.read(4)
            magic_hex = magic.encode("hex")
            logger.debug('Image magic number: %8s' % magic_hex)
    except Exception as e:
        logger.critical('Image %s is not accessible: 0X%s' % (image, str(e)))
    return magic_hex


def exec_exists(executable):
    """
    Verify if executable exists in path.

    Parameters
    ----------
    executable: str
        The file to be tested.

    Returns
    -------
        bool: True on success, False otherwise.

    """
    return subprocess.call(['which', executable],
                           stdout=open(os.devnull, 'wb'),
                           stderr=open(os.devnull, 'wb'),
                           shell=False) == 0


def exec_rename(fromname, toname):
    """
    Renames a file, symbolic link or directory.

    Parameters
    ----------
    fromname: str
        Full path of the original file.
    toname: str
        The new name as full path.

    Returns
    -------
        bool: True on success, raises an exception on failure.
    """
    try:
        #
        # delete to_ if already exists
        #
        # if file or directory
        if os.path.exists(toname):
            logger.debug('%s already exists' % toname)
            if os.path.isfile(toname):
                os.remove(toname)
            elif os.path.isdir(toname):
                os.rmdir(toname)
            else:
                logger.error('Failed to remove %s.' % toname)
        if os.path.islink(toname):
            logger.debug('%s already exists as a symbolic link.' % toname)
            if os.unlink(toname):
                logger.debug('Removed symbolic link %s' % toname)
            else:
                logger.error('Failed to remove symbolic link %s' % toname)

        if os.path.exists(fromname) or os.path.islink(fromname):
            logger.debug('%s exists and is a file.' % fromname)
            os.rename(fromname, toname)
            logger.debug('Renamed %s to %s.' % (fromname, toname))
            return True
        else:
            logger.error('%s does not exists' % fromname)

    except Exception as e:
        logger.error('Failed to rename %s to %s: %s' % (fromname, toname, str(e)))
        raise OciMigrateException('Failed to rename %s to %s: %s'
                                  % (fromname, toname, str(e)))
    return False


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
            return subprocess.check_call(command,
                                         stdout=open(os.devnull, 'wb'),
                                         stderr=open(os.devnull, 'wb'),
                                         shell=False)
        except subprocess.CalledProcessError as chkcallerr:
            logger.error('Subprocess error encountered while running '
                         '%s: %s' % (command, str(chkcallerr)))
            raise OciMigrateException('Subprocess error encountered while '
                                      'running %s: %s' % (command, str(chkcallerr)))
        except OSError as oserr:
            logger.error('OS error encountered while running '
                         '%s: %s' % (command, str(oserr)))
            raise OciMigrateException('OS error encountered while running '
                                      '%s: %s' % (command, str(oserr)))
        except Exception as e:
            logger.error('Error encountered while running '
                         '%s: %s' % (command, str(e)))
            raise OciMigrateException('Error encountered while running '
                                      '%s: %s' % (command, str(e)))
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
            thisproc = subprocess.Popen(command,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
            output, error = thisproc.communicate()
            retcode = thisproc.returncode
            logger.debug('return code for %s: %s' % (command, retcode))
            if retcode != 0:
                if error:
                    logger.error('Error occured while '
                                 'running %s: %s - %s'
                                 % (command, retcode, error))
                raise OciMigrateException('Error encountered while '
                                          'running %s: %s - %s'
                                          % (command, retcode, error))
            if output:
                return output
        except OSError as oserr:
            raise OciMigrateException('OS error encountered while '
                                      'running %s: %s' % (command, str(oserr)))
        except Exception as e:
            raise OciMigrateException('Error encountered while running %s: %s'
                                      % (command, str(e)))
    else:
        logger.critical('%s not found.' % command[0])
        raise NoSuchCommand(command[0])


def get_nameserver():
    """
    Get the nameserver definitions.

    Returns
    -------
    bool: True on success, False otherwise.
    """
    global nameserver
    logger.debug("Getting nameservers.")
    dnslist = []
    cmd = ['nmcli', 'dev', 'show']
    try:
        nmlist = run_popen_cmd(cmd).split('\n')
        for nmitem in nmlist:
            if 'DNS' in nmitem.split(':')[0]:
                dnslist.append(nmitem.split(':')[1].lstrip().rstrip())
        nameserver = dnslist[0]
        logger.debug('Nameserver set to %s' % nameserver)
        return True
    except Exception as e:
        logger.error('Failed to identify nameserver: %s.' % str(e))
        return False


def set_nameserver():
    """
    Setting temporary nameserver.

    Returns
    -------
    bool: True on success, False otherwise.
    """
    # rename eventual existing resolv.conf
    resolvpath = '/etc/resolv.conf'
    try:
        #
        # save current
        if os.path.isfile(resolvpath) \
                or os.path.islink(resolvpath) \
                or os.path.isdir(resolvpath):
            exec_rename(resolvpath, resolvpath + '_' + thistime)
        else:
            logger.debug('No %s found' % resolvpath)
        #
        # write new
        with open(resolvpath, 'wb') as f:
            f.writelines('nameserver %s\n' % nameserver)
        return True
    except Exception as e:
        error_msg('Failed to set nameserver: %s'
                  '\n  continuing but might cause issues installing cloud-init.'
                  % str(e))
        return False


def restore_nameserver():
    """
    Restore nameserver configuration.

    Returns
    -------
    bool: True on success, False otherwise.
    """
    resolvpath = '/etc/resolv.conf'
    try:
        #
        # save used one
        if file_exists(resolvpath):
            exec_rename(resolvpath, resolvpath + '_temp_' + thistime)
        else:
            logger.debug('No %s found.' % resolvpath)
        #
        # restore original one
        if file_exists(resolvpath + '_' + thistime):
            exec_rename(resolvpath + '_' + thistime, resolvpath)
        else:
            logger.debug('No %s found.' % resolvpath + '_' + thistime)
        return True
    except Exception as e:
        error_msg('Failed to restore nameserver: %s'
                  '\n  continuing but might cause issues installing cloud-init.'
                  % str(e))
        return False


def isthreadrunning(threadid):
    """
    Verify if thread is active.

    Parameters
    ----------
    threadid: thread
        The thread to test.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    logger.debug('Testing thread.')
    if threadid in threading.enumerate():
        return True
    else:
        return False


class ProGressBar(threading.Thread):
    """
    Class to generate an indication of progress, does not actually
    measure real progress, just shows the process is not hanging.

    Attributes
    ----------
    llength: int
        Length of the progress bar.
    iinterval: float
        Interval in sec of change.
    progarr: list
        List of char or str to use; the list is mirrored before use.
    """
    def __init__(self, llength, iinterval, progarr=None):
        self._stopthread = threading.Event()
        threading.Thread.__init__(self)
        self.llen = llength
        self.iint = iinterval
        if progarr is None:
            self.prog2 = ['-', '/', '|', '\\']
        else:
            self.prog2 = progarr
            lll = len(progarr)
            for i in range(1, lll-1):
                self.prog2.append(progarr[lll-i-1])
        self.stopthis = False

    def run(self):
        """
        Execute the progress bar.

        Returns
        -------
            No return value.
        """
        ll = len(self.prog2)
        lt = len(self.prog2[0]) * self.llen
        empty = ' '*lt
        sys.stdout.write('  [%s]\r  [' % empty)
        sys.stdout.flush()
        i = 0
        j = i%ll
        k = 0
        while True:
            sys.stdout.write('%s' % self.prog2[j])
            sys.stdout.flush()
            k += 1
            if k == self.llen:
                k = 0
                i += 1
                j = i%ll
                sys.stdout.write(']\r  [')
                sys.stdout.flush()
            time.sleep(self.iint)
            if self.stopthis:
                break

    def stop(self):
        """
        Notify thread to stop the progress bar.

        Returns
        -------
            No return value.
        """
        self.stopthis = True
        self.join()

    def join(self, timeout=None):
        """
        Terminate the thread.

        Parameters
        ----------
        timeout: float
            Time to wait if set.

        Returns
        -------
            No return value.
        """
        self._stopthread.set()
        threading.Thread.join(self, timeout)
