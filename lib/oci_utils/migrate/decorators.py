# oci-utils
#
# Copyright (c) 2020, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module with oci image migrate related decorators.
"""

import time
from functools import wraps

from oci_utils.migrate.exception import OciMigrateException


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
                # _logger.debug('State loop %d' % i)
                try:
                    funcret = func(*args, **kwargs)
                    return funcret
                except Exception as e:
                    # _logger.debug('Failed, sleeping for %d sec: %s'
                    #              % (intsec, str(e)))
                    if i == maxloop - 1:
                        raise OciMigrateException('State Loop exhausted:') from e
                    time.sleep(intsec)
        return loop_func
    return wrap


def is_an_os_specific_method(some_method):
    """
    A decorator to mark methods in the class OsSpecificOps as to be executed.

    Returns
    -------
    Adds an attribute to the method.
    """
    some_method._execute_as_os_specific = True
    return some_method
