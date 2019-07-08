#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing Ubuntu Linux type specific OS methods.
"""
import logging
import os
import sys

# for the sake of testing
sys.path.append('/omv/data/git_pycharm/oci-utils/lib')
import yaml
from oci_utils.migrate import gen_tools
from oci_utils.migrate import migrate_utils
from oci_utils.migrate import data
from oci_utils.migrate.exception import OciMigrateException
from ConfigParser import ConfigParser


logger = logging.getLogger('oci-image-migrate')

_os_type_tag_csl_tag_type_os_ = 'ubuntu,'

def exec_apt(cmd):
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
    logger.debug('apt command: %s' % cmd)
    try:
        logger.debug('command: %s' % cmd)
        output= gen_tools.run_popen_cmd(cmd)
        logger.debug('apt command output: %s' % str(output))
        return output
    except Exception as e:
        logger.critical('Failed to execute apt: %s' % str(e))
        raise OciMigrateException('\nFailed to execute apt: %s' % str(e))


def install_cloud_init(*args):
    """
    Install cloud init package
    Parameters
    ----------
    args: tbd

    Returns
    -------
        bool: True on success, raise an exception otherwise.
    """
    try:
        installoutput = exec_apt(['install', '-y', 'cloud-init'])
        logger.debug('Successfully installed cloud init:\n%s' % installoutput)
    except Exception as e:
        logger.critical('Failed to install the cloud-init package:\n%s' % str(e))
        gen_tools.error_msg('Failed to install the cloud-init package:\n%s' % str(e))
        raise OciMigrateException('Failed to install the cloud-init package:\n%s' % str(e))
    return True


def update_network_config():
    """
    Modify the network configuration in the image file to prevent conflicts
    during import. This is only for Ubuntu-type linux. Currently
    NetworkManger, netplan, network connections and interface
    file are scanned. Bonding and bridging are not supported for now,
    nor multiple ip per
    interface.

    Returns
    -------

    """
    resval = {}
    #
    # Network Manager. Only looking in the default location, for now.
    nwmf = data.default_nwmconfig
    resval['NWM'] = False
    if gen_tools.file_exists(nwmf):
        logger.debug('NetworkManager config file %s exists.' % nwmf)
        thisparser = ConfigParser()
        try:
            rf = thisparser.read(nwmf)
            sectiondata = dict(thisparser.items('ifupdown'))
            logger.debug('NWM configuration: %s' % sectiondata)
            if sectiondata['managed'].lower() == 'false':
                logger.debug('NetworkManager not active.')
            else:
                logger.debug('NetworkManager is active.')
                resval['NWM'] = True
        except Exception as e:
            logger.error('Failed to read Network Manager configuration %s: '
                         '%s.' % (nwmf, str(e)))
            # raise OciMigrateException('Failed to read OCI configuration %s: %s.' % (data.ociconfigfile, str(e)))
    else:
        logger.debug('File %s does not exist.' % nwmf)
    #
    # Network connections
    resval['netconnections'] = False
    nwcf = data.default_nwconnections
    if gen_tools.dir_exists(nwcf):
        logger.debug('Directory %s exists.' % nwcf)
        dircontents = os.listdir(nwcf)
        logger.debug('Found %s.' % dircontents)
        for nwfn in os.listdir(nwcf):
            thisparser = ConfigParser()
            try:
                logger.debug('Connection: %s' % nwfn)
                rg = thisparser.read(nwfn)
                condata = dict(thisparser.items('connection'))
                logger.debug('Connection data: %s' % condata)
                ipv4data = dict(thisparser.items('ipv4'))
                logger.debug('ipv4 data: %s' % ipv4data)
                if ipv4data['method'] is not 'disabled':
                    logger.debug('Found an enabled network: %s' % condata['id'])
                    resval['netconnections'] = True
                ipv6data = dict(thisparser.items('ipv6'))
                logger.debug('ipv6 data: %s' % ipv6data)
            except Exception as e:
                logger.error('Failed to read Network Connections '
                             'configuration %s: %s' % (nwfn, str(e)))
    else:
        logger.debug('Directory %s does not exist.' % nwcf)
    #
    # netplan
    resval['netplan'] = False
    npf = data.default_netplan
    gots1 = False
    if gen_tools.dir_exists(npf):
        logger.debug('Directory %s exists.' % npf)
        dircontents = os.listdir(npf)
        logger.debug('Found %s.' % dircontents)
        for fn in dircontents:
            if fn.split('.')[-1] == 'yaml':
                thisfn = npf + '/' + fn
                logger.debug('Reading file %s' % thisfn)
                try:
                    if not gots1:
                        with open(thisfn, 'r') as yamlfile:
                            thisyaml = yaml.safe_load(yamlfile)
                            saveyaml = thisyaml
                        logger.debug('Contents of %s: %s' % (thisfn, saveyaml))
                        for k, v in saveyaml.items():
                            if k.lower() == 'network':
                                logger.debug('Found network')
                                for x, y in v.items():
                                    if x.lower() == 'ethernets':
                                        logger.debug('Found ethernets')
                                        for s, t in y.items():
                                            s1 = s
                                            logger.debug('Primary interface supposed %s' % s1)
                                            gots1 = True
                                            break
                                    else:
                                        logger.debug('Not ethernet: %s' % x)
                            else:
                                logger.debug('Not a network def: %s' % k)
                    else:
                        logger.debug('Already found primary: %s' % s1)
                    if migrate_utils.exec_rename(thisfn, os.path.split(thisfn)[0] + '/bck_' + os.path.split(fn)[1] + '_bck'):
                            logger.debug('Netplan config file %s successfully renamed to %s' % (thisfn, os.path.split(thisfn)[0] + '/bck_' + os.path.split(thisfn)[1] + '_bck'))
                    else:
                            logger.error('Failed to rename %s to %s.' % (thisfn, os.path.split(thisfn)[0] + '/bck_' + os.path.split(thisfn)[1] + '_bck'))
                except Exception as e:
                    logger.error('Error while investigating netplan configuration: %s' % str(e))
                    raise OciMigrateException('Error while investigating netplan configuration: %s' % str(e))
            else:
                logger.debug('%s is not a yaml file.' % fn)
        if gots1:
            logger.debug('Found a netplan configuration, updating %s.' % s1)
            netplan_config = data.default_netplan_config['network']['ethernets'].pop[s1]
            try:
                with open(data.default_netplan_file, 'w') as f:
                    yaml.dump(netplan_config, f, default_flow_style=False)
            except Exception as e:
                logger.error('Failed to write netplan config file %s: %s' % (data.default_netplan_file, str(e)))
        else:
            logger.debug('No network interface found in netplan config')
    else:
        logger.debug('No netplan configuration found')

    #
    # interfaces
    resval['interfaces'] = False
    intfn = data.default_interfaces
    if gen_tools.file_exists(intfn):
        logger.debug('Interfaces config file %s exists.' % intfn)
        try:
            with open(intfn, 'rb') as f:
                interfaces = f.readlines()
            for lin in interfaces:
                if 'iface' in lin.lower():
                    s0 = lin.split()[1]
                    if s0 != 'lo':
                        s1 = s0
                        gots1 = True
                        logger.debug('Found interface %s.' % s1)
                        break
                    else:
                        logger.debug('Skipping interface %s' % s0)
                else:
                    logger.debug('Skipping %s' % lin)
        except Exception as e:
            logger.error('Failed to read %s: %s' % (intfn, str(e)))
        if gots1:
            if migrate_utils.exec_rename(intfn, os.path.split(intfn)[0] + '/bck_' + os.path.split(intfn)[1] + '_bck'):
                logger.debug('Network interfaces file %s successfully renamed to %s' % (intfn, os.path.split(intfn)[0] + '/bck_' + os.path.split(intfn)[1] + '_bck'))
                try:
                    with open(intfn, 'wb') as f:
                        for ln in data.default_interfaces_file:
                            f.write(ln.replace('_XXXX_', s1))
                except Exception as e:
                    logger.error('Failed to write %s.' % intfn)
            else:
                logger.error('Failed to rename %s to %s.' % (intfn, os.path.split(intfn)[0] + '/bck_' + os.path.split(intfn)[1] + '_bck'))
        else:
            logger.debug('No network interface found in %s.' % intfn)
    else:
        logger.debug('Interfaces config file does not exist.')


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
    resval = {}
    network_list = dict()
    #
    # netplan
    resval['netplan'] = False
    npf = data.default_netplan
    gots1 = False
    if gen_tools.dir_exists(npf):
        logger.debug('Directory %s exists.' % npf)
        dircontents = os.listdir(npf)
        logger.debug('Found %s.' % dircontents)
        for fn in dircontents:
            if fn.split('.')[-1] == 'yaml':
                thisfn = npf + '/' + fn
                try:
                    if not gots1:
                        with open(thisfn, 'r') as yamlfile:
                            thisyaml = yaml.safe_load(yamlfile)
                            saveyaml = thisyaml
                            for k, v in saveyaml.items():
                                if k.lower() == 'network':
                                    for x, y in v. items():
                                        if x.lower() == 'ethernets':
                                            for s,t in y.items():
                                                resval['netplan'] = True
                                                network_list.update({s: t})
                                                logger.debug('Network interface: %s : %s' % (s, t))
                                                gen_tools.result_msg('Network interface: %s : %s' % (s, t))
                                        else:
                                            logger.debug('Skipping %s' % x)
                                else:
                                    logger.debug('Skipping %s' % k)
                except yaml.YAMLError as yex:
                    logger.error('Problem with yaml: %s' % str(yex))
                except Exception as e:
                    logger.error('Failed to handle file %s: %s' % (thisfn, str(e)))
            else:
                logger.debug('%s is not a yaml file.' % fn)
    else:
        logger.debug('Netplan directory does not exists.')
    return network_list