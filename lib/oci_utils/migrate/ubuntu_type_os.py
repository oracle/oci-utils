# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing Ubuntu Linux type specific OS methods.
"""
import logging

from oci_utils.migrate import console_msg, pause_msg
from oci_utils.migrate import migrate_tools
from oci_utils.migrate.exception import OciMigrateException

_logger = logging.getLogger('oci-utils.ubuntu-type-os')

_os_type_tag_csl_tag_type_os_ = 'ubuntu, debian,'


def os_banner():
    """
    Show OS banner.
    Returns
    -------
        No return value.
    """
    console_msg('OS is one of %s' % _os_type_tag_csl_tag_type_os_)


def exec_apt(cmd):
    """
    Execute an apt command.

    Parameters
    ----------
    cmd: list
        The apt command as a list.

    Returns
    -------
        str: apt output on success, raises an exception otherwise.
    """
    cmd = ['/usr/bin/apt'] + cmd
    _logger.debug('apt command: %s' % cmd)
    try:
        _logger.debug('command: %s' % cmd)
        output = migrate_tools.run_popen_cmd(cmd).decode('utf-8')
        _logger.debug('apt command output: %s' % str(output))
        return output
    except Exception as e:
        _logger.critical('Failed to execute apt: %s' % str(e))
        raise OciMigrateException('\nFailed to execute apt: %s' % str(e))


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
    try:
        if migrate_tools.set_nameserver():
            _logger.debug('Updating nameserver info succeeded.')
        else:
            _logger.error('Failed to update nameserver info.')
        #
        deblist = exec_apt(['list', 'cloud-init'])
        cloud_init_present = False
        for pkg in deblist.splitlines():
            _logger.debug('%s' % pkg)
            if 'cloud-init' in pkg:
                _logger.debug('The deb package cloud-init is available.')
                cloud_init_present = True
                break
        if not cloud_init_present:
            _logger.debug('The deb package cloud-init is missing.')
            migrate_tools.migrate_preparation = False
            migrate_tools.migrate_non_upload_reason += \
                '\n  The deb package cloud-init is missing from the repository.'
            return False
        else:
            installoutput = exec_apt(['install', '-y', 'cloud-init'])
            _logger.debug('Successfully installed cloud init:\n%s' % installoutput)
        pause_msg('Installed cloud-init here, or not.')
        if migrate_tools.restore_nameserver():
            _logger.debug('Restoring nameserver info succeeded.')
        else:
            _logger.error('Failed to restore nameserver info.')
    except Exception as e:
        _logger.critical('Failed to install the cloud-init package:\n%s' % str(e))
        migrate_tools.error_msg('Failed to install the cloud-init package:\n%s' % str(e))
        migrate_tools.migrate_non_upload_reason += \
            '\n Failed to install the cloud-init package: %s' % str(e)
        return False
    return True
