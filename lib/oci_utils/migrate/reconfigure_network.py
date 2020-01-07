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
import six
import stat
import yaml

from glob import glob
from oci_utils.migrate import get_config_data
from oci_utils.migrate import migrate_tools
from oci_utils.migrate import migrate_utils
from oci_utils.migrate.exception import OciMigrateException
from six.moves import configparser

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
    pregex=fnmatch.translate('*rules')
    rulefiles=[]
    if migrate_tools.dir_exists(udevrootdir):
        #
        # Backup
        shutil.copytree(udevrootdir, os.path.split(udevrootdir)[0] + '/bck_'
                        + os.path.split(udevrootdir)[1]
                        + '_'
                        + migrate_tools.thistime)

        for root, dirs, files in os.walk(udevrootdir):
            for fn in files:
                fullfn = os.path.join(root, fn)
                #
                # Look for .rules file
                if re.search(pregex, fullfn):
                    rulefiles.append(fullfn)
                    macmatch = False
                    with open(fullfn, 'rb') as g:
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
                            fndata = open(mv_fullfn, 'rb').read()
                            newf = open(fullfn, 'wb')
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
    if migrate_tools.dir_exists(ifrootdir):
        for cfgfile in glob(ifrootdir + '/ifcfg-*'):
            _logger.debug('Checking configfile: %s' % cfgfile)
            try:
                with open(cfgfile, 'rb') as f:
                    nl = filter(None, [x[:x.find('#')] for x in f])
                ifcfg = dict(l.translate(None, '"').split('=') for l in nl)
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
                     + migrate_tools.thistime
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
            with open(dhcpniccfg, 'wb') as f:
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
    thisroot = rootdir + get_config_data('default_netplan')
    if migrate_tools.dir_exists(thisroot):
        _logger.debug('netplan directory exists.')
        #
        # contains yaml files?
        yaml_files = glob(thisroot + '/*.yaml')
        if len(yaml_files) > 0:
            for yf in sorted(yaml_files):
                try:
                    with open(yf, 'r') as yfd:
                        thisyaml = yaml.safe_load(yfd)
                        netplan_data[yf] = thisyaml
                        _logger.debug('netplan: %s' % thisyaml)
                except Exception as e:
                    _logger.error('Failed to parse %s: %s' % (yf, str(e)))
                    migrate_tools.error_msg('Failed to parse %s: %s' % (yf, str(e)))
                    break
                #
                if 'network' in thisyaml:
                    if 'ethernets' in thisyaml['network']:
                        for k,_ in sorted(
                                six.iteritems(thisyaml['network']['ethernets'])
                                ):
                            netplan_nics.append(k)
                    else:
                        _logger.debug('ethernets key missing.')
                else:
                    _logger.debug('network key missing.')
            if len(netplan_nics) == 0:
                _logger.debug('No netplan definitions found in %s' % thisroot)
            else:
                nicname = sorted(netplan_nics)[0]
                #
                # rename and recreate
                try:
                    #
                    # backup
                    migrate_tools.exec_rename(thisroot, os.path.split(thisroot)[0]
                                          + '/bck_'
                                          + os.path.split(thisroot)[1]
                                          + '_'
                                          + migrate_tools.thistime)
                    #
                    # recreate dir
                    os.mkdir(thisroot)
                    mode755 = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | \
                              stat.S_IWUSR | stat.S_IRUSR | stat.S_IRGRP | \
                              stat.S_IROTH
                    os.chmod(thisroot, mode755)
                    #
                    # recreate netplan config
                    this_netplan = get_config_data('default_netplan_config')
                    this_netplan['network']['ethernets'][nicname] \
                        = this_netplan['network']['ethernets'].pop('_XXXX_')
                    with open(thisroot + '/'
                              + get_config_data('default_netplan_file'), 'w') \
                            as yf:
                        yaml.safe_dump(this_netplan, yf, default_flow_style=False)
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
    thisdir = rootdir + get_config_data('default_nwconnections')
    _logger.debug('Network manager dir: %s' % thisdir)
    thiscfg = rootdir + get_config_data('default_nwmconfig')
    _logger.debug('Network manager conf: %s' % thiscfg)
    #
    # backup
    try:
        #
        # copy
        if migrate_tools.file_exists(thiscfg):
            _logger.debug('Copy %s %s' % (thiscfg, os.path.split(thiscfg)[0]
                                          + '/bck_'
                                          + os.path.split(thiscfg)[1]
                                          + '_'
                                          + migrate_tools.thistime))
            shutil.copy(thiscfg, os.path.split(thiscfg)[0]
                        + '/bck_'
                        + os.path.split(thiscfg)[1]
                        + '_'
                        + migrate_tools.thistime)
        else:
            _logger.debug('No %s found.' % thiscfg)
        if migrate_tools.dir_exists(thisdir):
            _logger.debug('Copytree %s %s' % (thisdir, os.path.split(thisdir)[0]
                                              + '/bck_'
                                              + os.path.split(thisdir)[1]
                                              + '_'
                                              + migrate_tools.thistime))
            shutil.copytree(thisdir, os.path.split(thisdir)[0]
                            + '/bck_'
                            + os.path.split(thisdir)[1]
                            + '_'
                            + migrate_tools.thistime)
        else:
            _logger.debug('%s not found.' % thisdir)
    except Exception as e:
        migrate_tools.error_msg('Failed to backup the networkmanager '
                            'configuration: %s' % str(e))
    #
    #
    if migrate_tools.dir_exists(thisdir):
        _logger.debug('NetworkManager/%s directory exists.' % thisdir)
        #
        # contains nwm keyfiles?
        nwm_files = glob(thisdir + '/*')
        if len(nwm_files) > 0:
            migrate_utils.exec_rmdir(thisdir)
            migrate_utils.exec_mkdir(thisdir)
            _logger.debug('%s emptied.' % thisdir)
        else:
            _logger.debug('No network manager keyfiles found.')
        #
        # update networkmanager configuration
        # TODO: write config file with configparser
        nwm_config_data = get_config_data('default_nwm_conf_file')
        with open(thiscfg, 'w') as nwmf:
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
    thisroot = rootdir + get_config_data('default_interfaces')
    thisinterfaces = thisroot + '/interfaces'

    if migrate_tools.file_exists(thisinterfaces):
        int_data[get_config_data('default_interfaces')] = list()
        _logger.debug('%s file exists' % thisinterfaces)
        try:
            with open(thisinterfaces, 'r') as inf:
                for ln in inf:
                    int_data[get_config_data('default_interfaces')].append(ln)
                    if 'iface' in ln.split():
                        if ln.split()[1] != 'lo':
                            int_nics.append(ln.split()[1])
                    else:
                        _logger.debug('no iface in %s' % ln)
        except Exception as e:
            _logger.error('Error occured while reading %s: %s'
                         % (thisinterfaces, str(e)))
        #
        # rewrite
        if len(int_nics) == 0:
            _logger.debug('No interface definitions found in %s' %
                          thisinterfaces)
        else:
            try:
                #
                # backup
                _logger.debug('Copytree %s %s' % (thisroot, os.path.split(thisroot)[0]
                                                  + '/bck_'
                                                  + os.path.split(thisroot)[1]
                                                  + migrate_tools.thistime))
                shutil.copytree(thisroot, os.path.split(thisroot)[0]
                                + '/bck_'
                                + os.path.split(thisroot)[1]
                                + '_'
                                + migrate_tools.thistime)
                #
                # remove dir
                shutil.rmtree(thisroot + '/interfaces.d')
                #
                # recreate interfaces config
                with open(thisinterfaces, 'w') as fi:
                    fi.writelines(ln.replace('_XXXX_', int_nics[0]) + '\n'
                                  for ln in get_config_data('default_interfaces_config'))
                migrate_tools.result_msg(msg='Network interfaces file rewritten.',
                                     result=True)
            except Exception as e:
                _logger.error('Failed to write new interfaces configuration '
                             'file %s: %s' % (thisinterfaces, str(e)))
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

    for thisroot in get_config_data('default_systemd'):
        networkd_root = rootdir + thisroot
        if migrate_tools.dir_exists(networkd_root):
            _logger.debug('systemd network directory exists.')
            systemd_files = glob(thisroot + '/*.network')
            if len(systemd_files) > 0:
                for sf in sorted(systemd_files):
                    ignore = False
                    for ig in nw_ignore:
                        if ig in sf:
                            ignore = True
                            break
                    if not ignore:
                        thispars = ConfigParser()
                        sys_data[sf] = dict()
                        try:
                            sv = thispars.read(sf)
                            if 'Match' in thispars.sections():
                                ifname = thispars.get('Match', 'Name')
                                sys_nics.append(ifname)
                            else:
                                _logger.debug('-- No Match section in %s' % sf)
                            #
                            for sec in thispars.sections():
                                sys_data[sf][sec] = thispars.items(sec)
                                _logger.debug('%s' % sys_data[sf][sec])
                        except Exception as e:
                            _logger.error('Failed to parse %s: %s' % (sf, str(e)))
                        #
                        # rename - backup
                        bcknm = os.path.split(sf)[0] + '/bck_' \
                                + os.path.split(sf)[1] + '_' \
                                + migrate_tools.thistime
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
