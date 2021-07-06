#
# Copyright (c) 2020, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.
#

__all__ = ['NetworkInterfaceSetupHelper', '_intf_dict']

import logging
from . import sudo_utils
from ..metadata import InstanceMetadata
from . import network_helpers as NetworkHelpers


_logger = logging.getLogger('oci-utils.network_interface')


class _intf_dict(dict):
    """
    Creates a new dictionnary representing an interface
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
    _INTF_MTU = 9000

    def __init__(self, interface_info, namespace_name=None):
        """
        Creates a new NetworkInterface
        parameter:
          interface_info : information about the interface as _intf_dict
          namespace_name : [optional] the namespace name in which the setup will happen
        """
        assert isinstance(interface_info, _intf_dict), "must be a _intf_dict"
        self.info = interface_info
        self.ns = namespace_name

    def setup(self):
        """
        Setups the interface.
        returns:
            None
        raises:
            Exception in case of error
        """
        # for BM case , create virtual interface if needed

        try:
            _metadata = InstanceMetadata().refresh()
        except IOError as e:
            raise Exception('cannot get instance metadata') from e
        _is_bm_shape = _metadata['instance']['shape'].startswith('BM')

        _macvlan_name = None
        _vlan_name = ''
        if _is_bm_shape and self.info['VLTAG'] != "0":

            _vlan_name = '%sv%s' % (self.info['IFACE'], self.info['VLTAG'])
            _macvlan_name = "%s.%s" % (self.info['IFACE'], self.info['VLTAG'])

            _ip_cmd = ['/usr/sbin/ip']
            if self.info.has('NS'):
                _ip_cmd.extend(['netns', 'exec', self.info['NS'], '/usr/sbin/ip'])

            _ip_cmd.extend(['link', 'add', 'link', self.info['IFACE'], 'name', _macvlan_name, 'address',
                            self.info['MAC'], 'type', 'macvlan'])
            _logger.debug('creating macvlan [%s]', _macvlan_name)
            ret = sudo_utils.call(_ip_cmd)
            if ret != 0:
                raise Exception("cannot create MAC VLAN interface %s for MAC address %s" %
                                (_macvlan_name, self.info['MAC']))

            if self.info.has('NS'):
                # if physical iface/nic is in a namespace pull out the created mac vlan
                sudo_utils.call(['/usr/sbin/ip', 'netns', 'exec', self.info['NS'],
                                 '/usr/sbin/ip', 'link', 'set', _macvlan_name, 'netns', '1'])

            # create an ip vlan on top of the mac vlan
            ret = sudo_utils.call(['/usr/sbin/ip', 'link', 'add', 'link', _macvlan_name,
                                   'name', _vlan_name, 'type', 'vlan', 'id', self.info['VLTAG']])
            if ret != 0:
                raise Exception("cannot create VLAN %s on MAC VLAN %s" % (_vlan_name, _macvlan_name))

        _intf_dev_to_use = None
        if _vlan_name:
            # add the addr on the vlan intf then (BM case)
            _intf_dev_to_use = _vlan_name
        else:
            # add the addr on the intf then (VM case)
            _intf_dev_to_use = self.info['IFACE']

        # move the iface(s) to the target namespace if requested
        if self.ns is not None:
            if _is_bm_shape and _macvlan_name:
                _logger.debug("macvlan link move %s", self.ns)
                ret = sudo_utils.call(['/usr/sbin/ip', 'link', 'set', 'dev',
                                       _macvlan_name, 'netns', self.ns])
                if ret != 0:
                    raise Exception("cannot move MAC VLAN $macvlan into namespace %s" % self.ns)

            _logger.debug("%s link move %s", _intf_dev_to_use, self.ns)
            ret = sudo_utils.call(['/usr/sbin/ip', 'link', 'set', 'dev',
                                   _intf_dev_to_use, 'netns', self.ns])
            if ret != 0:
                raise Exception("cannot move interface %s into namespace %s" %
                                (_intf_dev_to_use, self.ns))

        # add IP address to interface
        if self.ns:
            _logger.debug("addr %s/%s add on %s ns '%s'",
                          self.info['ADDR'], self.info['SBITS'], self.info['IFACE'], self.ns)
        else:
            _logger.debug("addr %s/%s add on %s", self.info['ADDR'], self.info['SBITS'], self.info['IFACE'])
            _ip_cmd_prefix = ['/usr/sbin/ip']
        if self.ns is not None:
            _ip_cmd_prefix.extend(['netns', 'exec', self.ns, '/usr/sbin/ip'])

        _ip_cmd = list(_ip_cmd_prefix)
        _ip_cmd.extend(['addr', 'add', '%s/%s' % (self.info['ADDR'], self.info['SBITS']), 'dev', _intf_dev_to_use])

        ret = sudo_utils.call(_ip_cmd)
        if ret != 0:
            raise Exception('cannot add IP address %s/%s on interface %s' %
                            (self.info['ADDR'], self.info['SBITS'], self.info['IFACE']))

        if _is_bm_shape and _macvlan_name:
            _logger.debug("vlans set up")
            _ip_cmd = list(_ip_cmd_prefix)
            _ip_cmd.extend(['link', 'set', 'dev', _macvlan_name, 'mtu',
                            str(NetworkInterfaceSetupHelper._INTF_MTU), 'up'])
            ret = sudo_utils.call(_ip_cmd)
            if ret != 0:
                raise Exception("cannot set MAC VLAN %s up" % _macvlan_name)

            _ip_cmd = list(_ip_cmd_prefix)
            _ip_cmd.extend(['link', 'set', 'dev', _vlan_name, 'mtu', str(NetworkInterfaceSetupHelper._INTF_MTU), 'up'])
            ret = sudo_utils.call(_ip_cmd)
            if ret != 0:
                raise Exception("cannot set VLAN %s up" % _vlan_name)
        else:
            _logger.debug("%s set up", self.info['IFACE'])
            _ip_cmd = list(_ip_cmd_prefix)
            _ip_cmd.extend(['link', 'set', 'dev', self.info['IFACE'], 'mtu',
                            str(NetworkInterfaceSetupHelper._INTF_MTU), 'up'])
            ret = sudo_utils.call(_ip_cmd)
            if ret != 0:
                raise Exception("cannot set interface $iface MTU" % self.info['IFACE'])

    def tear_down(self):
        """
        unconfigure the interface.
        returns:
            None
        raises:
            Exception in case of error
        """
        _ip_cmd = ['/usr/sbin/ip']
        if self.info.has('NS'):
            _ip_cmd.extend(['netns', 'exec', self.info['NS'], '/usr/sbin/ip'])

        if self.info.has('VLAN'):
            # delete vlan and macvlan, removes the addrs (pri and sec) as well
            _macvlan_name = "%s.%s" % (self.info['IFACE'], self.info['VLTAG'])
            _ip_cmd.extend(['link', 'del', 'link', self.info['VLAN'], 'dev', _macvlan_name])
            _logger.debug('deleting macvlan [%s]', _macvlan_name)
            ret = sudo_utils.call(_ip_cmd)
            if ret != 0:
                raise Exception("cannot remove VLAN %s" % self.info['VLTAG'])
        else:
            if self.info.has('ADDR'):
                # delete addr from phys iface
                # deleting namespace will move phys iface back to main
                # note that we may be deleting sec addr from a vlan here
                _ip_cmd.extend(['addr', 'del', '%s/%s' % (self.info['ADDR'],
                                                          self.info['SBITS']), 'dev', self.info['IFACE']])
                _logger.debug('deleting interface [%s]', self.info['IFACE'])
                ret = sudo_utils.call(_ip_cmd)
                if ret != 0:
                    raise Exception("cannot remove ip address [%s] from %s" % (self.info['ADDR'], self.info['IFACE']))
                NetworkHelpers.remove_ip_addr_rules(self.info['ADDR'])

    def add_secondary_address(self, ip_address):
        """
        Add and secondary ip address from this interface
        Add it to VLAN or device according to this being VLANed or not
        parameter:
           ip_address: the IP to be removed as str
        raise:
        Exception : in case of error during removal
        """
        if self.info.has('VLAN'):
            _dev = self.info['VLAN']
        else:
            _dev = self.info['IFACE']

        _ip_cmd = ['/usr/sbin/ip']
        if self.info.has('NS'):
            _ip_cmd.extend(['netns', 'exec', self.info['NS'], '/usr/sbin/ip'])
        _ip_cmd.extend(['addr', 'add', '%s/32' % ip_address, 'dev', _dev])
        ret = sudo_utils.call(_ip_cmd)
        if ret != 0:
            raise Exception('Cannot add secondary address')

    def remove_secondary_address(self, ip_address):
        """
        Remove and secondary ip address from this interface
        Remove it from VLAN or device according to this being VLANed or not
        parameter:
           ip_address: the IP to be removed as str
        raise:
        Exception : in case of error during removal
        """

        if self.info.has('VLAN'):
            _dev = self.info['VLAN']
        else:
            _dev = self.info['IFACE']

        _ip_cmd = ['/usr/sbin/ip']
        if self.info.has('NS'):
            _ip_cmd.extend(['netns', 'exec', self.info['NS'], '/usr/sbin/ip'])
        _ip_cmd.extend(['addr', 'del', '%s/32' % ip_address, 'dev', _dev])
        ret = sudo_utils.call(_ip_cmd)
        if ret != 0:
            raise Exception('Cannot remove secondary address')
