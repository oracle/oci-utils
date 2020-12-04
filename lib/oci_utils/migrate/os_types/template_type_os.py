# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module containing a Template Linux type specific OS methods; intended as a
template.
"""
import logging

from oci_utils.migrate import console_msg
from oci_utils.migrate import migrate_tools
from oci_utils.migrate.decorators import is_an_os_specific_method

_logger = logging.getLogger('oci-utils.template-type-os')

_os_type_tag_csl_tag_type_os_ = 'templatetype,'


def os_banner():
    """
    Show OS banner.
    Returns
    -------
        No return value.
    """
    console_msg('OS is one of %s' % _os_type_tag_csl_tag_type_os_)


class OsSpecificOps():
    """
    Class containing specific operations for OL-type images.

    This class just contains methods to be executed only on template_type_os
    os type images. Only the methods marked by the decorator is_an_os-specific_
    method will be called. The methods do not need to be static. This class
    can be extended as necessary. It is the responsibility of the
    implementation to provide all code and data by those extensions.

    The os specific methods are called via execute_os_specific_tasks. One
    needs to take into account execute_os_specific_tasks is executed while in
    the chroot jail.
    """
    def __init__(self, **kwargs):
        """
        Idle, the kwargs arguments can be used in future versions to pass
        parameters to the methods.

        Parameters
        ----------
        kwargs: for future use, to pass parameters to the methods.
        """
        pass

    @is_an_os_specific_method
    def install_extra_pkgs(self):
        """
        Install required and useful packages for OL-type installs, read the
        list of packages from oci-migrate-conf.yaml, ol_os_packages_to_install.

        Returns
        -------
            bool: True on success, False otherwise.
        """

        def get_template_package_list():
            """
            Retrieve the list of packages to install from oci-migrate-config file.

            Returns
            -------
            list: list of package names to install.
            """
            _logger.debug('Collection list of packages.')
            return list()

        def exec_install_template_pkg(cmd):
            """
            Execute an install command.

            Parameters
            ----------
            cmd: list
                The install command line.

            Returns
            -------
                str: yum output on success, raises an exception otherwise.
            """
            return 'success'

        _logger.debug('Installing extra packages.')
        packages = get_template_package_list()
        #
        # install the packages.
        return True


def execute_os_specific_tasks():
    """
    Executes the marked methods.

    Returns
    -------
    dict: the return values.
    """
    _logger.debug('__ OS specific tasks.')
    os_specific_job = OsSpecificOps()
    os_return_values = migrate_tools.call_os_specific_methods(os_specific_job)
    _logger.debug('OS specific tasks: %s', os_return_values)
    return os_return_values
