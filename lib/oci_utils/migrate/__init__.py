# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import sys
import termios
import threading
import time
import tty
from datetime import datetime

import yaml


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


def read_yn(prompt, yn=True, waitenter=False, suppose_yes=False):
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
    #
    # add y/N to prompt if necessary.
    if yn:
        yn_prompt += ' (y/N) '
    #
    # if wait is set, wait for return key.
    if waitenter:
        resp_len = 0
        while resp_len == 0:
            resp = input(yn_prompt).lstrip()
            resp_len = len(resp)
        yn = list(resp)[0]
    #
    # if wait is not set, proceed on any key pressed.
    else:
        _ = sys.stdout.write(yn_prompt)
        sys.stdout.flush()
        yn = _getch()

    sys.stdout.write('\n')
    if yn.upper() == 'Y':
        return True
    else:
        return False


def exit_with_msg(msg, exit_code=1):
    """
    Post a message on stdout and exit.

    Parameters
    ----------
    msg: str
        The exit message.
    exit_code: int
        The exit code, default is 1.

    Returns
    -------
        No return value.
    """
    sys.stderr.write('\n  %s\n' % msg)
    exit(exit_code)


def pause_msg(msg=None, pause_flag='_OCI_PAUSE'):
    """
    Pause function.

    Parameters:
    ----------
    msg: str
        Eventual pause message.

    Returns
    -------
        No return value.
    """
    if os.environ.get('_OCI_PAUSE') or os.environ.get(pause_flag):
        ban0 = '\n  Press a key to continue'
        if msg is not None:
            ban0 = '\n  %s' % msg + ban0
        _ = read_yn(ban0, False)


def console_msg(msg=None):
    """
    Writes a message to the console.

    Parameters:
    ----------
        msg: str
            The message
    Returns:
    -------
         No return value.
    """
    if msg is None:
        msg = 'Notification.'
    sys.stdout.write('\n  %s\n' % msg)


def bytes_to_hex(bs):
    """
    Convert a byte string to an hex string.

    Parameters
    ----------
    bs: str
       byte string

    Returns
    -------
        str: hex string
    """
    return ''.join('%02x' % i for i in bs)


def terminal_dimension():
    """
    Collect the dimension of the terminal window.

    Returns
    -------
        tuple: (nb rows, nb colums)
    """
    rowstr, colstr = os.popen('stty size', 'r').read().split()
    return int(rowstr), int(colstr)


class OciMigrateConfParam(object):
    """
    Retrieve oci-image-migrate configuration data from the
    oci-image-migrate configuration file, in yaml format.
    """

    def __init__(self, yamlconf, tag):
        """
        Initialisation of the oci image migrate configuration retrieval.

        Parameters:
        ----------
            yamlconf: str
                The full path of the oci-image-migrate configuration file.
            tag: str
                The configuration structure to collect.
        """
        self._yc = yamlconf
        self._tg = tag

    def __enter__(self):
        """
        OciMigrateConfParam entry.
        """
        with open(self._yc, 'r') as f:
            self.confdata = yaml.load(f, Loader=yaml.SafeLoader)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        OciMigrateConfParam cleanup and exit.
        """
        pass

    def get_values(self):
        """
        Retrieve the configuration data, one entry if key is not '*', complete
        data otherwise.
        """
        return self.confdata if self._tg == '*' else self.confdata[self._tg]


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
        # length of variable progress bar
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
        j = i % self._nb_prog_chars
        #
        # counter in bar
        k = 0
        sys.stdout.write('\n')
        sys.stdout.flush()
        start_time = datetime.now()
        while True:
            now_time = datetime.now()
            delta_time = now_time - start_time
            hrs, rest = divmod(delta_time.seconds, 3600)
            mins, secs = divmod(rest, 60)
            pbar = '  ' \
                   + '%02d:%02d:%02d' % (hrs, mins, secs) \
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
                j = i % self._nb_prog_chars
            time.sleep(self._prog_int)
            if self.stop_the_progress_bar:
                now_time = datetime.now()
                delta_time = now_time - start_time
                hrs, rest = divmod(delta_time.seconds, 3600)
                mins, secs = divmod(rest, 60)
                pbar = '  ' \
                    + '%02d:%02d:%02d' % (hrs, mins, secs) \
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

