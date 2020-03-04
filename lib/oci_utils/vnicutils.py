# oci-utils
#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import logging
import os
import os.path
import subprocess

from . import cache
import oci_utils
from oci_utils import _configuration as OCIUtilsConfiguration
from .oci_api import HAVE_OCI_SDK, OCISession

# TODO: can we move this under 'impl' ?

_logger = logging.getLogger('oci-utils.vnicutils')
_secondary_vnic_all_configure_path = os.path.join(os.path.dirname(oci_utils.__file__), 'impl', '.vnic_script.sh')

class VNICUtils(object):
    """Class for managing VNICs
    """
    # file with saved vnic information
    __vnic_info_file = "/var/lib/oci-utils/vnic_info"
    # OBSOLETE: file with VNICs and stuff to exclude from automatic
    # configuration
    __net_exclude_file = "/var/lib/oci-utils/net_exclude"

    def __init__(self):
        """ Class VNICUtils initialisation.
        """
        self.vnic_info = None
        self.vnic_info_ts = 0

    @staticmethod
    def __new_vnic_info():
        """
        Create a new vnic info file

        Returns
        -------
        tuple
            (vnic info timestamp: datetime, vnic info: dict)
        """
        vnic_info = {
            'ns': None,
            'sshd': False,
            'exclude': [],
            'sec_priv_ip': []}
        vnic_info_ts = 0

        # migration from oci-utils 0.5's net_exclude file
        excludes = cache.load_cache(VNICUtils.__net_exclude_file)[1]
        if excludes is not None:
            vnic_info['exclude'] = excludes
            vnic_info_ts = \
                cache.write_cache(cache_content=vnic_info,
                                  cache_fname=VNICUtils.__vnic_info_file)
            try:
                os.remove(VNICUtils.__net_exclude_file)
            except Exception:
                pass

        # can we make API calls?
        oci_sess = None
        if HAVE_OCI_SDK:
            try:
                oci_sess = OCISession()
            except Exception:
                pass
        if oci_sess is not None:
            p_ips = oci_sess.this_instance().all_private_ips(refresh=True)
            sec_priv_ip = \
                [[ip.get_address(), ip.get_vnic().get_ocid()] for ip in p_ips]
            vnic_info['sec_priv_ip'] = sec_priv_ip
            vnic_info_ts = \
                cache.write_cache(cache_content=vnic_info,
                                  cache_fname=VNICUtils.__vnic_info_file)
        return vnic_info_ts, vnic_info

    @staticmethod
    def get_vnic_info_timestamp():
        """
        Get timestamp of vnic info repository The last modification time of
        the vnic info file

        Returns
        -------
        int
            The last modification time since epoch in seconds.
        """
        return cache.get_timestamp(VNICUtils.__vnic_info_file)

    def get_vnic_info(self):
        """
        Load the vnic_info file. If the file is missing , a new one is created.

        Returns
        -------
        tuple (int, dict)
            (vnic info timestamp: datetime, vnic info: dict)
        """
        self.vnic_info_ts, self.vnic_info = \
            cache.load_cache(VNICUtils.__vnic_info_file)
        if self.vnic_info is None:
            self.vnic_info_ts, self.vnic_info = VNICUtils.__new_vnic_info()

        return self.vnic_info_ts, self.vnic_info

    def save_vnic_info(self):
        """
        Save self.vnic_info in the vnic_info file.

        Returns
        -------
        int
            The timestamp of the file or None on failure.
        """
        _logger.debug("Saving vnic_info.")
        vnic_info_ts = cache.write_cache(cache_content=self.vnic_info,
                                         cache_fname=VNICUtils.__vnic_info_file)
        if vnic_info_ts is not None:
            self.vnic_info_ts = vnic_info_ts
        else:
            _logger.warn("Failed to save VNIC info to %s" %
                         VNICUtils.__vnic_info_file)
        return vnic_info_ts

    def _run_sec_vnic_script(self, script_args):
        """
        Run secondary_vnic_all_configure.sh.

        Parameters
        ----------
        script_args: list of string
            Arguments to be passed to the script.

        Returns
        -------
        tuple
            (The exit code of the script, the output of the script)
        """
        true_val = ['true', 'True', 'TRUE']
        vf_net = OCIUtilsConfiguration.get('vnic', 'vf_net') in true_val
        if vf_net and '-s' not in script_args:
            _logger.debug(
                'Skipping execution of the secondary vnic script')
            return 0, 'Info: vf_net is enabled in the oci-utils configuration'
        all_args = [_secondary_vnic_all_configure_path]
        all_args += script_args
        if "-c" in script_args:
            if 'sshd' in self.vnic_info:
                if self.vnic_info['sshd']:
                    all_args += ['-r']
            if 'ns' in self.vnic_info:
                if self.vnic_info['ns'] is not None:
                    all_args += ['-n', self.vnic_info['ns']]
        if "-c" in script_args or "-s" in script_args:
            if 'exclude' in self.vnic_info:
                for exc in self.vnic_info['exclude']:
                    all_args += ['-X', exc]
            if 'sec_priv_ip' in self.vnic_info:
                for ipaddr, vnic_id in self.vnic_info['sec_priv_ip']:
                    all_args += ['-e', ipaddr, vnic_id]

        _logger.debug('Executing "%s"' % " ".join(all_args))
        try:
            output = subprocess.check_output(
                all_args, stderr=subprocess.STDOUT)
        except OSError:
            _logger.debug('failed to execute '
                          '/usr/libexec/secondary_vnic_all_configure.sh')
            return 404, 'failed to execute secondary VNIC script'
        except subprocess.CalledProcessError as e:
            _logger.debug('Error running command "%s":' % ' '.
                          join(all_args))
            _logger.error(e.output)
            return e.returncode, e.output

        return 0, output

    def set_namespace(self, ns):
        """
        Set the 'ns' field of the vnic_info dict to the given value. This
        value is passed to the secondary vnic script with the -n option and
        is used to place the interface in the given namespace. The default
        is no namespace.

        Parameters
        ----------
        ns: str
            The namespace value.
        """
        self.vnic_info['ns'] = ns
        self.save_vnic_info()

    def set_sshd(self, val):
        """
        Set the 'sshd' field of the vnic_info dict to the given value.

        Parameters
        ----------
        val: bool
            When set to True, the secondary vnic script is called with
            the -r option, which, if a namespace is also specified,
            runs sshd in the namespace. The default is False.
        """
        self.vnic_info['sshd'] = val
        self.save_vnic_info()

    def add_private_ip(self, ipaddr, vnic_id):
        """
        Add the given secondary private IP to vnic_info save vnic info to
        the vnic_info file.

        Parameters
        ----------
        ipaddr: str
            The secondary IP address.
        vnic_id: int
            The VNIC id.
        """
        if [ipaddr, vnic_id] not in self.vnic_info['sec_priv_ip']:
            self.vnic_info['sec_priv_ip'].append([ipaddr, vnic_id])
        self.save_vnic_info()

    def set_private_ips(self, priv_ips):
        """
        Set the secondary private IP.

        Parameters
        ----------
        priv_ips: str
            The private IP addresses.
        """
        self.vnic_info['sec_priv_ip'] = priv_ips
        self.save_vnic_info()

    def delete_all_private_ips(self, vnic_id):
        """
        Delete all private IPs attached to a given VNIC.

        Parameters
        ----------
        vnic_id: int
            The vnic ID from which we delete private IP's.
        """
        remove_privip = []
        for privip in self.vnic_info['sec_priv_ip']:
            if privip[1] == vnic_id:
                remove_privip.append(privip)
                self.include(privip[0], save=False)
        for pi in remove_privip:
            self.vnic_info['sec_priv_ip'].remove(pi)
        self.save_vnic_info()

    def del_private_ip(self, ipaddr, vnic_id):
        """
        Delete secondary private IP from vnic_info save vnic_info to the
        vnic_info file.

        Parameters
        ----------
        ipaddr: str
            The IP addr to be removed.
        vnic_id: int
            The VNIC ID.

        Returns
        -------
        tuple
            (exit code: int, output from the "sec vnic" script execution).
            # See _run_sec_vnic_script()
        """
        if vnic_id is None:
            for ip in self.vnic_info['sec_priv_ip']:
                if ip[0] == ipaddr:
                    vnic_id = ip[1]
                    break
        if vnic_id is None:
            return 0, 'IP %s is not configured.' % ipaddr

        ret, info = self._run_sec_vnic_script(['-d', '-e', ipaddr, vnic_id])
        if ret == 0:
            if [ipaddr, vnic_id] in self.vnic_info['sec_priv_ip']:
                self.vnic_info['sec_priv_ip'].remove([ipaddr, vnic_id])
            self.include(ipaddr, save=False)
            self.save_vnic_info()
        return ret, info

    def exclude(self, item, save=True):
        """
        Add item to the "exclude" list. IP addresses or interfaces that are
        excluded from automatic configuration.

        Parameters
        ----------
        item: str
            Item (IP or interface) to be excluded.
        save: bool
            If True save to persistent configuration (vnic_info file) (the
            default is True).
        """
        if item not in self.vnic_info['exclude']:
            _logger.debug('Adding %s to "exclude" list' % item)
            self.vnic_info['exclude'].append(item)
            if save:
                self.save_vnic_info()

    def include(self, item, save=True):
        """
        Remove item from the "exclude" list, IP addresses or interfaces that
        are excluded from automatic configuration.

        Parameters
        ----------
        item: str
            Item (IP or interface) to be excluded.
        save: bool
            If True save to persistent configuration (vnic_info file) (the
            default is True).
        """
        if item in self.vnic_info['exclude']:
            _logger.debug('Removing %s from "exclude" list' % item)
            self.vnic_info['exclude'].remove(item)
            if save:
                self.save_vnic_info()

    def auto_config(self, sec_ip, quiet, show):
        """
        Auto configure VNICs. Run the secondary vnic script in automatic
        configuration mode (-c).

        Parameters
        ----------
        sec_ip: str
            secondary IP
        quiet: bool
            Do we run the underlying script silently?
        show: bool
            Do network config should be part of the output?

        Returns
        -------
        tuple
            (exit code: int,  output from the "sec vnic" script execution.)
            # See _run_sec_vnic_script()
        """
        args = ['-c']
        if quiet:
            args += ['-q']
        if show:
            args += ['-s']
        if sec_ip:
            for si in sec_ip:
                args += ['-e', si[0], si[1]]
                if [si[0], si[1]] not in self.vnic_info['sec_priv_ip']:
                    self.vnic_info['sec_priv_ip'].append((si[0], si[1]))
                self.include(si[0], save=False)
                self.save_vnic_info()

        return self._run_sec_vnic_script(args)

    def auto_deconfig(self, sec_ip, quiet, show):
        """
        De-configure VNICs. Run the secondary vnic script in automatic
        de-configuration mode (-d).

        Parameters
        ----------
        sec_ip: str
            The secondary IP.
        quiet: bool
            Do we run the underlying script silently?
        show: bool
            Do network config should be part of the output?

        Returns
        -------
        tuple
            (exit code: int, output from the "sec vnic" script execution.)
            # See _run_sec_vnic_script()
        """
        args = ['-d']
        if quiet:
            args += ['-q']
        if show:
            args += ['-s']
        if sec_ip:
            for si in sec_ip:
                args += ['-e', si[0], si[1]]
                if [si[0], si[1]] in self.vnic_info['sec_priv_ip']:
                    self.vnic_info['sec_priv_ip'].remove([si[0], si[1]])
                self.exclude(si[0], save=False)
                self.save_vnic_info()
        return self._run_sec_vnic_script(args)

    def get_network_config(self):
        """
        Get network configuration. Run the secondary vnic script in show
        configuration mode (-s).

        Returns
        -------
        tuple
            (exit code: int, output from the "sec vnic" script execution.)
            # See _run_sec_vnic_script()
        """
        return self._run_sec_vnic_script(['-s'])
