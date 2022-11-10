#
# Copyright (c) 2020, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.
#

__all__ = ['NetworkInterfaceSetupHelper',
           '_intf_dict'
           ]

import logging
from pprint import pformat

from oci_utils import where_am_i

from . import IP_CMD
from . import network_helpers as NetworkHelpers
from . import sudo_utils
from ..metadata import InstanceMetadata

_logger = logging.getLogger('oci-utils.network_interface')


class _intf_dict(dict):
    """
    Creates a new dictionary representing an interface
    keys are
        CONFSTATE  'uncfg' indicates missing IP config,
                   'missing' missing VNIC,
                   'excl' excluded (-X),
                   '-' hist configuration match oci vcn configuration
    """

    def __init__(self, other=None):
        if other:
            super().__init__(other)
        else:
            super().__init__(CONFSTATE='uncfg')

    def __eq__(self, other):
        return self['MAC'].upper() == other['MAC'].upper()

    def __missing__(self, key):
        return '-'

    def has(self, key):
        """
        Check that key is found in this dict and that
        the value is not None
        """
        return self.__contains__(key) and self.__getitem__(key) is not None

    @staticmethod
    def _to_str(value):
        if isinstance(value, bytes):
            return value.decode()
        if not isinstance(value, str):
            return str(value)
        return value

    def __setitem__(self, key, value):
        """
        everything stored as str
        """
        if isinstance(value, list):
            super().__setitem__(key, [_intf_dict._to_str(_v) for _v in value])
        else:
            super().__setitem__(key, _intf_dict._to_str(value))


