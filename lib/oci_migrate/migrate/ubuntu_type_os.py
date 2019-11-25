# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing Ubuntu Linux type specific OS methods.
"""
import logging

from oci_migrate.migrate import config
from oci_migrate.migrate import gen_tools
from oci_migrate.migrate.exception import OciMigrateException

logger = logging.getLogger('oci-utils.oci-image-migrate')

_os_type_tag_csl_tag_type_os_ = 'ubuntu, debian,'


def os_banner():
    """
    Show OS banner.
    Returns
    -------
        No return value.
    """
    gen_tools.result_msg('OS is one of %s' % _os_type_tag_csl_tag_type_os_,
                         result=True)


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
    logger.debug('apt command: %s' % cmd)
    try:
        logger.debug('command: %s' % cmd)
        output = gen_tools.run_popen_cmd(cmd)
        logger.debug('apt command output: %s' % str(output))
        return output
    except Exception as e:
        logger.critical('Failed to execute apt: %s' % str(e))
        raise OciMigrateException('\nFailed to execute apt: %s' % str(e))


def install_cloud_init(*args):
    """
    Install cloud init package
    Parameters
    ----------
    args: tbd

    Returns
    -------
        bool: True on success, raise an exception otherwise.
    """
    try:
        if gen_tools.set_nameserver():
            logger.debug('Updating nameserver info succeeded.')
        else:
            logger.error('Failed to update nameserver info.')
        #
        deblist = exec_apt(['list', 'cloud-init'])
        cloud_init_present = False
        for l in deblist.splitlines():
            logger.debug('%s' % l)
            if 'cloud-init' in l:
                logger.debug('The deb package cloud-init is available.')
                cloud_init_present = True
                break
        if not cloud_init_present:
            logger.error('The deb package cloud-init is missing.')
            config.migrate_preparation = False
            config.migrate_non_upload_reason += '\n  The deb package cloud-init ' \
                                              'is missing from the repository.'
            raise OciMigrateException('The deb package cloud-init is missing '
                                      'from the repository.')
        else:
            installoutput = exec_apt(['install', '-y', 'cloud-init'])
            logger.debug('Successfully installed cloud init:\n%s' % installoutput)
        # gen_tools.pause_msg('Installed cloud-init here, or not.')
        if gen_tools.restore_nameserver():
            logger.debug('Restoring nameserver info succeeded.')
        else:
            logger.error('Failed to restore nameserver info.')
    except Exception as e:
        logger.critical('Failed to install the cloud-init package:\n%s' % str(e))
        gen_tools.error_msg('Failed to install the cloud-init package:\n%s' % str(e))
        raise OciMigrateException('Failed to install the cloud-init package:\n%s' % str(e))
    return True
