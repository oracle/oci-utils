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
from oci_utils import _configuration as OCIUtilsConfiguration
from .oci_api import OCISession
from .metadata import InstanceMetadata
from .impl import network_helpers as NetworkHelpers
from .impl import sudo_utils

_logger = logging.getLogger('oci-utils.vnicutils')

_INTF_MTU = 9000


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
            (exit code: int, output message).
        """

        _interfaces = self.get_network_config()
        _interface_to_delete = None
        for _interface in _interfaces:
            if _interface.get('VNIC') == vnic_id and _interface.get('ADDR') == ipaddr:
                _interface_to_delete = _interface
                break

        if not _interface_to_delete:
            return 0, 'IP %s is not configured.' % ipaddr

        # 1. delete any rule for this ip
        NetworkHelpers.remove_ip_addr_rules(_interface_to_delete['ADDR'])

        # 2. remove addr from the system
        if _interface_to_delete['NS']:
            NetworkHelpers.remove_ip_addr(_interface_to_delete['IFACE'],
                                          _interface_to_delete['ADDR'], _interface_to_delete['NS'])
        else:
            NetworkHelpers.remove_ip_addr(_interface_to_delete['IFACE'], _interface_to_delete['ADDR'])

        # 3. removes the mac address from the unmanaged-devices list in then NetworkManager.conf file.
        NetworkHelpers.add_mac_to_nm(_interface_to_delete['MAC'])

        # 4. update cache
        if [ipaddr, vnic_id] in self.vnic_info['sec_priv_ip']:
            self.vnic_info['sec_priv_ip'].remove([ipaddr, vnic_id])
        self.include(ipaddr, save=False)
        self.save_vnic_info()

        return 0, ''

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

        _all_intf = self.get_network_config()
        _all_to_be_configure = []
        _all_to_be_deconfigure = []

        # 1.1 compute list of interface which need configuration
        # 1.2 compute list of interface which need deconfiguration
        for _intf in _all_intf:
            # Is this intf excluded ?
            _excluded = False
            for excl in self.vnic_info['exclude']:
                if excl in (_intf['IFACE'], _intf['VNIC'], _intf['ADDR']):
                    _excluded = True
            if _excluded:
                break

            if _intf['CONFSTATE'] == 'ADD':
                _all_to_be_configure.append(_intf)
            if _intf['CONFSTATE'] == 'DELETE':
                _all_to_be_deconfigure.append(_intf)

        # 2 configure the one which need it

        ns_i = None
        if 'ns' in self.vnic_info:
            # if requested to use namespace, compute namespace name pattern
            ns_i = {}
            if self.vnic_info['ns']:
                ns_i['name'] = self.vnic_info['ns']
            else:
                ns_i['name'] = 'ons%s' % _intf['IFACE']

            ns_i['start_sshd'] = 'sshd' in self.vnic_info

        for _intf in _all_to_be_configure:
            try:
                _auto_config_intf(ns_i, _intf)

                # disable network manager for that device
                NetworkHelpers.remove_mac_from_nm(_intf['MAC'])

                # setup routes
                _auto_config_intf_routing(ns_i, _intf)

            except Exception as e:
                # best effort , just issue warning
                _logger.warning('Cannot configure %s: %s' % (_intf, str(e)))

        # 3 deconfigure the one which need it

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
        Get network configuration.
        fetch information from this instance metadata and aggregate
        it to system information. Information form metadata take precedence

        Returns
        -------
        list of dict
           keys are
            CONFSTATE  'unconfig' indicates missing IP config, 'missing' missing VNIC,
                            'excl' excluded (-X), '-' hist configuration match oci vcn configuration
            ADDR    IP address
            SPREFIX subnet CIDR prefix
            SBITS   subnet mask bits
            VIRTRT  virutal router IP address
            NS      namespace (if any)
            IND     interface index (if BM)
            IFACE   interface (underlying physical if VLAN is also set)
            VLTAG   VLAN tag (if BM)
            VLAN    IP virtual LAN (if any)
            STATE   state of interface
            MAC     MAC address
            VNIC    VNIC object identifier
        """
        interfaces = []

        _all_intfs = NetworkHelpers.get_network_namespace_infos()

        for _namespace, _nintfs in _all_intfs.items():
            for _i in _nintfs:
                if "NO-CARRIER" in _i['flags'] or "LOOPBACK" in _i['flags']:
                    continue
                if _i['type'] != 'ether':
                    continue
                _intf = {}
                _intf['MAC'] = _i.get('mac', '').upper()
                _intf['IFACE'] = _i['device'].decode()
                _intf['IND'] = _i['index'].decode()
                _intf['STATE'] = _i['opstate']
                _intf['NS'] = _namespace
                _intf['VLAN'] = _i.get('vlanid', '')
                _intf['CONFSTATE'] = 'ADD'
                if _i.get('address'):
                    _intf['CONFSTATE'] = '-'
                _found = False
                for md_vnic in InstanceMetadata()['vnics']:
                    if md_vnic['macAddr'].upper() == _intf['MAC']:
                        _intf['ADDR'] = md_vnic['privateIp']
                        _intf['SPREFIX'] = md_vnic['subnetCidrBlock'].split('/')[0]
                        _intf['SBITS'] = md_vnic['subnetCidrBlock'].split('/')[1]
                        _intf['VIRTRT'] = md_vnic['virtualRouterIp']
                        _intf['VLTAG'] = md_vnic['vlanTag']
                        _intf['VNIC'] = md_vnic['vnicId']
                        _found = True
                        break
                if not _found:
                    _intf['CONFSTATE'] = 'DELETE'

                interfaces.append(_intf)

        return interfaces


