# oci-utils
#
# Copyright (c) 2017, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Common cache file utils for oci_utils.
"""

import fcntl
import json
import os
import sys
from datetime import datetime


_GLOBAL_CACHE_DIR = "/var/cache/oci-utils"


def get_cache_file_path(filename):
    """
    Get the cachefile path. All cache file are located at same location.

    Parameters
    ----------
    filename :
        The filename of the cache file.

    Returns
    -------
    str
        The full path to the cache file.
    """
    return os.path.join(_GLOBAL_CACHE_DIR, filename)


def get_timestamp(fname):
    """
    Return the last modification timestamp of a file. See os.path.getmtime().

    Returns
    -------
        int
            The last modification time since epoch in seconds, 0 if file
            does not exist.
    """
    if fname is None:
        return 0

    if os.path.exists(fname):
        return os.path.getmtime(fname)
    return 0


def get_newer(fname1, fname2):
    """
    Get the newer file, compare timestamp of files and return the file with
    the most recent modification time.

    Parameters
    ----------
    fname1: str
        Full path to filename, ignored if None.
    fname2: str
        Full path to filename, ignored if None.

    Returns
    -------
    str
        filename of the newer file
    """
    if fname1 is None or not os.path.exists(fname1):
        if fname2 is None or not os.path.exists(fname2):
            return None
        return fname2
    if fname2 is None or not os.path.exists(fname2):
        if fname1 is None or not os.path.exists(fname1):
            return None
        return fname1

    # both files exist
    if get_timestamp(fname1) > get_timestamp(fname2):
        return fname1
    return fname2


def load_cache(global_file, user_file=None, max_age=None):
    """
    Load the contents of a json cache file. If both global and user cache
    files are given return the contents of the one that is newer. If the
    cache cannot be read or the age is older than max_age then return (0, None)

    global_file: str
        The global cache file.
    user_file: str
        The user cache file.
    max_age: int
        The maximum age of the most recent cache file in seconds.

    Returns
    -------
        tuple
            (timestamp, file_contents)
    """
    cache_fname = get_newer(global_file, user_file)
    if cache_fname is None:
        return 0, None

    cache_timestamp = get_timestamp(cache_fname)
    if max_age:
        if datetime.fromtimestamp(cache_timestamp) + max_age < datetime.now():
            return 0, None

    try:
        cache_fd = os.open(cache_fname, os.O_RDONLY)
        cache_file = os.fdopen(cache_fd, 'r')
        # acquire a shared lock
        fcntl.lockf(cache_fd, fcntl.LOCK_SH)
    except IOError:
        # can't access file
        return 0, None

    try:
        cache_content = json.load(cache_file)
    except (IOError, ValueError):
        # can't read file
        cache_timestamp = 0
        cache_content = None

    fcntl.lockf(cache_fd, fcntl.LOCK_UN)
    cache_file.close()

    return cache_timestamp, cache_content


def write_cache(cache_content, cache_fname, fallback_fname=None, mode=None):
    """
    Save the cache_content as JSON data in cache_fname, or in fallback_fname
    if cache_fname is not writeable.

    Parameters
    ----------
    cache_content: dict
        The cache data.
    cache_fname: str
        The full path fo the cache filename.
    fallback_fname: str
        The full path of the fallback filename.
    mode: int
        The octal representation of the file permissions, if set.

    Returns
    -------
    Return the cache timestamp for success, None for failure
    """
    fname = cache_fname
    # try to save in cache_file first
    try:
        cachedir = os.path.dirname(cache_fname)
        if not os.path.exists(cachedir):
            os.makedirs(cachedir)
        if mode is not None:
            cache_fd = os.open(cache_fname, os.O_WRONLY | os.O_CREAT,
                               mode)
        else:
            cache_fd = os.open(cache_fname, os.O_WRONLY | os.O_CREAT)
        cache_file = os.fdopen(cache_fd, 'w')
    except (OSError, IOError):
        # can't write to cache_fname, try fallback_fname
        if not fallback_fname:
            return None
        cachedir = os.path.dirname(fallback_fname)
        try:
            if not os.path.exists(cachedir):
                os.makedirs(cachedir)
            if mode is not None:
                cache_fd = os.open(fallback_fname,
                                   os.O_WRONLY | os.O_CREAT, mode)
            else:
                cache_fd = os.open(fallback_fname,
                                   os.O_WRONLY | os.O_CREAT)
            cache_file = os.fdopen(cache_fd, 'w')
            fname = fallback_fname
        except (OSError, IOError):
            # can't write to fallback file either, give up
            return None
    try:
        json_content = json.dumps(cache_content)
    except Exception:
        sys.stderr.write("Internal error: invalid content for %s\n" % fname)

    try:
        # acquire exclusive lock
        fcntl.lockf(cache_fd, fcntl.LOCK_EX)
        cache_file.write(json_content)
        cache_file.truncate()
        cache_timestamp = get_timestamp(fname)
        fcntl.lockf(cache_fd, fcntl.LOCK_UN)
        cache_file.close()
    except Exception:
        fcntl.lockf(cache_fd, fcntl.LOCK_UN)
        cache_file.close()
        return None

    return cache_timestamp
