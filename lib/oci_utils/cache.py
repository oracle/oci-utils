#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2017, 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

"""
Common cache file utils for oci_utils
"""

import os
from os.path import getmtime, exists
from datetime import datetime, timedelta
import posixfile
import json

GLOBAL_CACHE_DIR = "/var/cache/oci-utils"

def get_timestamp(fname):
    """
    Return the last modification timestamp of a file.
    """
    if fname is None:
        return 0

    if os.path.exists(fname):
        return os.path.getmtime(fname)
    else:
        return 0

def get_newer(fname1, fname2):
    """
    Given 2 file names, fname1 and fname2, return the name of the file
    that is newer.  If only one of them exists, return that one.
    Return None if neither file exists.
    """
    if fname1 is None or not os.path.exists(fname1):
        if fname2 is None or not os.path.exists(fname2):
            return None
        else:
            return fname2
    if fname2 is None or not os.path.exists(fname2):
        if fname1 is None or not os.path.exists(fname1):
            return None
        else:
            return fname1

    # both files exist
    if get_timestamp(fname1) > get_timestamp(fname2):
        return fname1
    else:
        return fname2

def load_cache(global_file, user_file=None, max_age=None):
    """
    Load the contents of a json cache file.
    If both global and user cache files are give return the contents of
    the one that is newer.
    If the cache is cannot be read or the age is older than max_age
    then return (0, None)
    max_age is datetime.timedelta
    Return a tuple of (timestamp, file_contents)
    """

    cache_fname = get_newer(global_file, user_file)
    if cache_fname is None:
        return (0, None)

    cache_timestamp = get_timestamp(cache_fname)
    if max_age:
        if datetime.fromtimestamp(cache_timestamp) + max_age < datetime.now():
            return (0, None)

    try:
        cache_file = posixfile.open(cache_fname, "r")
        # acquire read lock
        cache_file.lock("r|")
    except IOError:
        # can't access file
        return (0, None)

    try:
        cache_content = json.load(cache_file)
        cache_file.lock("u")
        cache_file.close()
    except IOError, ValueError:
        # can't read file
        try:
            cache_file.lock("u")
            cache_file.close()
        except:
            pass
        return (0, None)

    return (cache_timestamp, cache_content)

def write_cache(cache_content, cache_fname, fallback_fname=None):
    """
    Save the cache_content as JSON data in cache_fname, or
    in fallback_fname if cache_fname is not writeable
    Return the cache timestamp for success, None for failure
    """

    cache_timestamp = None
    fname = cache_fname
    # try to save in cache_file first
    try:
        cachedir = os.path.dirname(cache_fname)
        if not os.path.exists(cachedir):
            os.makedirs(cachedir)
        if not os.path.exists(cache_fname):
            cache_file = posixfile.open(cache_fname, 'w+')
        else:
            cache_file = posixfile.open(cache_fname, 'r+')
    except (OSError, IOError):
        # can't write to cache_fname, try fallback_fname
        if not fallback_fname:
            return None
        cachedir = os.path.dirname(fallback_fname)
        try:
            if not os.path.exists(cachedir):
                os.makedirs(cachedir)
            if not os.path.exists(fallback_fname):
                cache_file = posixfile.open(fallback_fname, 'w+')
            else:
                cache_file = posixfile.open(fallback_fname, 'r+')
            fname = fallback_fname
        except (OSError, IOError) as e:
            # can't write to fallback file either, give up
            return None
    try:
        cache_file.lock("w|")
        cache_file.write(json.dumps(cache_content))
        cache_file.truncate()
        cache_timestamp = get_timestamp(fname)
        cache_file.lock("u")
        cache_file.close()
    except:
        try:
            cache_file.lock("u")
            cache_file.close()
        except:
            pass
        return None

    return cache_timestamp
