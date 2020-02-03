# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" 
Module containing methods for the configuration of the networking with
respect to upload to the Oracle Cloud Infrastructure.
"""
import logging
import fnmatch
import os
import re
import shutil
import configparser
import stat
import yaml

from glob import glob
from oci_utils.migrate import get_config_data
from oci_utils.migrate import migrate_tools
from oci_utils.migrate import migrate_utils
from oci_utils.migrate.exception import OciMigrateException

_logger = logging.getLogger('oci-utils.reconfigure-network')
ConfigParser = configparser.ConfigParser


def cleanup_udev(rootdir):
    """
    Cleanup eventual HWADDR - device name definitions in udev rules.

    Parameters
    ----------
    rootdir: str
        Full path of udev root dir.

    Returns
    -------

    """
    _logger.debug('Update network udev rules.')
    udevrootdir = rootdir + '/etc/udev'
    _logger.debug('udev root is %s' % udevrootdir)
    pregex = fnmatch.translate('*rules')
    rulefiles = []
    if os.path.isdir(udevrootdir):
        #
        # Backup
        shutil.copytree(udevrootdir, os.path.split(udevrootdir)[0] + '/bck_'
                        + os.path.split(udevrootdir)[1]
                        + '_'
                        + migrate_tools.current_time)

        for root, dirs, files in os.walk(udevrootdir):
            for fn in files:
                fullfn = os.path.join(root, fn)
                #
                # Look for .rules file
                if re.search(pregex, fullfn):
                    rulefiles.append(fullfn)
                    macmatch = False
                    with open(fullfn, 'r') as g:
                        #
                        # Look for network naming rules
                        for line in g:
                            if re.match("(.*)KERNEL==\"eth(.*)", line):
                                macmatch = True
                                _logger.debug('Found rule in %s.' % fullfn)
                                break
                    if macmatch:
                        #
                        # Rewrite the network naming rules
                        mv_fullfn = fullfn + '_save'
                        try:
                            shutil.move(fullfn, mv_fullfn)
                            fndata = open(mv_fullfn, 'r').read()
                            newf = open(fullfn, 'w')
                            for lx in fndata.split('\n'):
                                if not re.match("(.*)KERNEL==\"eth(.*)", lx):
                                    newf.write('%s\n' % lx)
                            newf.close()
                            os.remove(mv_fullfn)
                        except Exception as e:
                            _logger.error('Failed to rewrite udev network '
                                          'naming rules: %s' % str(e))
                            return False
    else:
        _logger.debug('Directory %s not found.')
    return True


def reconfigure_ifcfg_config(rootdir):
    """
    Modify the network configuration in the image file to prevent
    conflicts during import. This is only for ol-type linux.

    Parameters
    ----------
    rootdir: str
        Full path of image root dir as loopback mounted.

    Returns
    -------
        list: list of nic.
        dict: the interfaces configuration.
    """
    #
    # Rename the config files
    _logger.debug('The network ifcfg configuration.')
    ifcfg_list = list()
    ifcfg_data = dict()
    ifrootdir = rootdir + get_config_data('default_ifcfg')
    if os.path.isdir(ifrootdir):
        for cfgfile in glob(ifrootdir + '/ifcfg-*'):
            _logger.debug('Checking configfile: %s' % cfgfile)
            try:
                with open(cfgfile, 'r') as f:
                    # nl = filter(None, [x[:x.find('#')] for x in f])
                    nl = [_f for _f in [x[:x.find('#')] for x in f] if _f]
                ifcfg = dict(dl.replace('"', '').split('=') for dl in nl)
                if 'DEVICE' in ifcfg:
                    devname = ifcfg['DEVICE']
                else:
                    _logger.debug('Missing device name in %s' % cfgfile)
                    devname = cfgfile.split('/')[-1]
                ifcfg_list.append(devname)
                ifcfg_data[devname] = ifcfg
                _logger.debug('Network interface: %s' % devname)
            except Exception as e:
                _logger.error('Problem reading network configuration file %s: '
                              '%s' % (cfgfile, str(e)))
    else:
        _logger.debug('No ifcfg network configuration.')
    #
    # backup
    for fn in glob(ifrootdir + '/ifcfg-*'):
        if 'ifcfg-lo' not in fn:
            fn_bck = os.path.split(fn)[0] \
                     + '/bck_' \
                     + os.path.split(fn)[1] \
                     + '_' \
                     + migrate_tools.current_time
            if migrate_tools.exec_rename(fn, fn_bck):
                _logger.debug('Network config file %s successfully '
                              'renamed to %s' % (fn, fn_bck))
            else:
                migrate_tools.error_msg('Failed to backup network configuration '
                                        'file %s to %s.' % (fn, fn_bck))
                raise OciMigrateException('Failed to rename network config '
                                          'file %s to %s' % (fn, fn_bck))
        else:
            _logger.debug('ifcfg-lo found.')
    #
    # Generate new default network configuration.
    if len(ifcfg_list) > 0:
        nic0 = sorted(ifcfg_list)[0]
        dhcpniccfg = ifrootdir + '/ifcfg-%s' % nic0
        _logger.debug('Replacing network config file %s' % dhcpniccfg)
        try:
            with open(dhcpniccfg, 'w') as f:
                f.writelines(ln.replace('_XXXX_', nic0) + '\n'
                             for ln in get_config_data('default_ifcfg_config'))
            migrate_tools.result_msg(msg='Replaced ifcfg network configuration.',
                                     result=True)
        except Exception as e:
            _logger.error('Failed to write %s/ifcfg-eth0' % ifrootdir)
            migrate_tools.error_msg('Failed to write %s: %s' % (dhcpniccfg, str(e)))
            raise OciMigrateException('Failed to write %s: %s'
                                      % (dhcpniccfg, str(e)))
    else:
        _logger.debug('No ifcfg definitions found.')
    #
    return ifcfg_list, ifcfg_data


def reconfigure_netplan(rootdir):
    """
    Parse the yaml netplan files and look for network interface names.

    Parameters
    ----------
    rootdir: str
        Full path of image root dir as loopback mounted.

    Returns
    -------
        list: list of nic.
        dict: the netplan network configurations.
    """

    _logger.debug('The netplan configuration.')
    netplan_data = dict()
    netplan_nics = list()
    root_path = rootdir + get_config_data('default_netplan')
    if os.path.isdir(root_path):
        _logger.debug('netplan directory exists.')
        #
        # contains yaml files?
        yaml_files = glob(root_path + '/*.yaml')
        if len(yaml_files) > 0:
            for yf in sorted(yaml_files):
                try:
                    with open(yf, 'r') as yfd:
                        yaml_data = yaml.safe_load(yfd)
                        netplan_data[yf] = yaml_data
                        _logger.debug('netplan: %s' % yaml_data)
                except Exception as e:
                    _logger.error('Failed to parse %s: %s' % (yf, str(e)))
                    migrate_tools.error_msg('Failed to parse %s: %s' % (yf, str(e)))
                    break
                #
                if 'network' in yaml_data:
                    if 'ethernets' in yaml_data['network']:
                        for k,_ in sorted(yaml_data['network']['ethernets'].items()):
                            netplan_nics.append(k)
                    else:
                        _logger.debug('ethernets key missing.')
                else:
                    _logger.debug('network key missing.')
            if len(netplan_nics) == 0:
                _logger.debug('No netplan definitions found in %s' % root_path)
            else:
                nicname = sorted(netplan_nics)[0]
                #
                # rename and recreate
                try:
                    #
                    # backup
                    migrate_tools.exec_rename(root_path, os.path.split(root_path)[0]
                                              + '/bck_'
                                              + os.path.split(root_path)[1]
                                              + '_'
                                              + migrate_tools.current_time)
                    #
                    # recreate dir
                    os.mkdir(root_path)
                    mode755 = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | \
                              stat.S_IWUSR | stat.S_IRUSR | stat.S_IRGRP | \
                              stat.S_IROTH
                    os.chmod(root_path, mode755)
                    #
                    # recreate netplan config
                    netplan_config = get_config_data('default_netplan_config')
                    netplan_config['network']['ethernets'][nicname] \
                        = netplan_config['network']['ethernets'].pop('_XXXX_')
                    with open(root_path + '/'
                              + get_config_data('default_netplan_file'), 'w') \
                            as yf:
                        yaml.safe_dump(netplan_config, yf, default_flow_style=False)
                    migrate_tools.result_msg(msg='Netplan network configuration '
                                             'files replaced.', result=True)
                except Exception as e:
                    migrate_tools.error_msg('Failed to write new netplan '
                                            'configuration file %s: %s'
                                            % (get_config_data('default_netplan_file'), str(e)))
                    raise OciMigrateException('Failed to write new netplan '
                                              'configuration file %s: %s'
                                              % (get_config_data('default_netplan_file'), str(e)))
        else:
            _logger.error('No netplan yaml config files found.')
    else:
        _logger.debug('No netplan configuration found.')

    return netplan_nics, netplan_data


def reconfigure_networkmanager(rootdir):
    """
    Replace the networkmanager configuration with Oracle Cloud Infrastructure
    compatible version.

    Parameters
    ----------
    rootdir: str
        Full path of image root dir as loopback mounted.
    Returns
    -------
        list: list of nic.
        dict: the network manager system-connections configurations
    """
    _logger.debug('The NetworkManager configuration.')
    netwmg_data = dict()
    netwmg_nics = list()
    network_config_dir = rootdir + get_config_data('default_nwconnections')
    _logger.debug('Network manager dir: %s' % network_config_dir)
    nw_mgr_cfg = rootdir + get_config_data('default_nwmconfig')
    _logger.debug('Network manager conf: %s' % nw_mgr_cfg)
    #
    # backup
    try:
        #
        # copy
        if os.path.isfile(nw_mgr_cfg):
            _logger.debug('Copy %s %s' % (nw_mgr_cfg, os.path.split(nw_mgr_cfg)[0]
                                          + '/bck_'
                                          + os.path.split(nw_mgr_cfg)[1]
                                          + '_'
                                          + migrate_tools.current_time))
            shutil.copy(nw_mgr_cfg, os.path.split(nw_mgr_cfg)[0]
                        + '/bck_'
                        + os.path.split(nw_mgr_cfg)[1]
                        + '_'
                        + migrate_tools.current_time)
        else:
            _logger.debug('No %s found.' % nw_mgr_cfg)
        if os.path.isdir(network_config_dir):
            _logger.debug('Copytree %s %s' % (network_config_dir, os.path.split(network_config_dir)[0]
                                              + '/bck_'
                                              + os.path.split(network_config_dir)[1]
                                              + '_'
                                              + migrate_tools.current_time))
            shutil.copytree(network_config_dir, os.path.split(network_config_dir)[0]
                            + '/bck_'
                            + os.path.split(network_config_dir)[1]
                            + '_'
                            + migrate_tools.current_time)
        else:
            _logger.debug('%s not found.' % network_config_dir)
    except Exception as e:
        migrate_tools.error_msg('Failed to backup the networkmanager '
                                'configuration: %s' % str(e))
    #
    #
    if os.path.isdir(network_config_dir):
        _logger.debug('NetworkManager/%s directory exists.' % network_config_dir)
        #
        # contains nwm keyfiles?
        nwm_files = glob(network_config_dir + '/*')
        if len(nwm_files) > 0:
            migrate_utils.exec_rmdir(network_config_dir)
            migrate_utils.exec_mkdir(network_config_dir)
            _logger.debug('%s emptied.' % network_config_dir)
        else:
            _logger.debug('No network manager keyfiles found.')
        #
        # update networkmanager configuration
        # TODO: write config file with configparser
        nwm_config_data = get_config_data('default_nwm_conf_file')
        with open(nw_mgr_cfg, 'w') as nwmf:
            nwmf.write('\n'.join(str(x) for x in nwm_config_data))
            migrate_tools.result_msg(msg='Networkmanager configuration updated.',
                                     result=True)
    else:
        _logger.debug(msg='  No NetworkManager configuration present.')

    return netwmg_nics, netwmg_data


def reconfigure_interfaces(rootdir):
    """
    Parse the network interfaces file.

    Parameters
    ----------
    rootdir: str
        Full path of image root dir as loopback mounted.

    Returns
    -------
        list: list of nic.
        dict: the interfaces configuration.
    """
    _logger.debug('The network interfaces configuration.')
    int_data = dict()
    int_nics = list()
    root_path = rootdir + get_config_data('default_interfaces')
    net_ifcfg_config = root_path + '/interfaces'

    if os.path.isfile(net_ifcfg_config):
        int_data[get_config_data('default_interfaces')] = list()
        _logger.debug('%s file exists' % net_ifcfg_config)
        try:
            with open(net_ifcfg_config, 'r') as inf:
                for ln in inf:
                    int_data[get_config_data('default_interfaces')].append(ln)
                    if 'iface' in ln.split():
                        if ln.split()[1] != 'lo':
                            int_nics.append(ln.split()[1])
                    else:
                        _logger.debug('no iface in %s' % ln)
        except Exception as e:
            _logger.error('Error occured while reading %s: %s'
                          % (net_ifcfg_config, str(e)))
        #
        # rewrite
        if len(int_nics) == 0:
            _logger.debug('No interface definitions found in %s' %
                          net_ifcfg_config)
        else:
            try:
                #
                # backup
                _logger.debug('Copytree %s %s' % (root_path, os.path.split(root_path)[0]
                                                  + '/bck_'
                                                  + os.path.split(root_path)[1]
                                                  + migrate_tools.current_time))
                shutil.copytree(root_path, os.path.split(root_path)[0]
                                + '/bck_'
                                + os.path.split(root_path)[1]
                                + '_'
                                + migrate_tools.current_time)
                #
                # remove dir
                shutil.rmtree(root_path + '/interfaces.d')
                #
                # recreate interfaces config
                with open(net_ifcfg_config, 'w') as fi:
                    fi.writelines(ln.replace('_XXXX_', int_nics[0]) + '\n'
                                  for ln in get_config_data('default_interfaces_config'))
                migrate_tools.result_msg(msg='Network interfaces file rewritten.',
                                         result=True)
            except Exception as e:
                _logger.error('Failed to write new interfaces configuration '
                              'file %s: %s' % (net_ifcfg_config, str(e)))
    else:
        _logger.debug('No network interfaces configuration.')
    return int_nics, int_data


def reconfigure_systemd_networkd(rootdir):
    """
    Parse the systemd network configuration.

    Parameters
    ----------
    rootdir: str
        Full path of image root dir as loopback mounted.

    Returns
    -------
        list: list of nic.
        dict: the interfaces configuration.
    """
    _logger.debug('The network systemd-networkd configuration.')
    sys_data = dict()
    sys_nics = list()
    nw_ignore = ['container-host0', 'container-ve', 'container-vz']

    for root_path in get_config_data('default_systemd'):
        networkd_root = rootdir + root_path
        if os.path.isdir(networkd_root):
            _logger.debug('systemd network directory exists.')
            systemd_files = glob(root_path + '/*.network')
            if len(systemd_files) > 0:
                for sf in sorted(systemd_files):
                    ignore = False
                    for ig in nw_ignore:
                        if ig in sf:
                            ignore = True
                            break
                    if not ignore:
                        systemtd_net_config = ConfigParser()
                        sys_data[sf] = dict()
                        try:
                            sv = systemtd_net_config.read(sf)
                            if 'Match' in systemtd_net_config.sections():
                                ifname = systemtd_net_config.get('Match', 'Name')
                                sys_nics.append(ifname)
                            else:
                                _logger.debug('-- No Match section in %s' % sf)
                            #
                            for sec in systemtd_net_config.sections():
                                sys_data[sf][sec] = systemtd_net_config.items(sec)
                                _logger.debug('%s' % sys_data[sf][sec])
                        except Exception as e:
                            _logger.error('Failed to parse %s: %s' % (sf, str(e)))
                        #
                        # rename - backup
                        bcknm = os.path.split(sf)[0] + '/bck_' \
                                              + os.path.split(sf)[1] + '_' \
                                              + migrate_tools.current_time
                        if migrate_tools.exec_rename(sf, bcknm):
                            _logger.debug('Network config file %s renamed to %s'
                                          % (sf, bcknm))
                            _logger.debug('Network config file %s successfully '
                                          'renamed to %s'
                                          % (sf, os.path.split(sf)[0]
                                            + '/bck' + os.path.split(sf)[1]
                                            + '_bck'))
                        else:
                            _logger.error('Failed to rename %s to %s'
                                          % (sf, os.path.split(sf)[0]
                                            + '/bck'
                                            + os.path.split(sf)[1]
                                            + '_bck'))
                            raise OciMigrateException('Failed to rename %s '
                                                      'to %s' % (sf, bcknm))
            else:
                _logger.debug('No systemd-networkd configuration.')
        else:
            _logger.debug('%s does not exist.'
                          % get_config_data('default_systemd'))
    #
    # write new config
    if len(sys_nics) > 0:
        nicname = sorted(sys_nics)[0]
        with open(rootdir + get_config_data('default_systemd_file'), 'w') as sdf:
            sdf.writelines(ln.replace('_XXXX_', nicname) + '\n'
                           for ln in get_config_data('default_systemd_config'))
        migrate_tools.result_msg(msg='systemd-networkd configuration rewritten.',
                                 result=True)
    else:
        _logger.debug('No systemd-networkd configuration.')
    return sorted(sys_nics), sys_data


def update_network_config(rootdir):
    """
    Modify the network configuration in the image file to prevent conflicts
    during import. Currently
    ifcfg, NetworkManager, netplan, network connections systemd-networkd and
    interface
    file are scanned. Bonding and bridging are not supported for now,
    nor multiple ip per interface.

    Parameters
    ----------
    rootdir: str
        Full path of image root dir.

    Returns
    -------
        dict: List with dictionary representation of the network
        configuration files.
    """
    migrate_tools.result_msg(msg='Adjust network configuration.', result=True)
    network_config = dict()
    network_list = list()
    #
    # Cleanup udev network device naming.
    if cleanup_udev(rootdir):
        _logger.debug('udev successfully modified.')
    else:
        _logger.debug('Failed to modify udev rules with respect to network '
                      'device naming.')
    #
    # ifcfg
    ifcfg_nics, ifcfg_data = reconfigure_ifcfg_config(rootdir)
    network_list += ifcfg_nics
    network_config['ifcfg'] = ifcfg_data
    #
    # netplan
    netplan_nics, netplan_data = reconfigure_netplan(rootdir)
    network_list += netplan_nics
    network_config['netplan'] = netplan_data
    #
    # network manager
    nwmg_nics, nwmg_data = reconfigure_networkmanager(rootdir)
    network_list += nwmg_nics
    network_config['network_manager'] = nwmg_data
    #
    # interfaces
    int_list, int_data = reconfigure_interfaces(rootdir)
    network_list += int_list
    network_config['interfaces'] = int_data
    #
    # systemd
    netsys_nics, netsys_data = reconfigure_systemd_networkd(rootdir)
    network_list += netsys_nics
    network_config['systemd-networkd'] = netsys_data

    return network_list, network_config
