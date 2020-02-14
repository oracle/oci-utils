# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing generic operation methods.
"""
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

from oci_utils.migrate import bytes_to_hex
from oci_utils.migrate.exception import OciMigrateException

_logger = logging.getLogger('oci-utils.migrate-tools')
debugflag = False
verboseflag = False
current_time = datetime.now().strftime('%Y%m%d%H%M')
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
    _logger.error('   %s' % msg)
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
            f.write('  %s: %s\n' % (datetime.now().strftime('%H:%M:%S'), msg))
    except Exception as e:
        _logger.error('   Failed to write to %s: %s' % (resultfilename, str(e)))
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
    try:
        with open(image, 'rb') as f:
            magic = f.read(4)
            magic_hex = bytes_to_hex(magic)
            _logger.debug('Image magic number: %8s' % magic_hex)
    except Exception as e:
        _logger.critical('  Image %s is not accessible: 0X%s' % (image, str(e)))
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
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
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
        bool: True on success, False if fromname does not exist or failed
              to remove toname, raises an exception on failure.
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
            elif os.path.islink(toname):
                if os.unlink(toname):
                    _logger.debug('Removed symbolic link %s' % toname)
                else:
                    _logger.error('   Failed to remove symbolic link %s' % toname)
            else:
                _logger.error('   Failed to remove %s.' % toname)
        else:
            _logger.debug('%s does exists' % toname)

        if os.path.exists(fromname) or os.path.islink(fromname):
            _logger.debug('%s exists and is a file or symbolic link.' % fromname)
            os.rename(fromname, toname)
            _logger.debug('Renamed %s to %s.' % (fromname, toname))
            return True
        else:
            _logger.error('   %s does not exists' % fromname)

    except Exception as e:
        _logger.error('   Failed to rename %s to %s: %s'
                      % (fromname, toname, str(e)))
        raise OciMigrateException('Failed to rename %s to %s: %s'
                                  % (fromname, toname, str(e)))
    return False


def run_call_cmd(command):
    """
    Execute an os command which does not return data.

    Parameters
    ----------
        command: list
            The os command and its arguments.

    Returns:
    -------
        int: The return value.
    """
    _logger.debug('Executing %s' % command)
    assert (len(command) > 0), 'empty command list'
    try:
        return(subprocess.call(command, stderr=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL))
    except OSError as oserr:
        raise OciMigrateException('OS error encountered while running %s: %s'
                                  % (command, str(oserr)))
    except subprocess.CalledProcessError as e:
        raise OciMigrateException('Error encountered while running %s: %s'
                                  % (command, str(e)))


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
            ext_process = subprocess.Popen(command,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
            output, error = ext_process.communicate()
            retcode = ext_process.returncode
            _logger.debug('return code for %s: %s' % (command, retcode))
            if retcode != 0:
                if error:
                    _logger.debug('Error occured while running %s: %s - %s'
                                  % (command, retcode, error.decode('utf-8')),
                                  exc_info=True)
                raise OciMigrateException('Error encountered while running %s: '
                                          '%s - %s' % (command, retcode,
                                                       error.decode('utf-8')))
            if output:
                return output
        except OSError as oserr:
            raise OciMigrateException('OS error encountered while '
                                      'running %s: %s' % (command, str(oserr)))
        except Exception as e:
            raise OciMigrateException('Error encountered while running %s: %s'
                                      % (command, str(e)))
    else:
        _logger.critical('  %s not found.' % command[0])
        raise OciMigrateException('%s does not exist' % command[0])


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
        nmlist = run_popen_cmd(cmd).decode('utf-8').split('\n')
        for nmitem in nmlist:
            if 'DNS' in nmitem.split(':')[0]:
                dnslist.append(nmitem.split(':')[1].lstrip().rstrip())
        nameserver = dnslist[0]
        _logger.debug('Nameserver set to %s' % nameserver)
        return True
    except Exception as e:
        _logger.error('   Failed to identify nameserver: %s.' % str(e))
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
            _ = exec_rename(resolvpath, resolvpath + '_' + current_time)
        else:
            _logger.error('   No %s found' % resolvpath)
        #
        # write new
        with open(resolvpath, 'w') as f:
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
        if os.path.isfile(resolvpath):
            exec_rename(resolvpath, resolvpath + '_temp_' + current_time)
        else:
            _logger.debug('No %s found.' % resolvpath)
        #
        # restore original one
        if os.path.isfile(resolvpath + '_' + current_time):
            exec_rename(resolvpath + '_' + current_time, resolvpath)
        else:
            _logger.debug('No %s found.' % resolvpath + '_' + current_time)
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
    _default_progress_chars = ['#']

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
        #
        # length of varible progress bar
        self._bar_len = bar_length - 14
        #
        # progress interval in sec
        self._prog_int = progress_interval
        if progress_chars is None:
            self._prog_chars = self._default_progress_chars
        else:
            self._prog_chars = progress_chars
        #
        # nb progress symbols
        self._nb_prog_chars = len(self._prog_chars)
        #
        # the max len of the progress symbols, should be all equal
        self._prog_len = 0
        for s in self._prog_chars:
            ls = len(s)
            if ls > self._prog_len:
                self._prog_len = ls
        #
        # nb iterations per bar
        self._cntr = self._bar_len - self._prog_len + 1
        self.stop_the_progress_bar = False

    def run(self):
        """
        Execute the progress bar.

        Returns
        -------
            No return value.
        """
        #
        # counter in progress bar symbols
        i = 0
        j = i%self._nb_prog_chars
        #
        # counter in bar
        k = 0
        sys.stdout.write('\n')
        sys.stdout.flush()
        while True:
            pbar = '  ' \
                   + datetime.now().strftime('%H:%M:%S') \
                   + ' [' \
                   + ' '*k \
                   + self._prog_chars[j] \
                   + ' ' * (self._bar_len - k - self._prog_len) \
                   + ']'
            sys.stdout.write('\r%s' % pbar)
            sys.stdout.flush()
            k += 1
            if k == self._cntr:
                k = 0
                i += 1
                j = i%self._nb_prog_chars
            time.sleep(self._prog_int)
            if self.stop_the_progress_bar:
                pbar = '  ' \
                   + datetime.now().strftime('%H:%M:%S') \
                   + ' [ ' \
                   + ' %s' % self._prog_chars[j] \
                   + ' done ]' \
                   + (self._bar_len - self._prog_len - 5)*' '
                sys.stdout.write('\r%s\n' % pbar)
                sys.stdout.flush()
                break

    def stop(self):
        """
        Notify thread to stop the progress bar.

        Returns
        -------
            No return value.
        """
        self.stop_the_progress_bar = True
        self.join()
        sys.stdout.write('\n')
        sys.stdout.flush()

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
