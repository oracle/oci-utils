# oci-utils
#
# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" OS command line utils.
"""

import logging
import subprocess

from . import (SUDO_CMD, CAT_CMD, RM_CMD, SH_CMD, CP_CMD, TOUCH_CMD, CHMOD_CMD, MKDIR_CMD)

__all__ = ['call', 'call_output', 'execute', 'call_popen_output', 'delete_file', 'copy_file', 'write_to_file']

_logger = logging.getLogger('oci-utils.sudo')


def _prepare_command(cmd):
    """
    Prepare the command line to be executed prepend sudo if not already present.

    Parameters
    ----------
    cmd : list
        Command line as list of strings.

    Returns
    -------
        list
            The prepared command.
    """
    assert (len(cmd) > 0), 'Empty command list'
    _cmd = []
    if cmd[0] != SUDO_CMD:
        _cmd.insert(0, SUDO_CMD)
    _cmd.extend(cmd)

    return _cmd


def execute(cmd):
    """
    Execute a command return.

    Parameters
    ----------
    cmd: list
        Command line as list of strings.

    Returns
    -------
    (exit code, stdout, stderr)
    """
    _c = _prepare_command(cmd)
    if _logger.isEnabledFor(logging.DEBUG):
        _logger.debug('Executing [%s]', ' '.join(_c))
    cp = subprocess.run(_c, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if cp.returncode != 0 and _logger.isEnabledFor(logging.DEBUG):
        _logger.debug("Execution failed: ec=%s, output=[%s], stderr=[%s] ", cp.returncode, cp.stdout, cp.stderr)
    return cp.returncode, cp.stdout.decode('utf-8'), cp.stderr.decode('utf-8')


def call(cmd, log_output=True):
    """
    Execute a command.

    Parameters
    ----------
    cmd: list
        Command line as list of strings.
    log_output: bool
        Write error messages to logfile if set.

    Returns
    -------
        int
            The command return code.
    """
    _c = _prepare_command(cmd)
    try:
        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug('Executing [%s]', _c)
        cp = subprocess.run(_c, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if cp.returncode != 0 and log_output:
            _logger.debug("Execution failed: ec=%s, output=[%s], stderr=[%s] ", cp.returncode, cp.stdout, cp.stderr)
        return cp.returncode
    except OSError:
        return 404


def call_output(cmd, log_output=True):
    """
    Executes a command.

    Parameters
    ----------
    cmd: list
        Command line as list of strings.
    log_output: bool
        Write error messages to logfile if set.

    Returns
    -------
        str
            The stdout and stderr, on success.
        int
            404 on OSError.
        None
            When command execution fails.
    """
    _c = _prepare_command(cmd)
    try:
        return subprocess.check_output(_c, stderr=subprocess.STDOUT)
    except OSError:
        return 404
    except subprocess.CalledProcessError as e:
        if log_output:
            if _logger.isEnabledFor(logging.DEBUG):
                # pylint: disable=logging-not-lazy,logging-format-interpolation
                _logger.debug("Error executing {}: {}\n{}\n".format(_c, e.returncode, e.output.decode('utf-8')))
        return None


def call_popen_output(cmd, log_output=True):
    """
    Executes a command.

    Parameters
    ----------
    cmd: list
        Command line as list of strings.
    log_output: bool
        Write error messages to logfile if set.

    Returns
    -------
        str
            The stdout and stderr, on success.
        int
            404 on OSError.
        None
            When command execution fails.
    """
    _c = _prepare_command(cmd)
    try:
        p = subprocess.Popen(' '.join(_c), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return p.communicate()[0]
    except OSError:
        return 404
    except subprocess.CalledProcessError as e:
        if log_output:
            if _logger.isEnabledFor(logging.DEBUG):
                _logger.debug("Error executing {}: {}\n{}\n".format(_c, e.returncode, e.output))
        return None


def create_dir(path):
    """
    Creates a directory.

    Parameters
    ----------
    path: str
        The full path of the directory.

    Returns
    -------
        The return code fo the mkdir command.
    """
    return call([MKDIR_CMD, '--parents', path])


def delete_file(path):
    """
    Delete a file.

    Parameters
    ----------
    path: str
        The full path of the file.

    Returns
    -------
        The return code fo the delete command.
    """
    return call([RM_CMD, '-f', path])


def copy_file(path, newpath):
    """
    Copy a file.

    Parameters
    ----------
    path: str
        The full path of the file.
    newpath: str
        The full destination path.
    Returns
    -------
        The return code fo the delete command.
    """
    return call([CP_CMD, '--archive', path, newpath])


def write_to_file(path, content):
    """
    Overwrite content of a file with given content

    Parameters
    ----------
    path: str
        The full path of the file.
    content: str
        The text to be writen

    Returns
    -------
        The return code fo the cat(1) command.
    """

    _c = _prepare_command([SH_CMD, '-c', '%s > %s' % (CAT_CMD, path)])
    (_, err) = subprocess.Popen(_c,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                stdin=subprocess.PIPE).communicate(content.encode())
    if err:
        _logger.debug("Error writing content to file: %s", err)
        return 1
    return 0


def create_file(path, mode=None):
    """
    create a file

    Parameters
    ----------
    path: str
        The full path of the file.
    mode: str
        the mode to apply to the file

    Returns
    -------
        The return code fo the cat(1) command.
    """
    _logger.debug("Creating file : %s", path)
    res = call([TOUCH_CMD, path])
    if res == 0 and mode is not None:
        res = set_file_mode(path, mode)
    return res


def set_file_mode(path, mode=None):
    """
    set access mode of a  file

    Parameters
    ----------
    path: str
        The full path of the file.
    mode: str
        the mode to apply to the file

    Returns
    -------
        The return code fo the chmod(1) command.
    """
    _logger.debug("Applying mode  %s to file %s", mode, path)
    return call([CHMOD_CMD, mode, path])
