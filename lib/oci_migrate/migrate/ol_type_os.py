# #!/usr/bin/env python

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing Oracle Linux type specific OS methods.
"""
import logging

# for the sake of testing
from oci_migrate.migrate import configdata
from oci_migrate.migrate import gen_tools
from oci_migrate.migrate.exception import OciMigrateException

logger = logging.getLogger('oci-image-migrate')

_os_type_tag_csl_tag_type_os_ = 'ol, rhel, fedora, centos,'


def os_banner():
    """
    Show OS banner.
    Returns
    -------
        No return value.
    """
    gen_tools.result_msg(msg='OS is one of %s' % _os_type_tag_csl_tag_type_os_,
                         result=True)


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
    logger.debug('yum command: %s' % cmd)
    try:
        logger.debug('command: %s' % cmd)
        output = gen_tools.run_popen_cmd(cmd)
        logger.debug('yum command output: %s' % str(output))
        return output
    except Exception as e:
        logger.critical('Failed to execute yum: %s' % str(e))
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
        bool: True on success, raise an exception on failure.
    """
    try:
        #
        # set current nameserver config.
        if gen_tools.set_nameserver():
            logger.debug('Updating nameserver info succeeded.')
        else:
            logger.error('Failed to update nameserver info.')
        #
        # verify if latest channel is enabled.
        rpmlist = exec_yum(['list', 'cloud-init'])
        cloud_init_present = False
        for l in rpmlist.splitlines():
            logger.debug('%s' % l)
            if 'cloud-init' in l:
                logger.debug('The rpm cloud-init is available.')
                cloud_init_present = True
                break
        if not cloud_init_present:
            logger.error('The rpm cloud-init is missing.')
            configdata.migrate_prepartion = False
            configdata.migrate_non_upload_reason += '\n  The cloud-init rpm package ' \
                                              'is missing from the yum repository.'
            raise OciMigrateException('The rpm cloud-init is missing '
                                      'from the yum repository.')
        else:
            installoutput = exec_yum(['install', '-y', 'cloud-init'])
            logger.debug('Successfully installed cloud init:\n%s'
                         % installoutput)
        # gen_tools.pause_msg('Installed cloud-init here, or not.')
        if gen_tools.restore_nameserver():
            logger.debug('Restoring nameserver info succeeded.')
        else:
            logger.error('Failed to restore nameserver info.')
    except Exception as e:
        logger.critical('Failed to install cloud init package:\n%s' % str(e))
        gen_tools.error_msg('Failed to install cloud init package:\n%s' % str(e))
        raise OciMigrateException('\nFailed to install cloud init package: %s'
                                  % str(e))
    return True