def _auto_config_intf_routing(net_namespace_info, intf_infos):
    """
    Configure interface routing
    parameter:
     net_namespace_info:
        information about namespace (or None if no namespace use)
        keys:
           name : namespace name
           start_sshd: if True start sshd within the namespace
     intf_info: interface info as dict
        keys: see VNICITils.get_network_config

    Raise:
        Exception. if configuration failed
    """
    if net_namespace_info:
        _logger.debug("default route add")
        ret, out = NetworkHelpers.add_static_ip_route(
            ['default', 'via', intf_infos['VIRTRT']], namespace=net_namespace_info['name'])
        if ret != 0:
            raise Exception("cannot add namespace %s default gateway %s: %s" %
                            (net_namespace_info['name'], intf_infos['VIRTRT'], out))
        _logger.debug("added namespace %s default gateway %s" % (net_namespace_info['name'], intf_infos['VIRTRT']))
        if net_namespace_info['start_sshd']:
            ret = sudo_utils.call(['/usr/sbin/ip', 'netns', 'exec', net_namespace_info['name'], '/usr/sbin/sshd'])
            if ret != 0:
                raise Exception("cannot start ssh daemon")
            _logger.debug('sshd daemon started')
    else:
        if InstanceMetadata()['instance']['shape'].startswith('BM'):
            _route_table_name = 'ort%svl%s' % (intf_infos['IFACE'], intf_infos['VLTAG'])
        else:
            _route_table_name = 'ort%s' % intf_infos['IFACE']

        NetworkHelpers.add_route_table(_route_table_name)
        _logger.debug("default route add")
        ret, out = NetworkHelpers.add_static_ip_route(
            ['default', 'via', intf_infos['VIRTRT'], 'table', _route_table_name])
        if ret != 0:
            raise Exception("cannot add default route via %s on %s to table %s" %
                            (intf_infos['VIRTRT'], intf_infos['IFACE'], _route_table_name))
        _logger.debug("added default route via %s dev %s table %s" %
                      (intf_infos['VIRTRT'], intf_infos['IFACE'], _route_table_name))

        # create source-based rule to use table
        ret, out = NetworkHelpers.add_static_ip_rule(('from', intf_infos['ADDR'], 'lookup', _route_table_name))
        if ret != 0:
            raise Exception("cannot add rule from %s use table %s" % (intf_infos['ADDR'], _route_table_name))
        _logger.debug("added rule for routing from %s lookup %s with default via %s" %
                      (intf_infos['ADDR'], _route_table_name, intf_infos['VIRTRT']))


