# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module containing Some Linux type specific OS methods; intended as a
template.
"""
import logging

from oci_migrate.migrate import gen_tools
from oci_migrate.migrate.exception import OciMigrateException

logger = logging.getLogger('oci-utils.oci-image-migrate')

_os_type_tag_csl_tag_type_os_ = 'sometype,'


def os_banner():
    """
    Show OS banner.
    Returns
    -------
        No return value.
    """
    gen_tools.result_msg(msg='OS is one of %s' % _os_type_tag_csl_tag_type_os_,
                         result=True)


def install_cloud_init(*args):
    """
    Install cloud init package
    Parameters
    ----------
    args: tbd

    Returns
    -------

    """
    pass
