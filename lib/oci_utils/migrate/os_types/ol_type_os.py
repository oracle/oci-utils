# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing Oracle Linux type specific OS methods.
"""
import logging
import os
import stat

import yaml

from oci_utils.migrate import console_msg
from oci_utils.migrate import error_msg
from oci_utils.migrate import migrate_data
from oci_utils.migrate import migrate_tools
from oci_utils.migrate import pause_msg
from oci_utils.migrate import result_msg
from oci_utils.migrate import system_tools
from oci_utils.migrate.decorators import is_an_os_specific_method
from oci_utils.migrate.exception import OciMigrateException
from oci_utils.migrate.migrate_tools import get_config_data

_logger = logging.getLogger('oci-utils.ol-type-os')

_os_type_tag_csl_tag_type_os_ = 'ol, rhel, fedora, centos,'


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


def os_banner():
    """
    Show OS banner.
    Returns
    -------
        No return value.
    """
    console_msg('OS is one of %s' % _os_type_tag_csl_tag_type_os_)


def get_package_mgr_tool():
    """
    Find out which package to use for package manipulation (yum or dnf) and
    define the essential parameters.

    Returns
    -------
        dict: dictionary with method and command parameters.
    """
    #
    # look for package install tool.

    package_mgr_dict = dict()
    if bool(system_tools.exec_exists('dnf')):
        _logger.debug('Upgrade using dnf')
        package_mgr_dict['pkg_mgr'] = 'dnf'
        package_mgr_dict['package_available'] = ['--showduplicates', 'search']
        package_mgr_dict['package_remove'] = ['erase', '-y']
        package_mgr_dict['package_install'] = ['install', '-y']
        package_mgr_dict['package_localinstall'] = ['localinstall', '-y']
    elif bool(system_tools.exec_exists('yum')):
        _logger.debug('Upgrade using yum')
        package_mgr_dict['pkg_mgr'] = 'yum'
        package_mgr_dict['package_available'] = ['--showduplicates', 'search']
        package_mgr_dict['package_remove'] = ['remove', '-y']
        package_mgr_dict['package_install'] = ['install', '-y']
        package_mgr_dict['package_localinstall'] = ['localinstall', '-y']
    else:
        raise OciMigrateException('Failed to find upgrade tool')
    _logger.debug('Package install tool data:\n %s', package_mgr_dict)
    return package_mgr_dict


class OsSpecificOps():
    """
    Class containing specific operations for OL-type images.

    This class just contains methods to be executed only on OL os type
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
        self.package_tool = get_package_mgr_tool()

    @is_an_os_specific_method
    def a10_remove_cloud_init(self):
        """
        Remove the cloud-init software and the configuration data.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        _logger.debug('__ Remove existing cloud_init config.')
        try:
            pkg_mgr = self._exec_yum \
                if self.package_tool['pkg_mgr'] == 'yum' else self._exec_dnf
            package_erase = self.package_tool['package_remove'] + ['cloud-init']
            remove_output = pkg_mgr(package_erase)
            _logger.debug('cloud-init removed: %s', remove_output)
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
            _logger.warning('Failed to remove cloud-init completely which might cause issues at instance '
                            'creation: %s', str(e))
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

        def get_ol_package_list():
            """
            Retrieve the list of packages to install from oci-migrate-config file.

            Returns
            -------
            list: list of package names to install.
            """
            _logger.debug('Collection list of packages.')
            try:
                pkg_list = get_config_data('ol_os_packages_to_install')
                if not bool(pkg_list):
                    _logger.debug('Package list is empty.')
                    return False
                _logger.debug('Package list: %s', pkg_list)
                return pkg_list
            except Exception as e:
                _logger.warning('Failed to find a list of packages: %s', str(e))
                return False

        _logger.debug('__ Installing extra packages.')
        #
        # collect packages to install
        packages = get_ol_package_list()
        if not bool(packages):
            _logger.debug('No extra packages to install.')
            return True
        #
        #
        try:
            #
            # set current nameserver config.
            if system_tools.set_nameserver():
                _logger.debug('Updating nameserver info succeeded.')
            else:
                _logger.error('  Failed to update nameserver info.')
            #
            # get package manipulation tool.
            pkg_mgr = self._exec_yum \
                if self.package_tool['pkg_mgr'] == 'yum' else self._exec_dnf
            #
            # install packages
            for pkg in packages:
                #
                # verify if the package is available, the correct channel enabled.
                rpmlist = pkg_mgr(self.package_tool['package_available'] + [pkg])
                pkg_present = False
                for lline in rpmlist.splitlines():
                    _logger.debug('%s', lline)
                    if pkg in lline:
                        _logger.debug('The rpm %s is available.', pkg)
                        pkg_present = True
                        break
                if not pkg_present:
                    _logger.error('  The rpm %s is missing.', pkg)
                    migrate_data.migrate_preparation = False
                    migrate_data.migrate_non_upload_reason += \
                        '\n  The rpm package %s is missing from ' \
                        'the yum repository.' % pkg
                    return False
                installoutput = pkg_mgr(self.package_tool['package_install'] + [pkg])
                _logger.debug('Successfully installed pkg %s:\n%s', pkg, installoutput)
                result_msg(msg='Installed %s.' % pkg, result=False)
                pause_msg(msg='Installed %s here, or not.' % pkg, pause_flag='_OCI_CHROOT')
            #
            # restore nameserver data
            if system_tools.restore_nameserver():
                _logger.debug('Restoring nameserver info succeeded.')
            else:
                _logger.error('  Failed to restore nameserver info.')

        except Exception as e:
            errmsg = 'Failed to install one or more packages of ' \
                     '%s:\n%s' % (packages, str(e))
            _logger.critical('   %s', errmsg)
            error_msg('%s' % errmsg)
            migrate_data.migrate_preparation = False
            migrate_data.migrate_non_upload_reason += '\n  %s' % errmsg
            return False
        return True

    @staticmethod
    @is_an_os_specific_method
    def a30_set_oci_region():
        """
        Add a job to cloud-init config file to complete the ociregion data
        at first boot.

        Returns
        -------
            bool: True on success, False otherwise.
        """

        def add_oci_region(regionscript):
            """
            Update the default user name in the cloud.cfg file.

            Parameters:
            ----------
                regionscript: str
                    full path of the bash script.

            Returns:
            -------
                bool: True on success, False otherwise.
            """
            _logger.debug('__ Add oci region.')
            try:
                cloudconfig = get_config_data('cloudconfig_file')
                _logger.debug('Updating cloud.cfg file %s, adding oci region detection.', cloudconfig)
            except Exception as e:
                _logger.error('Failed to find cloud config file location: %s.', str(e))
                return False

            if os.path.isfile(cloudconfig):
                with open(cloudconfig, 'r') as f:
                    cloudcfg = yaml.load(f, Loader=yaml.SafeLoader)
                region_definition = False
                if isinstance(cloudcfg, dict):
                    if 'runcmd' in list(cloudcfg.keys()):
                        #
                        # runcmd present in cloud config file
                        run_cmd = cloudcfg['runcmd']
                        for yaml_key in run_cmd:
                            if isinstance(yaml_key, list):
                                for yamlval in yaml_key:
                                    if regionscript in yamlval:
                                        _logger.debug('%s already in cloud_init', regionscript)
                                        region_definition = True
                                        break
                            else:
                                if regionscript in yaml_key:
                                    _logger.debug('%s already in cloud_init', regionscript)
                                    region_definition = True
                                    break
                        if not region_definition:
                            #
                            # the regionscript not yet defined in runcmd
                            run_cmd.append(regionscript)
                    else:
                        #
                        # runcmd not yet present in cloud config file
                        cloudcfg['runcmd'] = [regionscript]

                    with open(cloudconfig, 'w') as f:
                        yaml.dump(cloudcfg, f, width=50)
                        _logger.debug('Cloud configuration file %s successfully updated.', cloudconfig)
                    return True
                _logger.error('Invalid cloud config file.')
                return False
            _logger.error('Cloud config file %s does not exist.', cloudconfig)
            return False

        _logger.debug('__ Set OCI region.')
        #
        # get the script name
        try:
            oci_region_script = get_config_data('ol_os_oci_region_script')
            _logger.debug('Got oci-region script name: %s', oci_region_script)
        except Exception as e:
            _logger.warning('Failed to collect the oci_region_script path: %s', str(e))
            return False
        #
        # write the oci region script code
        with open(oci_region_script, 'w') as fi:
            fi.writelines(ln + '\n' for ln in get_config_data('ol_os_oci_region_bash'))
        os.chmod(oci_region_script, stat.S_IRWXU)
        #
        # update cloud-init with runcmd command
        if add_oci_region(oci_region_script):
            _logger.debug('oci region successfully added.')
            result_msg(msg='Updated OCI region.', result=False)
            return True
        _logger.debug('Failed to update oci region.')
        return False

    @staticmethod
    @is_an_os_specific_method
    def a40_update_initrd():
        """
        Recreate initramfs with all modules included.

        Returns
        -------
        bool: True on success, False otherwise
        """
        # todo: complete the rebuild of initramfs
        _logger.debug('__ Update initrd.')
        dracutpath = system_tools.exec_exists('dracut')
        if dracutpath is not None:
            _logger.debug('dracut found at %s', dracutpath)
        else:
            _logger.debug('dracut not found')
        return True

    @is_an_os_specific_method
    def b20_install_cloud_agent(self):
        """
        Install the oracle cloud agent.
        Returns
        -------
           bool: True on success, False otherwise. (always True as failing to
                 install the oracle cloud agent is not fatal.
        """
        _logger.debug('__ Install oracle cloud agent.')
        if bool(migrate_data.oracle_cloud_agent_location):
            _logger.debug('oracle cloud agent present: %s', migrate_data.oracle_cloud_agent_location)
        else:
            _logger.debug('No oracle cloud agent package present, skipping.')
            return True
        #
        # get package manipulation tool.
        pkg_mgr = self._exec_yum \
            if self.package_tool['pkg_mgr'] == 'yum' else self._exec_dnf
        #
        # install rpm
        oracle_cloud_agent_rpm = migrate_data.oracle_cloud_agent_location
        simple_rpm = oracle_cloud_agent_rpm.split('/')[-1]
        try:
            install_output = pkg_mgr(self.package_tool['package_localinstall'] + [oracle_cloud_agent_rpm])
            _logger.debug('Successfully installed pkg %s:\n%s', simple_rpm, install_output)
            migrate_tools.result_msg(msg='Installed %s.' % simple_rpm, result=False)
            pause_msg('cloud agent', pause_flag='_OCI_AGENT')
        except Exception as e:
            _logger.warning('Failed to install %s: %s', simple_rpm, str(e))
        return True

    @staticmethod
    def _exec_dnf(cmd):
        """
        Execute a dnf command.

        Parameters
        ----------
        cmd: list
            The dnf command parameters as s list.

        Returns
        -------
            str: dnf output on success, raises an exception otherwise.
        """
        cmd = ['dnf'] + cmd
        _logger.debug('Running dnf command: %s', cmd)
        try:
            _logger.debug('command: %s', cmd)
            output = system_tools.run_popen_cmd(cmd)['output'].decode('utf-8')
            _logger.debug('dnf command output: %s', str(output))
            return output
        except Exception as e:
            _logger.critical('   Failed to execute dnf: %s', str(e))
            raise OciMigrateException('\nFailed to execute dnf.') from e

    @staticmethod
    def _exec_yum(cmd):
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
        _logger.debug('Running yum command: %s', cmd)
        try:
            _logger.debug('command: %s', cmd)
            output = system_tools.run_popen_cmd(cmd)['output'].decode('utf-8')
            _logger.debug('yum command output: %s', str(output))
            return output
        except Exception as e:
            _logger.critical('   Failed to execute yum: %s', str(e))
            raise OciMigrateException('\nFailed to execute yum.') from e
