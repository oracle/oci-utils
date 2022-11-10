# oci-utils
#
# Copyright (c) 2018, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import logging
import os
import os.path
from pprint import pformat

from oci_utils import where_am_i

from . import cache
from .impl import IP_CMD
from .impl import network_helpers as NetworkHelpers
from .impl import sudo_utils
from .impl.network_interface import NetworkInterfaceSetupHelper, _intf_dict
from .metadata import InstanceMetadata
from .oci_api import OCISession

_logger = logging.getLogger('oci-utils.vnicutils')


class VNICUtils:
    """Class for managing VNICs
    """
    # file with saved vnic information
    VNICINFO_CACHE = cache.get_cache_file_path('vnic-info')
    # kept here for compatiblity with pre-0.12.6 releases.
    __vnic_info_file = "/var/lib/oci-utils/vnic_info"
    # OBSOLETE: file with VNICs and stuff to exclude from automatic
    # configuration. only kept for migration
    VNICEXCLUDE_CACHE = cache.get_cache_file_path('vnic-exclude')
    # kept here for compatiblity with pre-0.12.6 releases.
    __net_exclude_file = "/var/lib/oci-utils/net_exclude"

    def __init__(self, ocisession=None):
        """ Class VNICUtils initialisation.
        """
        self.vnic_info = self.get_vnic_info()
        self._metadata = None
        try:
            self._metadata = InstanceMetadata().refresh()
        except IOError as e:
            _logger.warning('Cannot get metadata: %s', str(e))
        if ocisession is None:
            try:
                self.oci_sess = OCISession()
            except Exception as e:
                _logger.error('Cannot create a session.')
                _logger.debug('Cannot create a session: %s', str(e), stack_info=True)
     
        else:
            self.oci_sess = ocisession
            

    @staticmethod
    def __new_vnic_info():
        """
        Create a new vnic info file

        Returns
        -------
        tuple
            (vnic info timestamp: datetime, vnic info: dict)
        """
        _logger.debug('%s', where_am_i())
        _vnic_info = {'exclude': [], 'deconfig': [], 'sec_priv_ip': []}

        # migration from oci-utils 0.5's net_exclude file
        excludes = cache.load_cache_11876(global_file=VNICUtils.VNICINFO_CACHE,
                                          global_file_11876=VNICUtils.__net_exclude_file)[1]
        if excludes is not None:
            _vnic_info['exclude'] = excludes
            cache.write_cache_11876(cache_content=_vnic_info,
                                    cache_fname=VNICUtils.VNICEXCLUDE_CACHE,
                                    cache_fname_11876=VNICUtils.__vnic_info_file)
            try:
                os.remove(VNICUtils.__net_exclude_file)
                os.remove(VNICUtils.VNICEXCLUDE_CACHE)
            except Exception as e:
                _logger.debug('Cannot remove file [%s] or [%s]: %s', VNICUtils.__net_exclude_file,
                              VNICUtils.VNICEXCLUDE_CACHE,
                              str(e))

            _logger.debug('Excluded intf: %s ', excludes)
        #
        return _vnic_info

    def excluded_interfaces(self):
        """
        Gets excluded interface from auto configuration/deconfiguration
        """
        _logger.debug('%s', where_am_i())
        return self.vnic_info['exclude']

    def get_vnic_info(self):
        """
        Load the vnic_info file. If the file is missing , a new one is created.

        Returns
        -------
        tuple (int, dict)
            (vnic info timestamp: datetime, vnic info: dict)
        """
        _logger.debug('%s', where_am_i())
        self.vnic_info_ts, self.vnic_info = cache.load_cache_11876(global_file=VNICUtils.VNICINFO_CACHE,
                                                                   global_file_11876=VNICUtils.__vnic_info_file)
        if self.vnic_info is None:
            self.vnic_info = {'exclude': [],
                              'deconfig': [],
                              'sec_priv_ip': []}
        # for compatibility
        if 'deconfig' not in self.vnic_info:
            self.vnic_info['deconfig'] = []
        if 'sec_priv_ip' not in self.vnic_info:
            self.vnic_info['sec_priv_ip'] = []
        return self.vnic_info

    def save_vnic_info(self):
        """
        Save self.vnic_info in the vnic_info file.

        Returns
        -------
        int
            The timestamp of the file or None on failure.
        """
        _logger.debug('%s', where_am_i())
        # _ = cache.write_cache(cache_content=self.vnic_info, cache_fname=VNICUtils.__vnic_info_file)
        return cache.write_cache_11876(cache_content=self.vnic_info,
                                       cache_fname=VNICUtils.VNICINFO_CACHE,
                                       cache_fname_11876=VNICUtils.__vnic_info_file)

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
        _logger.debug('%s', where_am_i())
        self.vnic_info['ns'] = ns

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
        _logger.debug('%s', where_am_i())
        self.vnic_info['sshd'] = val

    def add_private_ip(self, ipaddr, vnic_id):
        """
        Add the given secondary private IP to vnic_info.
        Save vnic info to the vnic_info file.

        Parameters
        ----------
        ipaddr: str
            The secondary IP address.
        vnic_id: int
            The vNIC id.
        """
        _logger.debug('%s', where_am_i())
        _interfaces = self.get_network_config()
        _logger.debug('\n%s', pformat(_interfaces, indent=4))

        _intf = None
        #
        # find the interface
        for _interface in _interfaces:
            if _interface.get('VNIC') == vnic_id:
                _intf = _interface
                break
        _logger.debug('Interface\n%s', pformat(_intf, indent=4))

        if _intf is None:
            # should not happen
            raise ValueError('Cannot find vnic with id [%s]: caller did not check?' % vnic_id)

        if 'MISSING_SECONDARY_IPS' not in _intf:
            _intf['MISSING_SECONDARY_IPS'] = [ipaddr]
            _logger.debug('Added missing secondary ipaddr: %s', [ipaddr])
        else:
            if ipaddr not in _intf['MISSING_SECONDARY_IPS']:
                _intf['MISSING_SECONDARY_IPS'].append(ipaddr)
                _logger.debug('Added missing secondary ipaddr next: %s', pformat(_intf, indent=4))

        if [ipaddr, vnic_id] not in self.vnic_info['sec_priv_ip']:
            self.vnic_info['sec_priv_ip'].append([ipaddr, vnic_id])
            _logger.debug('Added sec priv ip to intf: %s', pformat(self.vnic_info, indent=4))
        _logger.debug('vnic_info %s', pformat(self.vnic_info, indent=4))

        self.save_vnic_info()
        _logger.debug('Interface\n%s', pformat(_intf, indent=4))
        self._config_secondary_intf(_intf)

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
        _logger.debug('%s', where_am_i())
        _interfaces = self.get_network_config()
        _interface_to_delete = None
        # find interface to the the ip from
        for _interface in _interfaces:
            if _interface.get('VNIC') == vnic_id \
                    and (_interface.get('ADDR') == ipaddr
                         or ipaddr in _interface.get('SECONDARY_ADDRS', ())):
                _interface_to_delete = _interface
                break
        _logger.debug('Interface: %s', pformat(_interface_to_delete, indent=4))
        if not _interface_to_delete:
            _logger.debug('IP [%s] to remove not found on vNIC %s', ipaddr, vnic_id)
            return 0, 'IP %s is not configured.' % ipaddr

        # 1. delete any rule for this ip
        # NetworkHelpers.remove_ip_addr_rules(ipaddr)
        NetworkHelpers.remove_ip_rules(ipaddr)

        # 2. remove addr from the system
        NetworkInterfaceSetupHelper(_interface_to_delete).remove_secondary_address(ipaddr)

        # __GT__ should not be executed at remove secondary addr, moved to detach vnic
        # 3. removes the mac address from the unmanaged-devices list in then NetworkManager.conf file.
        # NetworkHelpers.add_mac_to_nm(_interface_to_delete['MAC'])

        # 4. update cache
        if [ipaddr, vnic_id] in self.vnic_info['sec_priv_ip']:
            self.vnic_info['sec_priv_ip'].remove([ipaddr, vnic_id])
        self.include(ipaddr)
        self.save_vnic_info()

        return 0, ''

    def _is_intf_excluded(self, interface):
        """
        Checks if this interface is excluded.
        Checks if interface name, VNIC ocid or ip addr is part of excluded items

        Parameters
        ----------
        interface: dict
            interface data

        Returns
        -------
            bool: True if deconfigured, False otherwise.
        """
        _logger.debug('%s\n%s', where_am_i(), pformat(interface, indent=4))
        for excl in self.vnic_info.get('exclude', ()):
            if excl in (interface['IFACE'], interface['VNIC'], interface['ADDR']):
                return True
        return False

    def _is_intf_deconfigured(self, interface):
        """
        Checks if the interface is deconfigured explicitly
        Checks if interface name, VNIC ocid or ip addr is part of deconfigured items

        Parameters
        ----------
        interface: dict
            interface data

        Returns
        -------
            bool: True if deconfigured, False otherwise.
        """
        _logger.debug('%s\n%s', where_am_i(), pformat(interface, indent=4))
        for deconf in self.vnic_info.get('deconfig', ()):
            if deconf in (interface['IFACE'], interface['VNIC'], interface['ADDR']):
                return True
        return False

    def exclude(self, item):
        """
        Remove item from the "exclude" list. IP addresses or interfaces that are
        excluded from automatic configuration.

        Parameters
        ----------
        item: str
            Item (IP or interface) to be excluded.
        """
        _logger.debug('%s %s', where_am_i(), item)
        if item not in self.vnic_info['exclude']:
            _logger.debug('Adding %s to "exclude" list', item)
            self.vnic_info['exclude'].append(item)
            _ = self.save_vnic_info()

    def include(self, item):
        """
        Add item to the "exclude" list, IP addresses or interfaces that
        are excluded from automatic configuration.

        Parameters
        ----------
        item: str
            Item (IP or interface) to be excluded.
        """
        _logger.debug('__include %s', item)
        _logger.debug('%s %s', where_am_i(), item)
        if item in self.vnic_info['exclude']:
            _logger.debug('Removing %s from "exclude" list', item)
            self.vnic_info['exclude'].remove(item)
            _ = self.save_vnic_info()

    def auto_config(self, sec_ip, deconfigured=True):
        """
        Auto configure VNICs.

        Parameters
        ----------
        sec_ip: list of tuple (<ip adress>,<vnic ocid>)
            secondary IPs to add to vnics. can be None or empty
        deconfigured: bool
            if True, does configure manually unconfigured interfaces.

        Returns
        -------

        """
        _logger.debug('%s: %s %s', where_am_i(), sec_ip, deconfigured)
        _all_intf = self.get_network_config()
        # we may need a mapping of intf by physical NIC index
        # for BMs secondary VNIC are not plumbed
        # {<index>: <intf name>}
        _by_nic_index = {}
        #
        # the interfaces to be configured according to metadata
        _all_to_be_configured = []
        #
        # the interfaces on which a secondary interface must be added
        _all_to_be_modified = []
        #
        # the interfaces to be unconfigured according to metadata
        _all_to_be_deconfigured = []
        #
        # 1.1 compose list of interface which need configuration
        # 1.2 compose list of interface which need deconfiguration
        for _intf in _all_intf:

            if _intf['IFACE'] != '-':
                # keep track of interface by NIC index
                _by_nic_index[_intf['NIC_I']] = _intf['IFACE']
            _logger.debug('By nic index %s', pformat(_by_nic_index, indent=4))

            # Is this intf excluded ?
            if self._is_intf_excluded(_intf):
                continue

            # add secondary IPs if any
            if sec_ip:
                for (ip, vnic) in sec_ip:
                    if vnic == _intf['VNIC']:
                        if 'MISSING_SECONDARY_IPS' not in _intf:
                            _intf['MISSING_SECONDARY_IPS'] = [ip]
                        else:
                            if ip not in _intf['MISSING_SECONDARY_IPS']:
                                _intf['MISSING_SECONDARY_IPS'].append(ip)

            #
            _logger.debug('Auto config interface %s %s', _intf['ADDR'], _intf['CONFSTATE'])
            if _intf['CONFSTATE'] == 'ADD':
                if deconfigured:
                    _logger.debug('Auto config configure called via oci-network-config')
                if deconfigured or not self._is_intf_deconfigured(_intf):
                    _all_to_be_configured.append(_intf)
                    # take care of secondary addresses.
                    # at this point we cannot rely on MISSING_SECONDARY_IPS as we are configured "new" interface
                    # in order to use the same code path, set MISSING_SECONDARY_IPS here so _all_to_be_modified set
                    # will also contain this one. Need better refactoring: enough for now.
                    if len(_intf.get('SECONDARY_ADDRS', ())) > 0:
                        _intf['MISSING_SECONDARY_IPS'] = _intf['SECONDARY_ADDRS']
            if _intf['CONFSTATE'] == 'DELETE':
                _all_to_be_deconfigured.append(_intf)
            #
            # if called by the ocid service, the interfaces which were unconfigured by the oci-network-config
            # unconfigure command should not be touched; only an oci-network-config configure command will change this;
            # the ocid service calls auto_config with deconfigured=False.
            if deconfigured or not self._is_intf_deconfigured(_intf):
                if 'MISSING_SECONDARY_IPS' in _intf:
                    _all_to_be_modified.append(_intf)

        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug("Interfaces to be configured: %d", len(_all_to_be_configured))
            _logger.debug("Interfaces to be configured:\n %s", pformat(_all_to_be_configured, indent=4))
            _logger.debug("Interfaces to be unconfigured: %d", len(_all_to_be_deconfigured))
            _logger.debug("Interfaces to be unconfigured:\n %s", pformat(_all_to_be_deconfigured, indent=4))
            _logger.debug("Interfaces to be modified: %d", len(_all_to_be_modified))
            _logger.debug("Interfaces to be modified:\n %s", pformat(_all_to_be_modified, indent=4))

        # 2 configure the ones which need it
        for _intf in _all_to_be_configured:
            ns_i = None
            if 'ns' in self.vnic_info:
                # if requested to use namespace, compute namespace name pattern
                ns_i = {}
                if self.vnic_info['ns']:
                    ns_i['name'] = self.vnic_info['ns']
                else:
                    ns_i['name'] = 'ons%s' % _intf['IFACE']

                ns_i['start_sshd'] = 'sshd' in self.vnic_info
            try:
                # for BMs, IFACE can be empty ('-'), we local physical NIC
                # thank to NIC index
                # make a copy of it to change the IFACE
                _intf_to_use = _intf_dict(_intf)

                if self._metadata is None:
                    raise ValueError('No metadata information')

                if self._metadata['instance']['shape'].startswith('BM') and _intf['IFACE'] == '-':
                    _intf_to_use['IFACE'] = _by_nic_index[_intf['NIC_I']]
                    _intf_to_use['STATE'] = "up"

                if _logger.isEnabledFor(logging.DEBUG):
                    _logger.debug("Begin configuration of %s", pformat(_intf_to_use, indent=4))

                _auto_config_intf(ns_i, _intf_to_use)

                # disable network manager for that device
                NetworkHelpers.remove_mac_from_nm(_intf['MAC'])

                # setup routes
                self._auto_config_intf_routing(ns_i, _intf_to_use)
                #
                self.config(_intf['ADDR'])

            except Exception as e:
                # best effort , just issue warning
                _logger.debug('Cannot configure %s: %s', _intf_to_use, str(e))
                _logger.warning('Configuration failed: %s', str(e))

        # 3 deconfigure the one which need it
        for _intf in _all_to_be_deconfigured:
            try:
                self._auto_deconfig_intf_routing(_intf)
                _auto_deconfig_intf(_intf)
            except Exception as e:
                # best effort , just issue warning
                _logger.debug('Cannot deconfigure %s: %s', _intf, str(e))
                _logger.warning('Deconfiguration failed: %s', str(e))

        # 4 add secondaries IP address
        for _intf in _all_to_be_modified:
            if self._metadata['instance']['shape'].startswith('BM') and _intf['IFACE'] == '-':
                # it may happen if we came after configuring the interface by injecting MISSING_SECONDARY_IPS
                _intf['IFACE'] = _by_nic_index[_intf['NIC_I']]
                _intf['STATE'] = "up"
            self._config_secondary_intf(_intf)

    @staticmethod
    def _deconfig_secondary_addr(intf_infos, address):
        """
        Removes an IP address from a device

        Parameters:
        -----------
            device: network device as str
            address: IP address to be removed
            namespace: the network namespace (optional)
        Returns:
        --------
          None
        Raise:
        ------
            Exception in case of failure
        """
        _logger.debug('%s: %s %s', where_am_i(), address, pformat(intf_infos, indent=4))
        _logger.debug('Removing IP addr rules for %s', address)
        NetworkHelpers.remove_ip_rules(address)
        _logger.debug('Removing IP addr %s', address)
        NetworkInterfaceSetupHelper(intf_infos).remove_secondary_address(address)

    def auto_deconfig(self, sec_ip):
        """
        De-configure VNICs. Run the secondary vnic script in automatic
        de-configuration mode (-d).

        Parameters
        ----------
        sec_ip: list of tuple (<ip adress>,<vnic ocid>)
            secondary IPs to add to vnics. can be None or empty
        Returns
        -------
        tuple
            (exit code: int, output from the "sec vnic" script execution.)
        """
        _logger.debug('%s: %s', where_am_i(), sec_ip)
        _all_intf = self.get_network_config()
        _logger.debug('Deconfigure all interfaces %s', pformat(_all_intf, indent=4))

        # if we have secondary addrs specified, just take care of these
        #  vnic OCID give us the mac address then select the right interface which has the ip
        if sec_ip:
            _translated = []
            if self._metadata is None:
                return 1, 'No metadata available'
            _all_vnic_md = self._metadata['vnics']
            # 1. locate the MAC: translate ip/vnic to ip/mac
            for (ip, vnic) in sec_ip:
                _found = False
                for md_vnic in _all_vnic_md:
                    if md_vnic['vnicId'] == vnic:
                        _found = True
                        _logger.debug('Located vnic, mac is %s', md_vnic['macAddr'])
                        _translated.append((ip, md_vnic['macAddr']))
                        break
                if not _found:
                    _logger.warning('VNIC not found : %s ', vnic)

            for (ip, mac) in _translated:
                # fetch the right interface
                _found = False
                for intf in _all_intf:
                    if intf['MAC'] == mac:
                        if 'SECONDARY_ADDRS' in intf and ip in intf['SECONDARY_ADDRS']:
                            _found = True
                            self._deconfig_secondary_addr(intf, ip)
                            break
                if not _found:
                    _logger.warning('IP %s not found', ip)

        else:
            # unconfigure all
            for intf in _all_intf:
                # has this intf a valid ip address
                # (BM might have address stored as '-')
                if NetworkHelpers.is_valid_ip_address(intf.get('ADDR')):
                    # Is this intf the primary?
                    if intf.has('IS_PRIMARY'):
                        continue
                    # Is this intf has a configuration to be removed?
                    if intf['CONFSTATE'] == 'ADD':
                        continue
                    # Is this intf excluded ?
                    if self._is_intf_excluded(intf):
                        continue
                    for secondary_addr in intf.get('SECONDARY_ADDRS', ()):
                        self._deconfig_secondary_addr(intf, secondary_addr)
                    self._auto_deconfig_intf_routing(intf)
                    _auto_deconfig_intf(intf)
                    #
                    self.unconfig(intf['ADDR'])
                else:
                    _logger.debug('%s is not a valid ip address', intf.get('ADDR'))

        return 0, ''

    def unconfig(self, item):
        """
        Add item to the deconfig list.

        Parameters
        ----------
        item: str
            Item (IP or interface) to be unconfigured.
        """
        _logger.debug('%s: %s', where_am_i(), item)
        if item not in self.vnic_info['deconfig']:
            _logger.debug('Adding %s to "deconfig" list', item)
            self.vnic_info['deconfig'].append(item)
            _ = self.save_vnic_info()

    def config(self, item):
        """
        Remove item to the "deconfig" list.

        Parameters
        ----------
        item: str
            Item (IP or interface) to be (re)configured.
        """
        _logger.debug('%s: %s', where_am_i(), item)
        if item in self.vnic_info['deconfig']:
            _logger.debug('Removing %s from "deconfig" list', item)
            self.vnic_info['deconfig'].remove(item)
            _ = self.save_vnic_info()

    def _get_priv_addrs(self):
        """
        Gets all vnic private addrs

        Returns:
        --------
          dict : a vnic ocid indexed dict of list of IPs
        """
        _logger.debug('%s', where_am_i())
        res = {}
        # oci_sess = None
        my_instance = None
        try:
            my_instance = self.oci_sess.this_instance()
        except Exception as e:
            _logger.debug('Failed to get instance data: %s', str(e), stack_info=True)

        if bool(my_instance):
            p_ips = my_instance.all_private_ips()
            for p_ip in p_ips:
                _ocid = p_ip.get_vnic_ocid()
                _addr = p_ip.get_address()
                if _ocid not in res:
                    res[_ocid] = []
                res[_ocid].append(_addr)
        return res

    @staticmethod
    def get_all_from_system(all_intfs, link_by_index):
        """
        Build interface list from data collected from the system.

        Parameters
        ----------
        all_intfs: dict
            interface data collected from system with ip command.
        link_by_index: dict
            link by index map

        Returns
        -------
            list: of _intf_dict
        """
        _logger.debug('%s', where_am_i())
        all_interfaces = []
        for _namespace, _nintfs in all_intfs.items():
            for _i in _nintfs:
                _logger.debug('_i\n%s', pformat(_i, indent=4))
                if "NO-CARRIER" in _i['flags'] or "LOOPBACK" in _i['flags']:
                    continue
                if _i['type'] != 'ether':
                    continue

                _intf = _intf_dict()
                if _i.get('mac'):
                    _intf['MAC'] = _i.get('mac')
                _intf['IFACE'] = _i['device']
                if 'link' in _i and _i['link'] is not None:
                    _intf['LINK'] = _i['link']
                else:
                    # in that case, try with index if we have it
                    if _i['link_idx']:
                        _intf['LINK'] = link_by_index[_i['link_idx']]
                if 'subtype' in _i:
                    _intf['LINKTYPE'] = _i['subtype']
                else:
                    _intf['LINKTYPE'] = 'ether'
                _intf['IND'] = _i['index']
                _intf['STATE'] = _i['opstate']
                # default namespace is empty string
                if _namespace and _namespace != '':
                    _intf['NS'] = _namespace
                if _i.get('vlanid'):
                    _intf['VLAN'] = _i.get('vlanid')

                _i_addresses = _i.get('addresses', [])
                _logger.debug('_i get addresses\n%s', pformat(_i_addresses, indent=4))
                # prevent link local ipv6 addresses to be consideted as address in this context
                if len(_i_addresses) > 0:
                    _logger.debug('_i_addresses0:\n%s', pformat(_i_addresses[0], indent=4))
                    if not NetworkHelpers.is_link_local_address(_i_addresses[0]['address']):
                        _intf['CONFSTATE'] = '-'
                        _intf['ADDR'] = _i_addresses[0]['address']
                    if len(_i.get('addresses', [])) > 1:
                        # first one in the list is the primary address of that vnic
                        # _intf['SECONDARY_ADDRS'] = [ip['address'] for ip in _i.get('addresses')[1:]]
                        secondary_addrs = list()
                        for ip in _i_addresses[1:]:
                            if not NetworkHelpers.is_link_local_address(ip['address']):
                                secondary_addrs.append(ip['address'])
                        _intf['SECONDARY_ADDRS'] = secondary_addrs
                        _logger.debug('Secondary addrs: %s', secondary_addrs)
                else:
                    if not _i.get('is_vf'):
                        # by default, before correlation, set it to DELETE
                        _intf['CONFSTATE'] = 'DELETE'

                _logger.debug('From system _intf\n%s', pformat(_intf, indent=4))
                all_interfaces.append(_intf)
            _logger.debug('All from system _intf\n%s', pformat(all_interfaces, indent=4))
        return all_interfaces

    def get_all_from_metadata(self):
        """
        Build interface list from metadata.

        Returns
        -------
            list: of _intf_dict
        """
        _logger.debug('%s', where_am_i())
        all_interfaces = []
        _first_loop = True
        if self._metadata is None:
            _logger.warning('no metadata available')
        else:
            _ip_per_id = self._get_priv_addrs()

            for md_vnic in self._metadata['vnics']:
                _logger.debug('md_vnic\n%s', pformat(md_vnic, indent=4))
                _intf = _intf_dict()
                if _first_loop:
                    # primary always come first
                    _intf['IS_PRIMARY'] = True
                    _first_loop = False
                _intf['MAC'] = md_vnic['macAddr'].upper()
                _intf['ADDR'] = md_vnic['privateIp']
                _intf['SPREFIX4'] = md_vnic['subnetCidrBlock'].split('/')[0]
                _intf['SBITS4'] = md_vnic['subnetCidrBlock'].split('/')[1]
                _intf['VIRTRT4'] = md_vnic['virtualRouterIp']
                _intf['VLTAG'] = md_vnic['vlanTag']
                _intf['VNIC'] = md_vnic['vnicId']
                # if ipv6 is enabled.
                if 'ipv6SubnetCidrBlock' in md_vnic:
                    _intf['SPREFIX6'] = md_vnic['ipv6SubnetCidrBlock'].split('/')[0]
                if 'ipv6SubnetCidrBlock' in md_vnic:
                    _intf['SBITS6'] = md_vnic['ipv6SubnetCidrBlock'].split('/')[1]
                if 'ipv6VirtualRouterIp' in md_vnic:
                    _intf['VIRTRT6'] = md_vnic['ipv6VirtualRouterIp']
                if 'nicIndex' in md_vnic:
                    # VMs do not have such attr
                    _intf['NIC_I'] = md_vnic['nicIndex']
                if md_vnic['vnicId'] in _ip_per_id:
                    # get all but the primary one
                    _intf['SECONDARY_ADDRS'] = \
                        [_ip for _ip in _ip_per_id[md_vnic['vnicId']] if _ip != md_vnic['privateIp']]

                _logger.debug('from metadata _intf %s', pformat(_intf, indent=4))
                all_interfaces.append(_intf)
        return all_interfaces

    @staticmethod
    def get_link_by_indx(all_intfs):
        """
        Get the link by id map.

        Parameters
        ----------
        all_intfs: dict
            network namespace map.

        Returns
        -------
            dict: the link by id map.
        """
        _logger.debug('%s', where_am_i())
        link_by_idx = {}
        for _, _nintfs in all_intfs.items():
            for _i in _nintfs:
                link_by_idx[_i['index']] = _i['device']
        _logger.debug('Link by idx:\n%s', pformat(link_by_idx, indent=4))
        return link_by_idx

    @staticmethod
    def correlate_network_interface_data(from_metadata, from_system):
        """
        Correlate interface data collected from systen and from metadata.

        Parameters
        ----------
        from_metadata: list
            interface data coming from metadata.
        from_system
            interface data coming from system.

        Returns
        -------
            list: the interface data
        """
        _logger.debug('%s', where_am_i())
        interfaces = []
        _have_to_be_added = None
        _logger.debug('From metadata\n%s', pformat(from_metadata, indent=4))
        _logger.debug('From system\n%s', pformat(from_system, indent=4))
        for interface in from_metadata:
            try:
                # locate the one with same ethernet address
                _logger.debug('metadata mac %s', interface['MAC'])
                _candidates = [_i for _i in from_system if _i['MAC'] == interface['MAC']]
                _logger.debug('Candidates\n%s', pformat(_candidates, indent=4))
                _state = 'ADD'
                _have_to_be_added = set()
                _logger.debug('NB candidates %d', len(_candidates))
                if len(_candidates) == 1:
                    # only one found , no ambiguity
                    # treat secondary addrs: if have some in metadata not present on system , we have to plumb them
                    _logger.debug('Secondary addrs interface: %s', interface.get('SECONDARY_ADDRS', []))
                    _logger.debug('Secondary addrs candidate: %s', _candidates[0].get('SECONDARY_ADDRS', []))
                    _have_to_be_added = \
                        set(interface.get('SECONDARY_ADDRS', [])).difference(_candidates[0].get('SECONDARY_ADDRS', []))
                    interface.update(_candidates[0])
                    if _candidates[0].has('ADDR'):
                        if not NetworkHelpers.is_link_local_address(_candidates[0].get('ADDR')):
                            # an none_link_local addr on the correlated system intf -> state is '-'
                            _state = '-'
                            _logger.debug('%s is not link local', _candidates[0].get('ADDR'))
                        else:
                            _logger.debug('%s is link local', _candidates[0].get('ADDR'))

                    _logger.debug('A have to be added\n%s\nInterface\n%s\nCandidates\n%s ',
                                  pformat(_have_to_be_added, indent=4),
                                  pformat(interface, indent=4),
                                  pformat(_candidates, indent=4))
                elif len(_candidates) >= 2:
                    # we do not expect to have more than 2 anyway
                    # surely macvlan/vlans involved (BM case)
                    #  the macvlan interface give us the addr and the actual link
                    #  the vlan interface give us the vlan name
                    _macvlan_is = [_i for _i in _candidates if _i['LINKTYPE'] in ('macvlan', 'macvtap')]
                    _vlan_is = [_i for _i in _candidates if _i['LINKTYPE'] == 'vlan']
                    if len(_macvlan_is) > 0 and len(_vlan_is) > 0:
                        #
                        # treat secondary addrs: if have some in metadata not present on system , we have to plumb them
                        _logger.debug('Secondary addrs interface: %s', interface.get('SECONDARY_ADDRS', []))
                        _logger.debug('Secondary addrs candidate: %s', _vlan_is[0].get('SECONDARY_ADDRS', []))
                        _have_to_be_added = \
                            set(interface.get('SECONDARY_ADDRS', [])).difference(_vlan_is[0].get('SECONDARY_ADDRS', []))
                        interface.update(_macvlan_is[0])
                        interface['VLAN'] = _vlan_is[0]['IFACE']
                        interface['IFACE'] = _macvlan_is[0]['LINK']
                        if _vlan_is[0].has('ADDR'):
                            if not NetworkHelpers.is_link_local_address(_vlan_is[0].get('ADDR')):
                                _state = '-'
                                _logger.debug('%s is not link local', _vlan_is[0].get('ADDR'))
                            else:
                                _logger.debug('%s is link local', _vlan_is[0].get('ADDR'))
                        if _vlan_is[0].has('SECONDARY_ADDRS'):
                            interface['SECONDARY_ADDRS'] = _vlan_is[0]['SECONDARY_ADDRS']
                    _logger.debug('B have to be added\n%s\nInterface\n%s\nCandidates\n%s ',
                                  pformat(_have_to_be_added, indent=4),
                                  pformat(interface, indent=4),
                                  pformat(_candidates, indent=4))
                interface['CONFSTATE'] = _state
                #
                # clean up system list
                from_system = [_i for _i in from_system if _i['MAC'] != interface['MAC']]
                _logger.debug('New all from system:\n%s', pformat(from_system, indent=4))
            except ValueError as e:
                _logger.debug('Error while parsing [%s]: %s', str(interface), str(e))
            finally:
                if len(_have_to_be_added) > 0:
                    # this key will trigger configuration (see auto_config())
                    interface['MISSING_SECONDARY_IPS'] = list(_have_to_be_added)
                interfaces.append(interface)
        _logger.debug('C have to be added\n%s\nInterface\n%s\nCandidates\n%s ',
                      pformat(_have_to_be_added, indent=4),
                      pformat(interfaces, indent=4),
                      pformat(_candidates, indent=4))
        return interfaces, from_system

    def get_network_config(self):
        """
        Get network configuration.
        fetch information from this instance metadata and aggregate
        it to system information. Information form metadata take precedence

        Returns
        -------
        list of dict
           keys are
            CONFSTATE  'uncfg' indicates missing IP config, 'missing' missing VNIC,
                            'excl' excluded (-X), '-' hist configuration match oci vcn configuration
            ADDR       IP address
            SPREFIX4   subnet CIDR IPV4 prefix
            SBITS4     subnet mask IPV4 bits
            VIRTRT4    virtual router IPV4 address
            SPREFIX6   subnet CIDR IPV6 prefix
            SBITS6     subnet mask IPV6 bits
            VIRTRT6    virtual router IPV6 addressNS         namespace (if any)
            IND        interface index (if BM)
            IFACE      interface (underlying physical if VLAN is also set)
            VLTAG      VLAN tag (if BM)
            VLAN       IP virtual LAN (if any)
            STATE      state of interface
            MAC        MAC address
            NIC_I      (physical) NIC index
            VNIC       VNIC object identifier
            IS_PRIMARY is this interface the primary one ? (can be missing)
            SECONDARY_ADDRS secondary addresses
        """
        _logger.debug('%s', where_am_i())
        _all_intfs = NetworkHelpers.get_network_namespace_infos()
        _logger.debug('All interfaces\n%s', pformat(_all_intfs, indent=4))
        #
        # for BM cases (using macvlan/vlan) when using namespace , some interfaces (the macvlan ones within namespace)
        # do not have the 'link' property but the 'link_idx'
        # First build a "link by id" map
        # Note: loopback appears with index '1' in all namespaces.
        #
        # get link by id map
        _link_by_idx = self.get_link_by_indx(_all_intfs)
        _logger.debug('Link by id map:\n%s', pformat(_link_by_idx, indent=4))
        #
        # get data from system
        _all_from_system = self.get_all_from_system(_all_intfs, _link_by_idx)
        _logger.debug('All from system:\n%s', pformat(_all_from_system, indent=4))
        #
        # get data from metadata
        _all_from_metadata = self.get_all_from_metadata()
        _logger.debug('All from metadata:\n%s', pformat(_all_from_metadata, indent=4))
        #
        # correlate the information, precedence is given to metadata
        interfaces, _all_from_system = self.correlate_network_interface_data(_all_from_metadata, _all_from_system)
        _logger.debug('Correlated:\n%s', pformat(interfaces, indent=4))
        #
        # collect the ones left on system
        for interface in _all_from_system:
            interface['CONFSTATE'] = 'DELETE'
            interfaces.append(interface)
        _logger.debug('A interfaces:\n%s', pformat(interfaces, indent=4))
        #
        # final round for the excluded
        for interface in interfaces:
            if self._is_intf_excluded(interface):
                interface['CONFSTATE'] = 'EXCL'
                _logger.debug('Set exclude:\n%s', pformat(interface, indent=4))
            if interface['is_vf'] and interface['CONFSTATE'] == 'DELETE':
                # revert this as '-' , as DELETE state means nothing for VFs
                interface['CONFSTATE'] = '-'
                _logger.debug('Revert for vf:\n%s', pformat(interface, indent=4))

        _logger.debug('B interfaces:\n%s', pformat(interfaces, indent=4))
        return interfaces

    def _compute_routing_table_name(self, interface_info):
        """
        Compute the routing table name for a given interface return the name as str
        """
        _logger.debug('%s: %s', where_am_i(), interface_info)
        if self._metadata is None:
            raise ValueError('No metadata available')
        if self._metadata['instance']['shape'].startswith('BM'):
            return 'ort%svl%s' % (interface_info['NIC_I'], interface_info['VLTAG'])
        return 'ort%s' % interface_info['IND']

    def _auto_deconfig_intf_routing(self, intf_infos):
        """
        Deconfigure interface routing
        parameter:
        intf_info: interface info as dict
            keys: see VNICUTils.get_network_config

        Raise:
            Exception. if configuration failed
        """
        _logger.debug('%s: %s', where_am_i(), pformat(intf_infos, indent=4))
        # for namespaces the subnet and default routes will be auto deleted with the namespace
        if not intf_infos.has('NS'):
            _route_table_name = self._compute_routing_table_name(intf_infos)
            NetworkHelpers.remove_ip_rules(intf_infos['ADDR'])
            NetworkHelpers.delete_route_table(_route_table_name)

    def _auto_config_intf_routing(self, net_namespace_info, intf_infos):
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
        _logger.debug('%s: %s %s', where_am_i(), pformat(net_namespace_info, indent=4), pformat(intf_infos, indent=4))
        _intf_to_use = intf_infos['IFACE']
        if self._metadata['instance']['shape'].startswith('BM') and intf_infos['VLTAG'] != "0":
            # in that case we operate on the VLAN tagged intf no
            _intf_to_use = '%sv%s' % (intf_infos['IFACE'], intf_infos['VLTAG'])

        if net_namespace_info:
            _logger.debug("Default ipv4 route add")
            ret, out = NetworkHelpers.add_static_ip_route4(
                'default', 'via', intf_infos['VIRTRT4'], namespace=net_namespace_info['name'])
            if ret != 0:
                raise Exception("Cannot add namespace %s default gateway %s: %s" %
                                (net_namespace_info['name'], intf_infos['VIRTRT4'], out))
            _logger.debug("Added namespace %s default gateway %s", net_namespace_info['name'], intf_infos['VIRTRT4'])

            _logger.debug("Default ipv6 route add")
            if 'VIRTRT6' in intf_infos:
                ret, out = NetworkHelpers.add_static_ip_route6(
                    'default', 'via', intf_infos['VIRTRT6'], namespace=net_namespace_info['name'])
                if ret != 0:
                    raise Exception("Cannot add namespace %s default gateway %s: %s" %
                                    (net_namespace_info['name'], intf_infos['VIRTRT6'], out))
                _logger.debug("Added namespace %s default gateway %s", net_namespace_info['name'],
                              intf_infos['VIRTRT6'])

            if net_namespace_info['start_sshd']:
                ret = sudo_utils.call([IP_CMD, 'netns', 'exec', net_namespace_info['name'], '/usr/sbin/sshd'])
                if ret != 0:
                    raise Exception("Cannot start ssh daemon")
                _logger.debug('sshd daemon started')
        else:
            _route_table_name = self._compute_routing_table_name(intf_infos)

            NetworkHelpers.add_route_table(_route_table_name)

            _logger.debug("Default ipv4 route add")
            ret, out = NetworkHelpers.add_static_ip_route4(
                'default', 'via', intf_infos['VIRTRT4'], 'dev', _intf_to_use, 'table', _route_table_name)
            if ret != 0:
                raise Exception("Cannot add default route via %s on %s to table %s" %
                                (intf_infos['VIRTRT4'], _intf_to_use, _route_table_name))
            _logger.debug("Added default route via %s dev %s table %s",
                          intf_infos['VIRTRT4'], _intf_to_use, _route_table_name)

            _logger.debug("Default ipv6 route add")
            if 'VIRTRT6' in intf_infos:
                ret, out = NetworkHelpers.add_static_ip_route6(
                    'default', 'via', intf_infos['VIRTRT6'], 'dev', _intf_to_use, 'table', _route_table_name)
                if ret != 0:
                    raise Exception("Cannot add default ipv6 route via %s on %s to table %s" %
                                    (intf_infos['VIRTRT6'], _intf_to_use, _route_table_name))
                _logger.debug("Added default ipv6 route via %s dev %s table %s",
                              intf_infos['VIRTRT6'], _intf_to_use, _route_table_name)

            # create source-based rule to use table
            ip_address = intf_infos['ADDR']
            if NetworkHelpers.is_valid_ipv4_address(ip_address):
                ret, out = NetworkHelpers.add_static_ip_rule4('from', ip_address, 'lookup', _route_table_name)
                if ret != 0:
                    raise Exception("Cannot add rule from %s use table %s" % (intf_infos['ADDR'], _route_table_name))
                _logger.debug("Added rule for routing from %s lookup %s with default via %s",
                              intf_infos['ADDR'], _route_table_name, intf_infos['VIRTRT4'])
            elif NetworkHelpers.is_valid_ipv6_address(ip_address):
                ret, out = NetworkHelpers.add_static_ip_rule6('from', ip_address, 'lookup', _route_table_name)
                if ret != 0:
                    raise Exception("Cannot add rule from %s use table %s" % (intf_infos['ADDR'], _route_table_name))
                _logger.debug("Added rule for routing from %s lookup %s with default via %s",
                              intf_infos['ADDR'], _route_table_name, intf_infos['VIRTRT6'])
            else:
                raise Exception('Invalid ip address: %s' % ip_address)

            # ret, out = NetworkHelpers.add_static_ip_rule('from', intf_infos['ADDR'], 'lookup', _route_table_name)
            # if ret != 0:
            #     raise Exception("Cannot add rule from %s use table %s" % (intf_infos['ADDR'], _route_table_name))

            # _logger.debug("Added rule for routing from %s lookup %s with default via %s",
            #               intf_infos['ADDR'], _route_table_name, intf_infos['VIRTRT'])

    def _config_secondary_intf(self, intf_infos):
        """
        Configures interface secondary IPs

        parameter:
        intf_info: interface info as dict
            keys: see VNICUtils.get_network_config

        Raise:
            Exception. if configuration failed
        """
        _logger.debug('%s: %s', where_am_i(), pformat(intf_infos, indent=4))
        _route_table_name = self._compute_routing_table_name(intf_infos)

        _sec_addrs = []
        if intf_infos.has('SECONDARY_ADDRS'):
            _sec_addrs = intf_infos.get('SECONDARY_ADDRS')
        _logger.debug('secondary addresses: %s', _sec_addrs)

        for secondary_ip in intf_infos['MISSING_SECONDARY_IPS']:
            # _logger.debug('Adding secondary IP address %s to interface (or VLAN) %s',
            #               secondary_ip,
            #               pformat(intf_infos['IFACE'], indent=4))
            try:
                NetworkInterfaceSetupHelper(intf_infos).add_secondary_address(secondary_ip)
            except Exception as e:
                # if adding secondary address fails, skip to the next.
                _logger.debug('Unable to add secondary address %s: %s', secondary_ip, str(e))
                break

            NetworkHelpers.add_route_table(_route_table_name)

            if NetworkHelpers.is_valid_ipv4_address(secondary_ip):
                ret, _ = NetworkHelpers.add_static_ip_rule4('from', secondary_ip, 'lookup', _route_table_name)
            elif NetworkHelpers.is_valid_ipv6_address(secondary_ip):
                ret, _ = NetworkHelpers.add_static_ip_rule6('from', secondary_ip, 'lookup', _route_table_name)
            else:
                raise Exception('Invalid ip address: %s' % secondary_ip)
            if ret != 0:
                raise Exception("Cannot add rule from %s use table %s" % (secondary_ip, _route_table_name))
            _logger.debug("Added rule for routing from %s lookup %s with default via %s",
                          secondary_ip, _route_table_name, intf_infos['VIRTRT'])


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
    _logger.debug('%s: %s %s', where_am_i(), net_namespace_info, intf_infos)
    # if interface is not up bring it up
    if intf_infos['STATE'] != 'up':
        _logger.debug('Bringing intf [%s] up ', intf_infos['IFACE'])
        ret = sudo_utils.call([IP_CMD, 'link', 'set', 'dev', intf_infos['IFACE'], 'up'])
        if ret != 0:
            raise Exception('Cannot bring interface up')

    # create network namespace if needed
    if net_namespace_info is not None:
        if not NetworkHelpers.is_network_namespace_exists(net_namespace_info['name']):
            _logger.debug('creating namespace [%s]', net_namespace_info['name'])
            NetworkHelpers.create_network_namespace(net_namespace_info['name'])
        NetworkInterfaceSetupHelper(intf_infos, net_namespace_info['name']).setup()
    else:
        NetworkInterfaceSetupHelper(intf_infos).setup()


def _auto_deconfig_intf(intf_infos):
    """
    Deconfigures interface

    parameter:

    intf_info: interface info as dict
    keys: see VNICITils.get_network_config

    Raise:
        Exception. if configuration failed
    """
    _logger.debug('%s\n%s', where_am_i(), pformat(intf_infos, indent=4))
    if intf_infos.has('NS'):
        NetworkHelpers.kill_processes_in_namespace(intf_infos['NS'])
    # TODO EJANNET : LOOP on ('SECONDARY_ADDRS')
    #    -> NetworkInterfaceSetupHelper(intf_infos).remove_secondary_address()
    NetworkInterfaceSetupHelper(intf_infos).tear_down()

    # delete namespace
    if intf_infos.has('NS'):
        _logger.debug('deleting namespace [%s]', intf_infos['NS'])
        NetworkHelpers.destroy_network_namespace(intf_infos['NS'])

    NetworkHelpers.add_mac_to_nm(intf_infos['MAC'])
