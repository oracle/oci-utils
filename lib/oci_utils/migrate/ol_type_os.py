#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing Oracle Linux type specific OS methods.
"""
import logging
import os
import sys

# for the sake of testing
sys.path.append('/omv/data/git_pycharm/oci-utils/lib')
from oci_utils.migrate import gen_tools
from oci_utils.migrate.exception import OciMigrateException
from oci_utils.migrate import migrate_utils as migrate_utils
from oci_utils.migrate import data
from glob import glob

logger = logging.getLogger('oci-image-migrate')

_os_type_tag_csl_tag_type_os_ = 'ol, rhel, fedora, centos'


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
    # gen_tools.prog_msg('Installing the cloud-init package.')
    try:
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
            raise OciMigrateException('The rpm cloud-init is missing '
                                      'from the yum repository.')
        else:
            installoutput = exec_yum(['install', '-y', 'cloud-init'])
            logger.debug('Successfully installed cloud init:\n%s'
                         % installoutput)
    except Exception as e:
        logger.critical('Failed to install cloud init package:\n%s' % str(e))
        gen_tools.error_msg('Failed to install cloud init package:\n%s' % str(e))
        raise OciMigrateException('\nFailed to install cloud init package: %s'
                                  % str(e))
    return True


def update_network_config():
    """
    Modify the network configuration in the image file to prevent
    conflicts during import. This is only for ol-type linux.

    Returns
    -------
        bool: True on success, raise exception on failure
    """
    #
    # Rename the config files
    gen_tools.prog_msg('Updating the network configuration.')
    ifrootdir = '/etc/sysconfig/network-scripts'
    for fn in glob(ifrootdir + '/ifcfg-*'):
        if 'ifcfg-lo' not in fn:
            if migrate_utils.exec_rename(fn, os.path.split(fn)[0]
                                             + '/bck_'
                                             + os.path.split(fn)[1]
                                             + '_bck'):
                logger.debug('Network config file %s successfully '
                             'renamed to %s' % (fn, os.path.split(fn)[0]
                                                + '/bck_'
                                                + os.path.split(fn)[1]
                                                + '_bck'))
            else:
                logger.error('Failed to rename network config file %s '
                             'to %s' % (fn, os.path.split(fn)[0]
                                        + '/bck_'
                                        + os.path.split(fn)[1]
                                        + '_bck'))
                raise OciMigrateException('Failed to rename network config '
                                          'file %s to %s'
                                          % (fn, os.path.split(fn)[0]
                                             + '/bck_'
                                             + os.path.split(fn)[1]
                                             + '_bck'))
    #
    # Generate new default network configuration.
    try:
        with open('/etc/sysconfig/network-scripts/ifcfg-eth0', 'w') as f:
            f.writelines('%s\n' % ln
                         for ln in data.default_if_network_config)
    except Exception as e:
        logger.error(
            'Failed to write /etc/sysconfig/network-scripts/ifcfg-eth0')
        gen_tools.error_msg(
            'Failed to write /etc/sysconfig/network-scripts/ifcfg-eth0: %s'
            % str(e))
        raise OciMigrateException(
            'Failed to write /etc/sysconfig/network-scripts/ifcfg-eth0: %s'
            % str(e))
    return True


def get_network_data(rootdir):
    """
    Collect the network configuration files.

    Parameters
    ----------
    rootdir: str
        Full path of image root dir as loopback mounted.

    Returns
    -------
        dict: List with dictionary representation of the network
        configuration files.
    """
    network_list = dict()
    network_dir = rootdir + '/etc/sysconfig/network-scripts'
    logger.debug('Network directory: %s' % network_dir)
    try:
        for cfgfile in glob(network_dir + '/ifcfg-*'):
            with open(cfgfile, 'rb') as f:
                nl = filter(None, [x[:x.find('#')] for x in f])
            ifcfg = dict(l.translate(None, '"').split('=') for l in nl)
            network_list.update({cfgfile.split('/')[-1]: ifcfg})
            logger.debug('Network interface: %s : %s' %
                               (cfgfile.split('/')[-1], ifcfg))
            gen_tools.result_msg('Network interface: %s : %s' %
                                 (cfgfile.split('/')[-1], ifcfg))
    except Exception as e:
        logger.error('Problem reading network configuration files: %s' % str(e))
    return network_list
