# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module containing Some Linux type specific OS methods; intended as a
template.
"""
import logging

from oci_utils.migrate import console_msg
from oci_utils.migrate import migrate_tools
from oci_utils.migrate.exception import OciMigrateException

_logger = logging.getLogger('oci-utils.some-type-os')

_os_type_tag_csl_tag_type_os_ = 'sometype,'


def os_banner():
    """
    Show OS banner.
    Returns
    -------
        No return value.
    """
    console_msg('OS is one of %s' % _os_type_tag_csl_tag_type_os_)


def install_cloud_init(*args):
    """
    Install cloud init package
    Parameters
    ----------
    args: tbd

    Returns
    -------
        bool: True on success, False otherwise.
    """
    pass
