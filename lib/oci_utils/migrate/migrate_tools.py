# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing generic operation methods.
"""
import logging
import os
import six
import stat
import subprocess
import sys
import threading
import time

from datetime import datetime
from oci_utils.migrate.exception import NoSuchCommand
from oci_utils.migrate.exception import OciMigrateException

_logger = logging.getLogger('oci-utils.migrate-tools')
debugflag = False
verboseflag = False
thistime = datetime.now().strftime('%Y%m%d%H%M')
resultfilename = '/tmp/oci_image_migrate_result.dat'
nameserver = '8.8.8.8'
migrate_preparation = True
migrate_non_upload_reason = ''


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
    _logger.error('%s' % msg)
    if msg is not None:
        msg = '  *** ERROR *** %s' % msg
    else:
        msg = '  *** ERROR *** Unidentified error.'
    sys.stderr.write('%s' % msg)
    sys.stderr.flush()
    result_msg(msg=msg)
    time.sleep(1)


def result_msg(msg, flags='a', result=False):
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
    _logger.debug('%s' % msg)
    try:
        with open(resultfilename, flags) as f:
            f.write('  %s\n' % msg)
    except Exception as e:
        _logger.error('Failed to write to %s: %s' % (resultfilename, str(e)))
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
    _logger.debug('Directory full path name: %s' % dirpath)
    #
    try:
        return stat.S_ISDIR(os.stat(dirpath).st_mode)
    except Exception as e:
        _logger.debug('Path %s does not exist or is not a valid directory: %s' %
                     (dirpath, str(e)))
        return False


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
    _logger.debug('File full path name: %s' % filepath)
    #
    try:
        return stat.S_ISREG(os.stat(filepath).st_mode)
    except Exception as e:
        _logger.debug('Path %s does not exist or is not a valid regular file: '
                     '%s' % (filepath, str(e)))
        return False


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
    _logger.debug('Link full path name: %s' % linkpath)
    try:
        return os.path.islink(linkpath)
    except Exception as e:
        _logger.debug('%s is not a symbolic link or does not exist: %s' %
                     (linkpath, str(e)))
        return False


def get_magic_data(image):
    """
    Collect the magic number of the image file.

    Parameters
    ----------
    image: str
        Full path of the image file.

    Returns
    -------
        str: Magic string on success, None otherwise.
    """
    magic_hex = None
    bytes_to_hex_str = lambda b: ''.join('%02x' % i for i in six.iterbytes(b))
    try:
        with open(image, 'rb') as f:
            magic = f.read(4)
            magic_hex = bytes_to_hex_str(magic)
            _logger.debug('Image magic number: %8s' % magic_hex)
    except Exception as e:
        _logger.critical('Image %s is not accessible: 0X%s' % (image, str(e)))
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
            _logger.debug('%s already exists' % toname)
            if os.path.isfile(toname):
                os.remove(toname)
            elif os.path.isdir(toname):
                os.rmdir(toname)
            else:
                _logger.error('Failed to remove %s.' % toname)
        if os.path.islink(toname):
            _logger.debug('%s already exists as a symbolic link.' % toname)
            if os.unlink(toname):
                _logger.debug('Removed symbolic link %s' % toname)
            else:
                _logger.error('Failed to remove symbolic link %s' % toname)

        if os.path.exists(fromname) or os.path.islink(fromname):
            _logger.debug('%s exists and is a file.' % fromname)
            os.rename(fromname, toname)
            _logger.debug('Renamed %s to %s.' % (fromname, toname))
            return True
        else:
            _logger.error('%s does not exists' % fromname)

    except Exception as e:
        _logger.error('Failed to rename %s to %s: %s' % (fromname, toname, str(e)))
        raise OciMigrateException('Failed to rename %s to %s: %s'
                                  % (fromname, toname, str(e)))
    return False


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
    _logger.debug('%s command' % command)
    if exec_exists(command[0]):
        _logger.debug('running %s' % command)
        try:
            thisproc = subprocess.Popen(command,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
            output, error = thisproc.communicate()
            retcode = thisproc.returncode
            _logger.debug('return code for %s: %s' % (command, retcode))
            if retcode != 0:
                if error:
                    _logger.debug('Error occured while '
                                 'running %s: %s - %s'
                                 % (command, retcode, error), exc_info=True)
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
        _logger.critical('%s not found.' % command[0])
        raise NoSuchCommand(command[0])


def get_nameserver():
    """
    Get the nameserver definitions.

    Returns
    -------
    bool: True on success, False otherwise.
    """
    global nameserver
    _logger.debug("Getting nameservers.")
    dnslist = []
    cmd = ['nmcli', 'dev', 'show']
    try:
        nmlist = run_popen_cmd(cmd).decode().split('\n')
        for nmitem in nmlist:
            if 'DNS' in nmitem.split(':')[0]:
                dnslist.append(nmitem.split(':')[1].lstrip().rstrip())
        nameserver = dnslist[0]
        _logger.debug('Nameserver set to %s' % nameserver)
        return True
    except Exception as e:
        _logger.error('Failed to identify nameserver: %s.' % str(e))
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
            _logger.debug('No %s found' % resolvpath)
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
            _logger.debug('No %s found.' % resolvpath)
        #
        # restore original one
        if file_exists(resolvpath + '_' + thistime):
            exec_rename(resolvpath + '_' + thistime, resolvpath)
        else:
            _logger.debug('No %s found.' % resolvpath + '_' + thistime)
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
    _logger.debug('Testing thread.')
    if threadid in threading.enumerate():
        return True
    else:
        return False


class ProgressBar(threading.Thread):
    """
    Class to generate an indication of progress, does not actually
    measure real progress, just shows the process is not hanging.
    """
    _default_progress_chars = ['-', '/', '|', '\\']

    def __init__(self, bar_length, progress_interval, progress_chars=None):
        """
        Progressbar initialisation.

        Parameters:
        ----------
        bar_length: int
            Length of the progress bar.
        progress_interval: float
            Interval in sec of change.
        progress_chars: list
            List of char or str to use; the list is mirrored before use.
        """
        self._stopthread = threading.Event()
        threading.Thread.__init__(self)
        self._bar_len = bar_length
        self._prog_int = progress_interval
        if progress_chars is None:
            self.prog_chars = self._default_progress_chars
        else:
            #
            # compose list of characters to use in progress bar.
            self.prog_chars = progress_chars
            prog_char_len = len(self.progress_chars)
            for i in range(1, prog_char_len-1):
                self.prog_chars.append(progress_chars[prog_char_len-i-1])
        self.stopthis = False

    def run(self):
        """
        Execute the progress bar.

        Returns
        -------
            No return value.
        """
        prog_char_len = len(self.prog_chars)
        prog_bar_len = len(self.prog_chars[0]) * self._bar_len
        empty = ' '*prog_bar_len
        sys.stdout.write('  [%s]\r  [' % empty)
        sys.stdout.flush()
        i = 0
        j = i%prog_char_len
        k = 0
        while True:
            sys.stdout.write('%s' % self.prog_chars[j])
            sys.stdout.flush()
            k += 1
            if k == self._bar_len:
                k = 0
                i += 1
                j = i%prog_char_len
                sys.stdout.write(']\r  [')
                sys.stdout.flush()
            time.sleep(self._prog_int)
            if self.stopthis:
                sys.stdout.write('\r  [%s]\r  [' % empty)
                sys.stdout.flush()
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