class NetworkInterfaceSetupHelper:
    """ Class to assist setting up a network interface.
    """
    _INTF_MTU = 9000

    def __init__(self, interface_info, namespace_name=None):
        """
        Creates a new NetworkInterface

        Parameters:
        ----------
          interface_info : information about the interface as _intf_dict
          namespace_name : [optional] the namespace name in which the setup will happen
        """
        assert isinstance(interface_info, _intf_dict), "Must be a _intf_dict"
        self.info = interface_info
        self.ns = namespace_name
        # _logger.debug('interface_info %s',  pformat(self.info, indent=4))
        # _logger.debug('namespace_name %s',  namespace_name)

    def setup(self):
        """
        Set up the interface.

        Returns
        -------
            No return value, raises an exception in case of error.
        """
        _logger.debug('NetworkInterfaceSetupHelper %s', where_am_i())
        try:
            _metadata = InstanceMetadata().refresh()
        except IOError as e:
            raise Exception('Cannot get instance metadata') from e
        _is_bm_shape = _metadata['instance']['shape'].startswith('BM')

        _macvlan_name = None
        _vlan_name = ''
        #
        # for BM case , create virtual interface if needed
        if _is_bm_shape and self.info['VLTAG'] != "0":

            _vlan_name = '%sv%s' % (self.info['IFACE'], self.info['VLTAG'])
            _macvlan_name = "%s.%s" % (self.info['IFACE'], self.info['VLTAG'])

            _ip_cmd = [IP_CMD]
            if self.info.has('NS'):
                _ip_cmd.extend(['netns', 'exec', self.info['NS'], IP_CMD])

            _ip_cmd.extend(['link', 'add', 'link', self.info['IFACE'],
                            'name', _macvlan_name,
                            'address', self.info['MAC'],
                            'type', 'macvlan'])
            _logger.debug('Creating macvlan [%s]', _macvlan_name)
            ret = sudo_utils.call(_ip_cmd)
            if ret != 0:
                raise Exception("Cannot create MAC VLAN interface %s for MAC address %s"
                                % (_macvlan_name, self.info['MAC']))

            if self.info.has('NS'):
                # if physical iface/nic is in a namespace pull out the created mac vlan
                sudo_utils.call([IP_CMD, 'netns',
                                 'exec', self.info['NS'],
                                 IP_CMD, 'link', 'set', _macvlan_name,
                                 'netns', '1'])
            #
            # create an ip vlan on top of the mac vlan
            ret = sudo_utils.call([IP_CMD, 'link', 'add',
                                   'link', _macvlan_name,
                                   'name', _vlan_name,
                                   'type', 'vlan',
                                   'id', self.info['VLTAG']])
            if ret != 0:
                raise Exception("Cannot create VLAN %s on MAC VLAN %s"
                                % (_vlan_name, _macvlan_name))

        _intf_dev_to_use = None
        if _vlan_name:
            #
            # add the addr on the vlan intf then (BM case)
            _intf_dev_to_use = _vlan_name
        else:
            #
            # add the addr on the intf then (VM case)
            _intf_dev_to_use = self.info['IFACE']

        # move the iface(s) to the target namespace if requested
        if self.ns is not None:
            if _is_bm_shape and _macvlan_name:
                _logger.debug("macvlan link move %s", self.ns)
                ret = sudo_utils.call([IP_CMD, 'link', 'set', 'dev', _macvlan_name, 'netns', self.ns])
                if ret != 0:
                    raise Exception("Cannot move MAC VLAN $macvlan into namespace %s" % self.ns)

            _logger.debug("%s link move %s", _intf_dev_to_use, self.ns)
            ret = sudo_utils.call([IP_CMD, 'link', 'set', 'dev', _intf_dev_to_use, 'netns', self.ns])
            if ret != 0:
                raise Exception("Cannot move interface %s into namespace %s" % (_intf_dev_to_use, self.ns))

        # add IP address to interface
        _ip_cmd_prefix = list()
        if self.ns:
            _logger.debug("ADDR %s/%s add on %s ns '%s'",
                          self.info['ADDR'], self.info['SBITS4'], self.info['IFACE'], self.ns)
        else:
            _logger.debug("ADDR %s/%s add on %s", self.info['ADDR'], self.info['SBITS4'], self.info['IFACE'])
            _ip_cmd_prefix = [IP_CMD]
        if self.ns is not None:
            _ip_cmd_prefix.extend(['netns', 'exec', self.ns, IP_CMD])

        _ip_cmd = list(_ip_cmd_prefix)
        _ip_cmd.extend(['addr', 'add', '%s/%s' % (self.info['ADDR'], self.info['SBITS4']), 'dev', _intf_dev_to_use])

        ret = sudo_utils.call(_ip_cmd)
        if ret != 0:
            raise Exception('Cannot add IP address %s/%s on interface %s' %
                            (self.info['ADDR'], self.info['SBITS4'], self.info['IFACE']))

        if _is_bm_shape and _macvlan_name:
            _logger.debug("vlans set up")
            _ip_cmd = list(_ip_cmd_prefix)
            _ip_cmd.extend(['link', 'set',
                            'dev', _macvlan_name,
                            'mtu', str(NetworkInterfaceSetupHelper._INTF_MTU),
                            'up'])
            ret = sudo_utils.call(_ip_cmd)
            if ret != 0:
                raise Exception("Cannot set MAC VLAN %s up" % _macvlan_name)

            _ip_cmd = list(_ip_cmd_prefix)
            _ip_cmd.extend(['link', 'set', 'dev', _vlan_name, 'mtu', str(NetworkInterfaceSetupHelper._INTF_MTU), 'up'])
            ret = sudo_utils.call(_ip_cmd)
            if ret != 0:
                raise Exception("Cannot set VLAN %s up" % _vlan_name)
        else:
            _logger.debug("%s set up", self.info['IFACE'])
            _ip_cmd = list(_ip_cmd_prefix)
            _ip_cmd.extend(['link', 'set',
                            'dev', self.info['IFACE'],
                            'mtu', str(NetworkInterfaceSetupHelper._INTF_MTU),
                            'up'])
            ret = sudo_utils.call(_ip_cmd)
            if ret != 0:
                raise Exception("Cannot set interface %s MTU" % self.info['IFACE'])

    def tear_down(self):
        """
        Unconfigure the interface.

        Returns
        -------
            None
        Raises
        ------
            Exception in case of error
        """
        _logger.debug('NetworkInterfaceSetupHelper %s\n%s', where_am_i(), pformat(self.info, indent=4))
        _logger.debug('%s', where_am_i())
        _ip_cmd = [IP_CMD]
        if self.info.has('NS'):
            _ip_cmd.extend(['netns', 'exec', self.info['NS'], IP_CMD])

        if self.info.has('VLAN'):
            # delete vlan and macvlan, removes the addrs (pri and sec) as well
            _macvlan_name = "%s.%s" % (self.info['IFACE'], self.info['VLTAG'])
            _ip_cmd.extend(['link', 'del', 'link', self.info['VLAN'], 'dev', _macvlan_name])
            _logger.debug('Deleting macvlan [%s]', _macvlan_name)
            ret = sudo_utils.call(_ip_cmd)
            if ret != 0:
                raise Exception("Cannot remove VLAN %s" % self.info['VLTAG'])
        else:
            if self.info.has('ADDR'):
                # delete addr from phys iface
                # deleting namespace will move phys iface back to main
                # note that we may be deleting sec addr from a vlan here
                _ip_cmd.extend(['addr', 'del',
                                '%s/%s' % (self.info['ADDR'], self.info['SBITS4']),
                                'dev', self.info['IFACE']])
                _logger.debug('Deleting interface [%s]', self.info['IFACE'])
                ret = sudo_utils.call(_ip_cmd)
                if ret != 0:
                    raise Exception("Cannot remove ip address [%s] from %s" % (self.info['ADDR'], self.info['IFACE']))
                # NetworkHelpers.remove_ip_addr_rules(self.info['ADDR'])
                NetworkHelpers.remove_ip_rules(self.info['ADDR'])

    def add_secondary_address(self, ip_address):
        """
        Add a secondary ip address ro this interface
        Add it to VLAN or device according to this being VLANed or not

        Parameters
        ----------
            ip_address: the IP to be removed as str
        Raise
        -----
            Exception : in case of error during removal
        """
        _logger.debug('%s: %s', where_am_i(), ip_address)
        if self.info.has('VLAN'):
            _dev = self.info['VLAN']
        else:
            _dev = self.info['IFACE']

        _ip_cmd = NetworkHelpers.ip_cmd_version(ip_address)
        ip_addr = '%s/32' % ip_address if '-4' in _ip_cmd else '%s/128' % ip_address

        if self.info.has('NS'):
            _ip_cmd.extend(['netns', 'exec', self.info['NS'], IP_CMD])
        _ip_cmd.extend(['addr', 'add', '%s' % ip_addr, 'dev', _dev])
        ret = sudo_utils.call(_ip_cmd)
        _logger.debug('Execution o %s result %s', _ip_cmd, ret)

        if ret == 2:
            _logger.debug('Secondary address %s already exists.', ip_addr)
        if ret != 0:
            raise ValueError('Adding secondary address %s failed.' % ip_addr)

    def remove_secondary_address(self, ip_address):
        """
        Remove a secondary ip address from this interface
        Remove it from VLAN or device according to this being VLANed or not
        Parameters
        ----------
           ip_address: the IP to be removed as str

        Raise
        -----
            Exception : in case of error during removal
        """
        _logger.debug('%s: %s', where_am_i(), ip_address)
        if self.info.has('VLAN'):
            _dev = self.info['VLAN']
        else:
            _dev = self.info['IFACE']

        _ip_cmd = NetworkHelpers.ip_cmd_version(ip_address)
        if self.info.has('NS'):
            _ip_cmd.extend(['netns', 'exec', self.info['NS'], IP_CMD])
        ip_addr = '%s/32' % ip_address if '-4' in _ip_cmd else '%s/128' % ip_address
        _ip_cmd.extend(['addr', 'del', '%s' % ip_addr, 'dev', _dev])
        ret = sudo_utils.call(_ip_cmd)
        if ret != 0:
            raise Exception('Cannot remove secondary address')
