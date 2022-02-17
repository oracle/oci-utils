# oci-utils
#
# Copyright (c) 2017, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Common cache file utils for oci_utils.
"""

import fcntl
import json
import os
import shutil
import sys
from datetime import datetime
import logging

_GLOBAL_CACHE_DIR = "/var/cache/oci-utils"

_logger = logging.getLogger("oci-utils.cache")


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


def load_cache_11876(global_file, global_file_11876=None, user_file=None, max_age=None):
    """
    Wrapper for load_cache for LINUX_11876
    Load the contents of a json cache file. If both global and user cache
    files are given return the contents of the one that is newer. If the
    cache cannot be read or the age is older than max_age then return (0, None)

    global_file: str
        The global cache file.
    global_file_11876: str
        The old global cache file.
    user_file: str
        The user cache file.
    max_age: int
        The maximum age of the most recent cache file in seconds.

    Returns
    -------
        tuple
            (timestamp, file_contents)
    """
    _logger.debug('_Loading cache %s in compatibility mode.', global_file)
    if os.path.exists(global_file):
        try:
            if os.path.exists(global_file_11876):
                new_cache = shutil.copy(global_file_11876, global_file)
                _logger.debug('Cache %s copied to new location %s', global_file_11876, global_file)
                cache_timestamp, cache_content = load_cache(global_file=global_file,
                                                            user_file=user_file,
                                                            max_age=max_age)
                return cache_timestamp, cache_content
            else:
                _logger.debug('Cache file %s does not exists.', global_file_11876)
        except Exception as e:
            _logger.error('Failed to copy cache file %s to %s.', global_file_11876, global_file)
    else:
        # cache file does not yet exists
        _logger.debug('Cache file %s does not exist.', global_file)
    return 0, None


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
    _logger.debug('_Loading cache %s', global_file)

    cache_fname = get_newer(global_file, user_file)
    if cache_fname is None:
        return 0, None

    cache_timestamp = get_timestamp(cache_fname)
    if max_age:
        if datetime.fromtimestamp(cache_timestamp) + max_age < datetime.now():
            _logger.debug('Max age reached.')
            return 0, None

    try:
        cache_fd = os.open(cache_fname, os.O_RDONLY)
        cache_file = os.fdopen(cache_fd, 'r')
        # acquire a shared lock
        fcntl.lockf(cache_fd, fcntl.LOCK_SH)
    except IOError:
        # can't access file
        _logger.debug('Failed to load cache %s', cache_fname)
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


def write_cache_11876(cache_content, cache_fname, cache_fname_11876, fallback_fname=None, mode=None):
    """
    Wrapper for write_cache for LINUX_11876
    Save the cache_content as JSON data in cache_fname, or in fallback_fname
    if cache_fname is not writeable.

    Parameters
    ----------
    cache_content: dict
        The cache data.
    cache_fname: str
        The full path of the cache file.
    cache_fname_11876: str
        The full path of the old cache file.
    fallback_fname: str
        The full path of the fallback filename.
    mode: int
        The octal representation of the file permissions, if set.

    Returns
    -------
        str: the cache timestamp for success, None for failure
    """
    _logger.debug('_Writing cache file %s in compatibility mode.', cache_fname)
    try:
        timestamp_11876 = write_cache(cache_content=cache_content,
                                      cache_fname=cache_fname_11876,
                                      mode=mode)
    except Exception as e:
        _logger.error('Failed to write cache file %s: %s', cache_fname_11876, str(e))

    _logger.debug('Writing cache file %s', cache_fname)
    try:
        return write_cache(cache_content=cache_content,
                           cache_fname=cache_fname,
                           fallback_fname=fallback_fname,
                           mode=mode)
    except Exception as e:
        _logger.error('Failed to write cache file %s:%s', cache_fname, str(e))
        return None


def write_cache(cache_content, cache_fname, fallback_fname=None, mode=None):
    """
    Save the cache_content as JSON data in cache_fname, or in fallback_fname
    if cache_fname is not writeable.

    Parameters
    ----------
    cache_content: dict
        The cache data.
    cache_fname: str
        The full path of the cache filename.
    fallback_fname: str
        The full path of the fallback filename.
    mode: int
        The octal representation of the file permissions, if set.

    Returns
    -------
    Return the cache timestamp for success, None for failure
    """
    _logger.debug('_Writing to cache file')
    _logger.debug('Cache file %s.', cache_fname)
    _logger.debug('Cache content %s.', cache_content)
    fname = cache_fname
    #
    # try to write in cache_file first
    try:
        cachedir = os.path.dirname(cache_fname)
        if not os.path.exists(cachedir):
            os.makedirs(cachedir)
        if mode is not None:
            cache_fd = os.open(cache_fname, os.O_WRONLY | os.O_CREAT, mode)
        else:
            cache_fd = os.open(cache_fname, os.O_WRONLY | os.O_CREAT)
        cache_file = os.fdopen(cache_fd, 'w')
    except (OSError, IOError):
        #
        # can't write to cache_fname, try fallback_fname
        if not fallback_fname:
            return None
        cachedir = os.path.dirname(fallback_fname)
        try:
            if not os.path.exists(cachedir):
                os.makedirs(cachedir)
            if mode is not None:
                cache_fd = os.open(fallback_fname, os.O_WRONLY | os.O_CREAT, mode)
            else:
                cache_fd = os.open(fallback_fname, os.O_WRONLY | os.O_CREAT)
            cache_file = os.fdopen(cache_fd, 'w')
            fname = fallback_fname
        except (OSError, IOError):
            #
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
        _logger.debug('Failed to write cache %s', cache_fname)
        return None

    return cache_timestamp