def _auto_config_intf(net_namespace_info, intf_infos):
    """
    Configures interface

    parameter:
     net_namespace_info:
        information about namespace (or None if no namespace use)
        keys:
           name : namespace name
           start_sshd: if True start sshd within the namespace
     intf_info: interface info as dict
        keys: see VNICITils.get_network_config

    Raise:
        Exception. if configuration failed
    """
    # if interface is not up bring it up
    if intf_infos['STATE'] != 'up':
        _logger.debug('bringing intf [%s] up ' % intf_infos['IFACE'])
        ret = sudo_utils.call(['/usr/sbin/ip', 'link', 'set', 'dev', intf_infos['IFACE'], 'up'])
        if ret != 0:
            raise Exception('Cannot bring inerface up')

    # create network namespace if needed
    if net_namespace_info is not None:
        _logger.debug('creating namespace [%s]' % net_namespace_info['name'])
        ret = sudo_utils.call(['/usr/sbin/ip', 'netns', 'add', net_namespace_info['name']])
        if ret != 0:
            raise Exception('Cannot create network namespace')

    # for BM case , create virtual interface if needed
    _is_bm_shape = InstanceMetadata()['instance']['shape'].startswith('BM')
    _macvlan_name = None
    _vlan_name = '%sv%s' % (intf_infos['IFACE'], intf_infos['VLTAG'])
    if _is_bm_shape and intf_infos['VLTAG'] != "0":
        _ip_cmd = ['/usr/sbin/ip']
        if intf_infos['NS']:
            _ip_cmd.extend(['netns,', 'exec', intf_infos['NS'], '/usr/sbin/ip'])

        _macvlan_name = "%s.%s" % (intf_infos['IFACE'], intf_infos['VLTAG'])
        _ip_cmd.extend(['link', 'add', 'link', intf_infos['IFACE'], 'name', _macvlan_name, 'address',
                        intf_infos['MAC'], 'type', 'macvlan'])
        _logger.debug('creating macvlan [%s]' % _macvlan_name)
        ret = sudo_utils.call(_ip_cmd)
        if ret != 0:
            raise Exception("cannot create MAC VLAN interface %s for MAC address %s" %
                            (_macvlan_name, intf_infos['MAC']))

        if intf_infos['NS']:
            # if physical iface/nic is in a namespace pull out the created mac vlan
            sudo_utils.call(['/usr/sbin/ip', 'netns,', 'exec', intf_infos['NS'],
                             '/usr/sbin/ip', 'link', 'set', _macvlan_name, 'netns', '1'])

        # create an ip vlan on top of the mac vlan
        ret = sudo_utils.call(['/usr/sbin/ip', 'link', 'add', 'link', _macvlan_name,
                               'name', _vlan_name, 'type', 'vlan', 'id', intf_infos['VLTAG']])
        if ret != 0:
            raise Exception("cannot create VLAN %s on MAC VLAN %s" % (_vlan_name, _macvlan_name))

    # move the iface(s) to the target namespace if requested
    if net_namespace_info is not None:
        if _is_bm_shape and _macvlan_name:
            _logger.debug("macvlan link move %s" % net_namespace_info['name'])
            ret = sudo_utils.call(['/usr/sbin/ip', 'link', 'set', 'dev',
                                   _macvlan_name, 'netns', net_namespace_info['name']])
            if ret != 0:
                raise Exception("cannot move MAC VLAN $macvlan into namespace %s" % net_namespace_info['name'])

        _logger.debug("%s link move %s" % (intf_infos['IFACE'], net_namespace_info['name']))
        ret = sudo_utils.call(['/usr/sbin/ip', 'link', 'set', 'dev',
                               intf_infos['IFACE'], 'netns', net_namespace_info['name']])
        if ret != 0:
            raise Exception("cannot move interface %s into namespace %s" %
                            (intf_infos['IFACE'], net_namespace_info['name']))

    # add IP address to interface
    if net_namespace_info:
        _logger.debug("addr %s/%s add on %s ns '%s'" %
                      (intf_infos['ADDR'], intf_infos['SBITS'], intf_infos['IFACE'], net_namespace_info['name']))
    else:
        _logger.debug("addr %s/%s add on %s" %
                      (intf_infos['ADDR'], intf_infos['SBITS'], intf_infos['IFACE']))
    _ip_cmd_prefix = ['/usr/sbin/ip']
    if net_namespace_info is not None:
        _ip_cmd_prefix.extend(['netns,', 'exec', net_namespace_info['name'], '/usr/sbin/ip'])

    _ip_cmd = list(_ip_cmd_prefix)
    _ip_cmd.extend(['addr', 'add', '%s/%s' % (intf_infos['ADDR'], intf_infos['SBITS']), 'dev', intf_infos['IFACE']])
    ret = sudo_utils.call(_ip_cmd)
    if ret != 0:
        raise Exception('cannot add IP address %s/%s on interface %s' %
                        (intf_infos['ADDR'], intf_infos['SBITS'], intf_infos['IFACE']))

    if _is_bm_shape and _macvlan_name:
        _logger.debug("vlans set up")
        _ip_cmd = list(_ip_cmd_prefix)
        _ip_cmd.extend(['link', 'set', 'dev', _macvlan_name, 'mtu', str(_INTF_MTU), 'up'])
        ret = sudo_utils.call(_ip_cmd)
        if ret != 0:
            raise Exception("cannot set MAC VLAN %s up" % _macvlan_name)

        _ip_cmd = list(_ip_cmd_prefix)
        _ip_cmd.extend(['link', 'set', 'dev', _vlan_name, 'mtu', str(_INTF_MTU), 'up'])
        ret = sudo_utils.call(_ip_cmd)
        if ret != 0:
            raise Exception("cannot set VLAN %s up" % _vlan_name)
    else:
        _logger.debug("%s set up" % intf_infos['IFACE'])
        _ip_cmd = list(_ip_cmd_prefix)
        _ip_cmd.extend(['link', 'set', 'dev', intf_infos['IFACE'], 'mtu', str(_INTF_MTU), 'up'])
        ret = sudo_utils.call(_ip_cmd)
        if ret != 0:
            raise Exception("cannot set interface $iface MTU" % intf_infos['IFACE'])

    _logger.debug("added IP address %s on interface %s with MTU %d" %
                  (intf_infos['ADDR'], intf_infos['IFACE'], str(_INTF_MTU)))
