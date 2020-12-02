# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing Ubuntu Linux type specific OS methods.
"""
import logging
import os
import stat

from oci_utils.migrate import console_msg
from oci_utils.migrate import error_msg
from oci_utils.migrate import migrate_data
from oci_utils.migrate import migrate_tools
from oci_utils.migrate import pause_msg
from oci_utils.migrate import system_tools
from oci_utils.migrate.decorators import is_an_os_specific_method
from oci_utils.migrate.exception import OciMigrateException
from oci_utils.migrate.migrate_tools import get_config_data

_logger = logging.getLogger('oci-utils.ubuntu-type-os')

_os_type_tag_csl_tag_type_os_ = 'ubuntu, debian,'


def execute_os_specific_tasks():
    """
    Executes the marked methods.

    Returns
    -------
    dict: the return values.
    """
    os_specific_job = OsSpecificOps()
    os_return_values = migrate_tools.call_os_specific_methods(os_specific_job)
    return os_return_values


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


    This class just contains methods to be executed only on Ubuntu os type
    images. Only the methods marked by the decorator is_an_os-specific_method
    will be called. The methods do not need to be static. This class can be
    extended as necessary. It is the responsibility of the implementation to
    provide all code and data by those extensions.

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

    @staticmethod
    def _exec_apt(cmd):
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
        _logger.debug('apt command: %s', cmd)
        try:
            _logger.debug('command: %s', cmd)
            output = system_tools.run_popen_cmd(cmd)['output'].decode('utf-8')
            _logger.debug('apt command output: %s', str(output))
            return output
        except Exception as e:
            _logger.warning('   Failed to execute apt: %s', str(e))
            raise OciMigrateException('\nFailed to execute apt:') from e

    @is_an_os_specific_method
    def a10_remove_cloud_init(self):
        """
        Remove cloud-init package and configuration

        Returns
        -------
            bool: True on success, False otherwise.
        """
        _logger.debug('__ Remove existing cloud_init config.')
        try:
            #
            # write 90_dpkg.cfg
            dpkg_cfg_path = '/etc/cloud/cloud.cfg.d'
            if os.path.exists(dpkg_cfg_path):
                with open(dpkg_cfg_path + '/90_dpkg.cfg', 'w') as f:
                    f.write('datasource_list: [None]\n')
                _logger.debug('%s (re)written.', dpkg_cfg_path)
            else:
                _logger.debug('%s does not exist.', dpkg_cfg_path)
            #
            # remove cloud-init package
            purge_output = self._exec_apt(['purge', 'cloud-init', '-y'])
            _logger.debug('cloud-init purged: %s', purge_output)
            #
            # remove /etc/cloud
            cloud_cfg_path = '/etc/cloud'
            backup_cloud_path = system_tools.exec_rename(cloud_cfg_path)
            if bool(backup_cloud_path):
                _logger.debug('%s renamed to %s', cloud_cfg_path, backup_cloud_path)
            #
            # remove /var/lib/cloud
            var_lib_cloud_path = '/var/lib/cloud'
            backup_var_lib_cloud_path = system_tools.exec_rename(var_lib_cloud_path)
            if bool(backup_var_lib_cloud_path):
                _logger.debug('%s renamed to %s', var_lib_cloud_path, backup_var_lib_cloud_path)
            #
            # remove logs
            cloud_init_log = '/var/log/cloud-init.log'
            backup_cloud_init_log = system_tools.exec_rename(cloud_init_log)
            if bool(cloud_init_log):
                _logger.debug('%s renamed to %s', cloud_init_log, backup_cloud_init_log)
            #
            pause_msg(msg='cloud-init removed', pause_flag='_OCI_CHROOT')
            return True
        except Exception as e:
            _logger.warning('Failed to purge cloud-init completely which might cause issues '
                            'at instance creation: %s', str(e))
            return False

    @is_an_os_specific_method
    def a20_install_extra_pkgs(self):
        """
        Install required and useful packages for OL-type installs, read the
        list of packages from oci-migrate-conf.yaml, ol_os_packages_to_install.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        def get_ubuntu_package_list():
            """
            Retrieve the list of packages to install from oci-migrate-config file.

            Returns
            -------
            list: list of package names to install.
            """
            _logger.debug('Collection list of packages.')
            try:
                pkg_list = get_config_data('ubuntu_os_packages_to_install_apt')
                if not bool(pkg_list):
                    _logger.debug('apt package list is empty.')
                    return False
                _logger.debug('Package list: %s', pkg_list)
                return pkg_list
            except Exception as e:
                _logger.warning('Failed to find a list of packages: %s', str(e))
                return False

        _logger.debug('Installing extra packages.')
        packages = get_ubuntu_package_list()
        if not bool(packages):
            _logger.debug('No extra packages to install.')
            return True
        try:
            #
            # set current nameserver config.
            if system_tools.set_nameserver():
                _logger.debug('Updating nameserver info succeeded.')
            else:
                _logger.error('  Failed to update nameserver info.')

            #
            # update package list
            update_output = self._exec_apt(['update'])
            _logger.debug('Successfully updated package list.')
            #
            # install packages
            for pkg in packages:
                #
                # verify if the package is available.
                pkg_present = False
                deblist = self._exec_apt(['list', pkg])
                for lline in deblist.splitlines():
                    _logger.debug('%s', lline)
                    if pkg in lline:
                        _logger.debug('The deb package %s is available.', pkg)
                        pkg_present = True
                        break
                if not pkg_present:
                    _logger.debug('The deb package %s is missing.', pkg)
                    migrate_data.migrate_preparation = False
                    migrate_data.migrate_non_upload_reason +=\
                        '\n  The deb package %s is missing from ' \
                        'the repository.' % pkg
                    return False

                installoutput = self._exec_apt(['install', '-y', pkg])
                _logger.debug('Successfully installed %s:\n%s', pkg, installoutput)
                pause_msg(msg='Installed %s here, or not.' % pkg, pause_flag='_OCI_CHROOT')

            if system_tools.restore_nameserver():
                _logger.debug('Restoring nameserver info succeeded.')
            else:
                _logger.error('  Failed to restore nameserver info.')

        except Exception as e:
            _logger.critical('   Failed to install one or more packages of %s:\n%s', packages, str(e))
            error_msg('Failed to install one or more packages of %s:\n%s' % (packages, str(e)))
            migrate_data.migrate_non_upload_reason += \
                '\n Failed to install on or more packages ' \
                'of %s: %s' % (packages, str(e))
            return False
        return True

    @staticmethod
    @is_an_os_specific_method
    def a90_reinitialise_cloud_init():
        """
        Installs a script to reinitialise the cloud_init service.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        _logger.debug('__ Copy the reinitialise cloud init script.')
        #
        # get the script name
        try:
            #
            # get the script name
            reinitialise_cloud_init_script = \
                get_config_data('reinitialise_cloud_init_script')
            _logger.debug('Got reinitialise_cloud_init_script name: %s', reinitialise_cloud_init_script)
            #
            # write the reinitialise script code
            with open(reinitialise_cloud_init_script, 'w') as fi:
                fi.writelines(ln + '\n'
                              for ln in
                              get_config_data('reinitialise_cloud_init'))
            os.chmod(reinitialise_cloud_init_script, stat.S_IRWXU)
        except Exception as e:
            _logger.warning('Failed to collect the reinitialise_cloud_init_script path: %s', str(e))
            return False
        return True

    @staticmethod
    @is_an_os_specific_method
    def b10_is_cloud_init_enabled():
        """
        Verify if cloud-init package is enabled after install.
        Returns
        -------
           bool: True on success, False otherwise.
        """
        _logger.debug('__ Is cloud-init enabled.')
        cmd = ['systemctl', 'list-unit-files']
        enabled = False
        try:
            _logger.debug('command: %s', cmd)
            output = system_tools.run_popen_cmd(cmd)['output'].decode('utf-8').splitlines()
            for service in output:
                svc = service.split() if len(service) > 1 else ['a', 'b']
                if 'cloud-init' in svc[0]:
                    _logger.debug('Found service cloud-init: %s', svc)
                    if svc[-1] == 'enabled':
                        _logger.debug('Service cloud-init is enabled.')
                        enabled = True
                        break
            return enabled
        except Exception as e:
            _logger.warning('   Failed to execute systemctl: %s', str(e))
            raise OciMigrateException('\nFailed to execute systemctl: ') from e

    @is_an_os_specific_method
    def b30_install_snap_packages(self):
        """
        Add a job to the cloud-init config file to install additional packages
        by snap at first boot. (snapd cannot be run while in chroot during
        image preparation.)

        Returns
        -------
           bool: True on success, False otherwise. (always True as packages to
                 be installed via snap are not considered essential.)
        """
        def get_ubuntu_snap_package_list():
            """
            Retrieve the list of packages to install from oci-migrate-config file.

            Returns
            -------
            list: list of package names to install.
            """
            _logger.debug('__ Collection list of snap packages.')
            try:
                snap_pkg_list = get_config_data('ubuntu_os_packages_to_install_snap')
                if bool(snap_pkg_list):
                    pkg_list = '('
                else:
                    _logger.debug('snap package list is empty.')
                    return False
                _logger.debug('Package list: %s', snap_pkg_list)
                for pkg in snap_pkg_list:
                    pkg_list = pkg_list.__add__("'")\
                        .__add__(pkg)\
                        .__add__("'")\
                        .__add__(" ")
                pkg_list = pkg_list.__add__(')')
                _logger.debug('Package list: %s', pkg_list)
                return pkg_list
            except Exception as e:
                _logger.warning('Failed to find a list of packages: %s', str(e))
                return False

        _logger.debug('__ Install software packages using snap.')
        try:
            #
            # collect packages to install
            packages = get_ubuntu_snap_package_list()
            if not bool(packages):
                _logger.debug('No extra packages to install.')
                return True
            #
            # get snapd script name
            ubuntu_os_snap_install_script = \
                get_config_data('ubuntu_os_snap_install_script')
            _logger.debug('snap package install script: %s', ubuntu_os_snap_install_script)
            #
            # get, update and write the script.
            with open(ubuntu_os_snap_install_script, 'w') as bashf:
                bashf.writelines(
                    ln.replace('_XXXX_', packages) + '\n'
                    for ln in get_config_data('ubuntu_os_snapd_bash'))
            os.chmod(ubuntu_os_snap_install_script, stat.S_IRWXU)
            #
            # update cloud-init with runcmd command
            if migrate_tools.update_cloudconfig_runcmd(ubuntu_os_snap_install_script):
                _logger.debug('snap install script successfully added.')
                migrate_tools.result_msg(msg='snap packages install script '
                                             'successfully added.', result=False)
            else:
                _logger.debug('Failed to add snap install script.')
        except Exception as e:
            _logger.warning('Failed to install one or more packages of %s:\n%s', packages, str(e))
            #
            # not considered as essential or fatal.
        return True