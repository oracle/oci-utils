# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing Oracle Linux type specific OS methods.
"""
import logging

from oci_utils.migrate import console_msg, pause_msg
from oci_utils.migrate import migrate_tools
from oci_utils.migrate.exception import OciMigrateException

_logger = logging.getLogger('oci-utils.ol-type-os')

_os_type_tag_csl_tag_type_os_ = 'ol, rhel, fedora, centos,'


def os_banner():
    """
    Show OS banner.
    Returns
    -------
        No return value.
    """
    console_msg('OS is one of %s' % _os_type_tag_csl_tag_type_os_)


def exec_yum(cmd):
    """
    Execute a yum command.

    Parameters
    ----------
    cmd: list
        The yum command parameters as s list.

    Returns
    -------
        str: yum output on success, raises an exception otherwise.
    """
    cmd = ['yum'] + cmd
    _logger.debug('yum command: %s' % cmd)
    try:
        _logger.debug('command: %s' % cmd)
        output = migrate_tools.run_popen_cmd(cmd)
        _logger.debug('yum command output: %s' % str(output))
        return output
    except Exception as e:
        _logger.critical('Failed to execute yum: %s' % str(e))
        raise OciMigrateException('\nFailed to execute yum: %s' % str(e))


def install_cloud_init(*args):
    """
    Install the cloud-init package.

    Parameters
    ----------
    args: tuple
        1 argument expected, the VERSION_ID as a string and as specified in the
        os-release file.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    try:
        #
        # set current nameserver config.
        if migrate_tools.set_nameserver():
            _logger.debug('Updating nameserver info succeeded.')
        else:
            _logger.error('Failed to update nameserver info.')
        #
        # verify if latest channel is enabled.
        rpmlist = exec_yum(['list', 'cloud-init'])
        cloud_init_present = False
        for l in rpmlist.splitlines():
            _logger.debug('%s' % l)
            if 'cloud-init' in l:
                _logger.debug('The rpm cloud-init is available.')
                cloud_init_present = True
                break
        if not cloud_init_present:
            _logger.error('The rpm cloud-init is missing.')
            migrate_tools.migrate_preparation = False
            migrate_tools.migrate_non_upload_reason += \
                '\n  The rpm package cloud-initis missing from the yum repository.'
            return False
        else:
            installoutput = exec_yum(['install', '-y', 'cloud-init'])
            _logger.debug('Successfully installed cloud init:\n%s'
                         % installoutput)
        pause_msg('Installed cloud-init here, or not.')
        if migrate_tools.restore_nameserver():
            _logger.debug('Restoring nameserver info succeeded.')
        else:
            _logger.error('Failed to restore nameserver info.')
    except Exception as e:
        _logger.critical('Failed to install cloud init package:\n%s' % str(e))
        migrate_tools.error_msg('Failed to install cloud init package:\n%s' % str(e))
        migrate_tools.migrate_non_upload_reason += \
            '\n Failed to install cloud init package: %s' % str(e)
        return False
    return True
