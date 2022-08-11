# oci-utils
#
# Copyright (c) 2019, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing migrate related operation methods.
"""
import configparser
import encodings.idna
import importlib
import logging
import os
import pkgutil
import re
import sys
import time
from urllib.request import urlopen, urlretrieve, Request

import yaml

from oci_utils.migrate import OciMigrateConfParam
from oci_utils.migrate import ProgressBar
from oci_utils.migrate import bytes_to_hex
from oci_utils.migrate import console_msg
from oci_utils.migrate import error_msg
from oci_utils.migrate import migrate_data
from oci_utils.migrate import pause_msg
from oci_utils.migrate import read_yn
from oci_utils.migrate import result_msg
from oci_utils.migrate import system_tools
from oci_utils.migrate import terminal_dimension
from oci_utils.migrate.decorators import state_loop
from oci_utils.migrate.exception import OciMigrateException

_logger = logging.getLogger('oci-utils.migrate-tools')

ConfigParser = configparser.ConfigParser


def call_os_specific_methods(os_specific_object):
    """
    Runs operating system dependent operations on the image, while in
    chroot jail.

    Parameters
    ----------
    os_specific_object: object containing the operating system specific code.

    Returns
    -------
    dict: dictionary with return values.
    """
    _logger.debug('__ Execute os specific operations.')
    os_methods = dict()
    method_returnvalues = dict()
    for method_name in dir(os_specific_object):
        attr = getattr(os_specific_object, method_name)
        if getattr(attr, "_execute_as_os_specific", False):
            _logger.debug('OS specific method: %s', attr)
            os_methods[method_name] = attr
    for method_name, method_id in sorted(os_methods.items()):
        _logger.debug("Calling: %s", method_name)
        method_return = method_id()
        method_returnvalues[method_name] = method_return
        _logger.debug('OS specific method name: %s', method_name)
    return method_returnvalues


def exec_search(file_name, rootdir='/', dirnames=False):
    """
    Find the filename in the rootdir tree.

    Parameters
    ----------
    file_name: str
        The filename to look for.
    rootdir: str
        The directory to start from, default is root.
    dirnames: bool
        If True, also consider directory names.

    Returns
    -------
        str: The full path of the filename if found, None otherwise.
    """
    _logger.debug('__ Looking for %s in %s', file_name, rootdir)
    result_msg(msg='Looking for %s in %s, might take a while.' % (file_name, rootdir))
    try:
        for path_name, directories, files in os.walk(rootdir):
            # _logger.debug('%s %s %s', path_name, directories, files)
            if file_name in files:
                _logger.debug('Found %s', os.path.join(rootdir, path_name, file_name))
                return os.path.join(rootdir, path_name, file_name)
            if dirnames and file_name in directories:
                _logger.debug('Found %s as directory.', os.path.join(rootdir, path_name, file_name))
                return os.path.join(rootdir, path_name, file_name)
    except Exception as e:
        _logger.error('  Error while looking for %s: %s', file_name, str(e))
        raise OciMigrateException('Error while looking for %s:' % file_name) from e
    return None


def find_os_specific(ostag):
    """
    Look for the os type specific code.

    Parameters
    ----------
    ostag: str
        The os type id.

    Returns
    -------
        str: The module name on success, None otherwise.
    """
    _logger.debug('__ Find module with %s.', ostag)
    module = None
    package_name = migrate_data.module_home
    _ = __import__(package_name)
    path = os.path.dirname(sys.modules.get(package_name).__file__)
    current_module = os.path.splitext(os.path.basename(sys.modules[__name__].__file__))[0]
    _logger.debug('Path: %s', path)
    _logger.debug('ostag: %s', ostag)
    # _logger.debug('This module: %s', sys.modules[__name__].__file__)
    try:
        for _, module_name, _ in pkgutil.iter_modules([path]):
            #
            # find os_type_tag in files, contains a comma separted list of
            # supported os id's
            _logger.debug('module_name: %s', module_name)
            if module_name != current_module:
                module_file = path + '/' + module_name + '.py'
                if os.path.isfile(module_file):
                    with open(module_file, 'r') as f:
                        for fline in f:
                            if '_os_type_tag_csl_tag_type_os_' in fline.strip():
                                _logger.debug('Found os_type_tag in %s.', module_name)
                                _logger.debug('In line:\n  %s', fline)
                                if ostag in re.sub("[ ']", "", fline).split('=')[1].split(','):
                                    _logger.debug('Found ostag in %s.', module_name)
                                    module = module_name
                                else:
                                    _logger.debug('ostag not found in %s.', module_name)
                                break
                else:
                    _logger.debug('No file found for module %s', module_name)
    except Exception as e:
        _logger.critical('   Failed to locate the OS type specific module: %s', str(e))
    return module


def get_cloud_agent_if_relevant(root_part, os_type, major_release):
    """
    Download oracle cloud agent for os where this cannot be achieved via
    standard install channels.
    Parameters
    ----------
    root_part: str
        The root partition of the image as currently mounted.
    os_type: str
        The os type id as set in the os-release file.
    major_release: str
        The major release info.

    Returns
    -------
        bool: always True
    """
    _logger.debug('__ Collecting the oracle_cloud_agent package if relevant.')
    _logger.debug('root partition: %s', root_part)
    _logger.debug('os type: %s' % os_type)
    _logger.debug('major release: %s', major_release)
    pause_msg('cloud agent', pause_flag='_OCI_AGENT')
    try:
        if os_type in get_config_data('ol_os_for_cloud_agent'):
            _logger.debug('OS is OL-type os.')
            el_tag = get_config_data('ol_version_id_dict')[major_release]
            _logger.debug('el tag: %s', el_tag)
            cloud_agent_url = get_url_data_from_base(el_tag)
            _logger.debug('cloud agent url: %s', cloud_agent_url)
            if cloud_agent_url is None:
                _logger.debug('URL with oracle cloud agent package not found.')
            else:
                package_name = os.path.basename(cloud_agent_url)
                destination_dir = get_config_data('ol_os_oracle_cloud_agent_store')
                destination = os.path.join(root_part, destination_dir.lstrip('/'), package_name.lstrip('/'))
                _logger.debug('Destination for oracle cloud agent package: %s', destination)
                get_file_from_url(cloud_agent_url, destination)
                migrate_data.oracle_cloud_agent_location \
                    = os.path.join('/', destination_dir.lstrip('/'), package_name.lstrip('/'))
                _logger.debug('cloud agent location: %s', migrate_data.oracle_cloud_agent_location)
        else:
            _logger.debug('This operation is not relevant here.')
            return True
    except Exception as e:
        _logger.debug('Installation of the oracle cloud agent failed: %s', str(e))

    pause_msg('cloud agent', pause_flag='_OCI_AGENT')
    return True


def get_config_data(key):
    """
    Get a configuration definition.

    Parameters:
    ----------
    key: str
        Key from the configuration data if not None, full configuration
        otherwise.

    Return:
       The configuration data.
    """
    _logger.debug('__ Get config data: %s', key)
    try:
        with OciMigrateConfParam(migrate_data.oci_migrate_conf_file, key) as config:
            return config.get_values()
    except FileNotFoundError as fnf:
        _logger.debug('File %s not found: %s, using data structure.', migrate_data.oci_migrate_conf_file, str(fnf))
        if key in migrate_data.oci_image_migrate_config:
            return migrate_data.oci_image_migrate_config[key]

        raise Exception('Failed to get data for %s: does not exist')
    except Exception as e:
        raise OciMigrateException('Failed to get data for %s:' % key) from e


def get_file_from_url(url, dest):
    """
    Download file from the internet specified by url and store in destination.
    Parameters
    ----------
    url: str
        The url.
    dest: str
        The full path of the destination.

    Returns
    -------
        str: the full path of the destination on success, raises an exception
             otherwise.
    """
    _logger.debug('__ Get file from url %s.', url)
    _, nbcols = terminal_dimension()
    packname = os.path.basename(url)
    try:
        downloadwait = ProgressBar(nbcols, 0.2, progress_chars=['pulling oracle-cloud-agent'])
        downloadwait.start()
        _ = urlretrieve(url, dest)
    except Exception as e:
        _logger.warning('Failed to retrieve %s int %s: %s', url, dest, str(e))
        raise ('Failed to retrieve %s int %s: %s' % (url, dest, str(e)))
    finally:
        if system_tools.is_thread_running(downloadwait):
            downloadwait.stop()


def get_magic_data(image):
    """
    Collect the magic number of the image file.

    Parameters
    ----------
    image: str
        Full path of the image file.

    Returns
    -------
        str: Magic string on success, None otherwise.
    """
    _logger.debug('__ Get magic data from %s.', image)
    magic_hex = None
    try:
        with open(image, 'rb') as f:
            magic = f.read(4)
            magic_hex = bytes_to_hex(magic)
            _logger.debug('Image magic number: %8s', magic_hex)
    except Exception as e:
        _logger.critical('   Image %s is not accessible: 0X%s', image, str(e))
    return magic_hex


def get_oci_config(section='DEFAULT'):
    """
    Read the oci configuration file.

    Parameters
    ----------
    section: str
        The section from the oci configuration file. DEFAULT is the default.
        (todo: add command line option to use other user/sections)

    Returns
    -------
        dict: the contents of the configuration file as a dictionary.
    """
    _logger.debug('__ Reading the %s configuration file.', get_config_data('ociconfigfile'))
    oci_config_file = get_config_data('ociconfigfile')
    _logger.debug('oci config file path: %s', oci_config_file)
    if oci_config_file.startswith('~/'):
        oci_config_file = os.path.expanduser('~') + oci_config_file[1:]
        _logger.debug('oci config file expected at %s', oci_config_file)
    oci_cli_configer = ConfigParser()
    try:
        _ = oci_cli_configer.read(oci_config_file)
        sectiondata = dict(oci_cli_configer.items(section))
        _logger.debug('OCI configuration: %s', sectiondata)
        return sectiondata
    except Exception as e:
        _logger.error('  Failed to read OCI configuration %s: %s.', get_config_data('ociconfigfile'), str(e))
        raise OciMigrateException('Failed to read OCI configuration %s:' % (get_config_data('ociconfigfile'))) from e


def get_url_data_from_base(el_tag):
    """
    Try to get the oracle cloud agent rpm location from base info.

    Parameters
    ----------
        el_tag: str
            The el release.
    Returns
    -------
        str: The url on success, None otherwise.
    """
    _logger.debug('__ Get url from base.')
    agent_url = None
    try:
        base_url = get_config_data('ol_os_oracle_cloud_agent_base')
        latest_url = get_config_data('ol_os_oracle_cloud_agent')[el_tag]
        _logger.debug('Checking %s', latest_url)
        detail_url = re.sub(r"\s", "", read_from_url(latest_url).decode('utf-8'))
        _logger.debug('URL with latest oracle cloud agent: %s', detail_url)
        agent_url = base_url + detail_url
        _logger.debug('Full url: %s', agent_url)
    except Exception as e:
        _logger.warning('Failed to locate %s: %s', agent_url, str(e))
    return agent_url


def import_formats():
    """
    Loop through the module oci_utils.migrate, import modules which
    handle different image formats and construct the
    format data dictionary. Check the object definitions for the
    'format_data' attribute.

    Returns
    -------
        dict: Dictionary containing for each image format at least:
              { magic number : { name : <type name>,
                                 module : <module name>,
                                 clazz : <the class name>,
                                 prereq : <prequisites dictionary>
                                }
              }
    """
    _logger.debug('__ Importing image formats.')
    attr_format = 'format_data'
    imagetypes = dict()
    packagename = 'oci_utils.migrate.image_types'
    pkg = __import__(packagename)
    _logger.debug('pkg name: %s', pkg)
    path = os.path.dirname(sys.modules.get(packagename).__file__)
    _logger.debug('path: %s', path)
    #
    # loop through modules in path, look for the attribute 'format_data' which
    # defines the basics of the image type, i.e. the magic number, the name and
    # essentially the class name and eventually prequisites.
    for _, module_name, _ in pkgutil.iter_modules([path]):
        type_name = packagename + '.' + module_name
        _logger.debug('type_name: %s', type_name)
        try:
            impret = importlib.import_module(type_name)
            _logger.debug('import result: %s', impret)
            attrret = getattr(sys.modules[type_name], attr_format)
            _logger.debug('attribute format_data found: %s', attrret)
            for key in attrret:
                if key != get_config_data('dummy_format_key'):
                    imagetypes.update(attrret)
                else:
                    _logger.debug('%s is the dummy key, skipping.', key)
        except Exception as e:
            _logger.debug('attribute %s not found in %s: %s', attr_format, type_name, str(e))
    return imagetypes


@state_loop(3)
def mount_imgfn(imgname):
    """
    Link vm image with an nbd device.

    Parameters
    ----------
    imgname: str
        Full path of the image file.

    Returns
    -------
        str: Device name on success, raises an exception otherwise.
    """
    #
    # create nbd devices
    _logger.debug('__ Running mount image file %s.', imgname)
    result_msg(msg='Load nbd')
    if not system_tools.create_nbd():
        raise OciMigrateException('Failed ot load nbd module')

    _logger.debug('nbd module loaded')
    #
    # find free nbd device
    result_msg(msg='Find free nbd device')
    devpath = system_tools.get_free_nbd()
    _logger.debug('Device %s is free.', devpath)
    #
    # link img with first free nbd device
    result_msg(msg='Mount image %s' % imgname, result=True)
    _, nbcols = terminal_dimension()
    try:
        mountwait = ProgressBar(nbcols, 0.2, progress_chars=['mounting image'])
        mountwait.start()
        qemucmd = ['-c', devpath, imgname]
        pause_msg(qemucmd, pause_flag='_OCI_MOUNT')
        qemunbd_ret = system_tools.exec_qemunbd(qemucmd)
        if qemunbd_ret == 0:
            time.sleep(5)
            _logger.debug('qemu-nbd %s succeeded', qemucmd)
            return devpath

        _logger.critical('\n   Failed to create nbd devices: %d', qemunbd_ret)
        raise Exception('Failed to create nbd devices: %d' % qemunbd_ret)
    except Exception as e:
        _logger.critical('\n   Something wrong with creating nbd devices: %s', str(e))
        raise OciMigrateException('Unable to create nbd devices:') from e
    finally:
        if system_tools.is_thread_running(mountwait):
            mountwait.stop()


@state_loop(2)
def mount_lvm2(devname):
    """
    Create the mountpoints /mnt/<last part of lvm partitions> and mount the
    partitions on those mountpoints, if possible.

    Parameters
    ----------
    devname: str
        The full path of the device

    Returns
    -------
        list: The list of mounted partitions.
        ?? need to collect lvm2 list this way??
    """
    _logger.debug('__ Running mount lvm2 %s', devname)
    try:
        _, nbcols = terminal_dimension()
        mountwait = ProgressBar(int(nbcols), 0.2, progress_chars=['mounting lvm'])
        mountwait.start()
        #
        # physical volumes
        if system_tools.exec_pvscan(['--cache'], devname):
            _logger.debug('pvscan %s succeeded', devname)
        else:
            _logger.critical('   pvscan %s failed', devname)
        #
        pause_msg('pvscan test', pause_flag='_OCI_LVM')
        #
        # volume groups
        if system_tools.exec_vgscan(['--verbose']):
            _logger.debug('vgscan succeeded')
        else:
            _logger.critical('   vgscan failed')
        #
        pause_msg('vgscan test', pause_flag='_OCI_LVM')
        #
        # logical volumes
        vgs = new_volume_groups()
        if bool(vgs):
            _logger.debug('lvscan succeeded: %s', vgs)
        else:
            _logger.critical('   lvscan failed')
            raise OciMigrateException('Logical volume scan failed.')
        #
        pause_msg('lvscan test', pause_flag='_OCI_LVM')
        #
        # make available
        vgchange_args = ['--activate', 'y']
        vgchange_res = system_tools.exec_vgchange(vgchange_args)
        _logger.debug('vgchange:\n%s', vgchange_res)
        #
        pause_msg('vgchange_res test', pause_flag='_OCI_LVM')
        vgfound = False
        if vgchange_res is not None:
            for resline in vgchange_res.splitlines():
                _logger.debug('vgchange line: %s', resline)
                for vg in list(vgs.keys()):
                    if vg in resline:
                        _logger.debug('vgfound set to True')
                        vgfound = True
                    else:
                        _logger.debug('vg %s not in l', vg)
            _logger.debug('vgchange: %s found: %s', vgchange_res, vgfound)
            #
            # for the sake of testing
            pause_msg('vgchange_res test', pause_flag='_OCI_LVM')
        else:
            _logger.critical('   vgchange failed')
        return vgs
    except Exception as e:
        _logger.critical('   Mount lvm %s failed: %s', devname, str(e))
        raise OciMigrateException('Mount lvm %s failed: %s' % devname) from e
    finally:
        if system_tools.is_thread_running(mountwait):
            mountwait.stop()


@state_loop(3)
def mount_partition(devname, mountpoint=None):
    """
    Create the mountpoint /mnt/<last part of device specification> and mount a
    partition on on this mountpoint.

    Parameters
    ----------
    devname: str
        The full path of the device.
    mountpoint: str
        The mountpoint, will be generated if not provided.

    Returns
    -------
        str: The mounted partition on Success, None otherwise.
    """
    _logger.debug('__ Mount partition %s.', devname)
    #
    # create mountpoint /mnt/<devname> if not specified.
    if mountpoint is None:
        mntpoint = migrate_data.loopback_root + '/' + devname.rsplit('/')[-1]
        _logger.debug('Loopback mountpoint: %s', mntpoint)
        try:
            if system_tools.exec_mkdir(mntpoint):
                _logger.debug('Mountpoint: %s created.', mntpoint)
        except Exception as e:
            _logger.critical('   Failed to create mountpoint %s: %s', mntpoint, str(e))
            raise OciMigrateException('Failed to create mountpoint %s:' % mntpoint) from e
    else:
        mntpoint = mountpoint
    #
    # actual mount
    cmd = ['mount', devname, mntpoint]
    pause_msg(cmd, pause_flag='_OCI_MOUNT')
    _, nbcols = terminal_dimension()
    try:
        mountpart = ProgressBar(nbcols, 0.2, progress_chars=['mount %s' % devname])
        mountpart.start()
        _logger.debug('command: %s', cmd)
        cmdret = system_tools.run_call_cmd(cmd)
        if cmdret == 0:
            _logger.debug('%s mounted on %s.', devname, mntpoint)
            return mntpoint

        raise Exception('Mount %s failed: %d' % (devname, cmdret))
    except Exception as e:
        #
        # mount failed, need to remove mountpoint.
        _logger.critical('   Failed to mount %s, missing driver, filesystem corruption...: %s', devname, str(e))
        _logger.critical('   Check file system driver and kernel version compatibility. '
                         'Check Known Issues in the man page and manual.')
        if mountpoint is None:
            if system_tools.exec_rmdir(mntpoint):
                _logger.debug('%s removed', mntpoint)
            else:
                _logger.critical('   Failed to remove mountpoint %s', mntpoint)
    finally:
        if system_tools.is_thread_running(mountpart):
            mountpart.stop()

    return None


def new_volume_groups():
    """
    Scan the system for (new) logical volumes.

    Returns
    -------
        dict:  inactive, supposed new, volume groups with list of logical
        volumes on success, raises an exception on failure.
    """
    def is_workstation_volume_group(vg2test):
        """
        Verify if vg2test is a logical volume on the workstation.

        Parameters
        ----------
            vg2test: str
                volume group name.

        Returns
        -------
            bool: True if local volume group, False otherwise.
        """
        _logger.debug('__ Test if volume group %s is local', vg2test)
        _logger.debug('Local volume groups: %s', migrate_data.local_volume_groups)
        for vg_names in migrate_data.local_volume_groups:
            # _logger.debug('types    vgdev %s vg_names_1 %s', type(vgdev), type(vg_names[1]))
            _logger.debug('contents vgdev +%s+ vg_names_1 +%s+', vgdev, vg_names[1])
            if vgdev == vg_names[1]:
                # _logger.error('match')
                return True
        return False

    _logger.debug('__ Looking for logical volumes in image file.')
    lv_list = system_tools.exec_lvscan(['--verbose'])
    _logger.debug('Logical volumes scanned:\n%s', lv_list)
    _logger.debug('Local volume groups: %s', migrate_data.local_volume_groups)
    new_vgs = dict()
    for lvdevdesc in lv_list:
        lvarr = re.sub(r"'", "", lvdevdesc).split()
        lvdev = lvarr[1]
        vgarr = re.sub(r"/", " ", lvdev).split()
        vgdev = vgarr[1]
        lvdev = vgarr[2]
        mapperdev = re.sub(r"-", "--", vgdev) + '-' + re.sub(r"-", "--", lvdev)
        _logger.debug('vg: %s lv: %s mapper: %s', vgdev, lvdev, mapperdev)
        #
        # verify if volume group is an image or workstation volume group.
        if not is_workstation_volume_group(vgdev):
            if vgdev not in list(new_vgs.keys()):
                # new volume group
                new_vgs[vgdev] = [(lvdev, mapperdev)]
            else:
                # existing volume group, new logical volume
                new_vgs[vgdev].append((lvdev, mapperdev))
            _logger.debug('vg: %s lv: %s added', vgdev, lvdev)
        _logger.debug('New logical volumes: %s', new_vgs)
    return new_vgs


def print_header(head):
    """
    Display header for image data component.

    Parameters
    ----------
    head: str
        The header

    Returns
    -------
        No return value.
    """
    result_msg(msg='\n  %30s\n  %30s' % (head, '-'*30), result=True)


def read_from_url(url):
    """
    Read from an url

    Parameters
    ----------
    url: str
        The url.

    Returns
    -------
        obj: the contents of the url on success, raises an exception otherwise.
    """
    _logger.debug('__ Read from url %s.', url)
    #
    # to keep the encodings import in place
    _ = dir(encodings.idna)
    try:
        url_request = Request(url=url, headers={'Authorization': 'Bearer Oracle'})
        with urlopen(url_request) as url_ref:
            if url_ref.status != 200:
                raise Exception('url get status: %s while looking for %s' % (str(url_ref.status), url))
            url_contents = url_ref.read()
        return url_contents
    except Exception as e:
        _logger.warning('Failed to read from %s: %s', url, str(e))
        raise OciMigrateException('Failed to read from %s' % url) from e


def set_default_user(cfgfile, username):
    """
    Update the default user name in the cloud.cfg file.
    Paramaters:
    ----------
        cfgfile: str
            full path of the cloud init config file, yaml format.
        username: str
            name of the default cloud user.

    Returns:
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('__ Updating cloud.cfg file %s, setting default username to %s.', cfgfile, username)
    if os.path.isfile(cfgfile):
        bck_cfgfile = system_tools.backup_file(cfgfile)
        _logger.debug('Copied %s to %s', cfgfile, bck_cfgfile)
        with open(cfgfile, 'r') as f:
            cloudcfg = yaml.load(f, Loader=yaml.SafeLoader)
        if isinstance(cloudcfg, dict):
            if 'system_info' in list(cloudcfg.keys()) \
                    and 'default_user' in list(cloudcfg['system_info'].keys()) \
                    and 'name' in list(cloudcfg['system_info']['default_user'].keys()):
                cloudcfg['system_info']['default_user']['name'] = username
                with open(cfgfile, 'w') as f:
                    yaml.dump(cloudcfg, f, width=50)
                _logger.debug('Cloud configuration file %s successfully updated.', cfgfile)
                return True

            _logger.debug('No default username found in cloud config file.')
        else:
            _logger.error('  Invalid cloud config file.')
    else:
        _logger.error('  Cloud config file %s does not exist.', cfgfile)
    return False


def show_default_kernel(kernelversion):
    """
    Show the default kernel version.
    Parameters
    ----------
    kernelversion: str
        The version of the kernel booted by default.

    Returns
    -------
        No return value.
    """
    result_msg(msg='\n  Default kernel: %s' % kernelversion, result=True)


def show_fstab(fstabdata):
    """
    Show the relevant data in the fstab file.

    Parameters
    ----------
    fstabdata: list of lists, one list per fstab line.

    Returns
    -------
        No return value.
    """
    for line in fstabdata:
        result_msg(msg='%60s %20s %8s %20s %2s %2s' % (line[0], line[1], line[2], line[3], line[4], line[5]), result=True)


def show_grub_data(grublist):
    """
    Show the relevant data in the grub config file.

    Parameters
    ----------
    grublist: list of dictionaries, 1 per boot section, containing grub
    lines as list.

    Returns
    -------
        No return value.
    """
    for entry in grublist:
        _logger.debug('%s', entry)
        for grubkey in entry:
            for grubline in entry[grubkey]:
                result_msg(msg=grubline, result=True)
            result_msg(msg='\n', result=True)


def show_image_data(imgobj):
    """
    Show the collected data about the image.

    Parameters
    ----------
    imgobj: object
        The data about the image.

    Returns
    -------
        No return value.
    """
    print_header('Components collected.')
    for k, _ in sorted(imgobj.image_info.items()):
        result_msg(msg='  %30s' % k, result=True)

    _logger.debug('show data')
    print('\n  %25s\n  %s' % ('Image data:', '-'*60))
    #
    # name
    fnname = '  missing'
    print_header('Image file path.')
    if 'img_name' in imgobj.image_info:
        fnname = imgobj.image_info['img_name']
    result_msg(msg='  %30s' % fnname, result=True)
    #
    # type
    imgtype = '  missing'
    print_header('Image type.')
    if 'img_type' in imgobj.image_info:
        imgtype = imgobj.image_info['img_type']
    result_msg(msg='  %30s' % imgtype, result=True)
    #
    # size
    imgsizes = '    physical: missing data\n    logical:  missing data'
    print_header('Image size:')
    if 'img_size' in imgobj.image_info:
        imgsizes = '    physical: %8.2f GB\n      logical:  %8.2f GB' \
                   % (imgobj.image_info['img_size']['physical'],
                      imgobj.image_info['img_size']['logical'])
    result_msg(msg='%s' % imgsizes, result=True)
    #
    # header
    if 'img_header' in imgobj.image_info:
        try:
            imgobj.show_header()
        except Exception as e:
            result_msg(msg='Failed to show the image hadear: %s' % str(e), result=True)
    else:
        result_msg(msg='\n  Image header data missing.', result=True)
    #
    # mbr
    mbr = '  missing'
    print_header('Master Boot Record.')
    if 'mbr' in imgobj.image_info:
        if 'hex' in imgobj.image_info['mbr']:
            mbr = imgobj.image_info['mbr']['hex']
        result_msg(msg='%s' % mbr, result=True)
    #
    # partition table
        print_header('Partiton Table.')
        parttabmissing = '  Partition table data is missing.'
        if 'partition_table' in imgobj.image_info['mbr']:
            show_partition_table(imgobj.image_info['mbr']['partition_table'])
        else:
            result_msg(msg=parttabmissing, result=True)
    #
    # parted data
    print_header('Parted data.')
    parteddata = '  Parted data is missing.'
    if 'parted' in imgobj.image_info:
        show_parted_data(imgobj.image_info['parted'])
    else:
        result_msg(msg='%s' % parteddata, result=True)
    #
    # partition data
    print_header('Partition Data.')
    partdata = '  Partition data is missing.'
    if 'partitions' in imgobj.image_info:
        show_partition_data(imgobj.image_info['partitions'])
    else:
        result_msg(msg='%s' % partdata, result=True)
    #
    # grub config data
    print_header('Grub configuration data.')
    grubdat = '  Grub configuration data is missing.'
    if 'grubdata' in imgobj.image_info:
        show_grub_data(imgobj.image_info['grubdata'])
    else:
        result_msg(msg='%s' % grubdat, result=True)
    #
    # kernel versions
    print_header('Default kernel version.')
    kerneldefdat = '   Default kernel data not found or is missing.'
    if 'kernelversion' in imgobj.image_info:
        show_default_kernel(imgobj.image_info['kernelversion'])
    else:
        result_msg(msg='%s' % kerneldefdat, result=True)
    print_header('Installed kernels.')
    kernellisdat = '   List of kernels is missing.'
    if 'kernellist' in imgobj.image_info:
        show_kernel_list(imgobj.image_info['kernellist'])
    else:
        result_msg(msg='%s' % kernellisdat, result=True)
    #
    # logical volume data
    print_header('Logical Volume data.')
    lvmdata = '  Logical Volume data is missing.'
    if 'volume_groups' in imgobj.image_info:
        if imgobj.image_info['volume_groups']:
            show_lvm2_data(imgobj.image_info['volume_groups'])
    else:
        result_msg(msg=lvmdata, result=True)
    #
    # various data:
    print_header('Various data.')
    if 'bootmnt' in imgobj.image_info:
        result_msg(msg='  %30s: %s mounted on %s'
                       % ('boot', imgobj.image_info['bootmnt'][0], imgobj.image_info['bootmnt'][1]), result=True)
    if 'rootmnt' in imgobj.image_info:
        result_msg(msg='  %30s: %s mounted on %s'
                       % ('root', imgobj.image_info['rootmnt'][0], imgobj.image_info['rootmnt'][1]), result=True)
    if 'boot_type' in imgobj.image_info:
        result_msg(msg='  %30s: %-30s' % ('boot type:', imgobj.image_info['boot_type']), result=True)
    #
    # fstab
    print_header('fstab data.')
    fstabmiss = '  fstab data is missing.'
    if 'fstab' in imgobj.image_info:
        show_fstab(imgobj.image_info['fstab'])
    else:
        result_msg(msg=fstabmiss, result=True)
    #
    # os release data
    print_header('Operating System information.')
    osinfomissing = '  Operation System information is missing.'
    if 'osinformation' in imgobj.image_info:
        for k in sorted(imgobj.image_info['osinformation']):
            result_msg(msg='  %35s : %-30s' % (k, imgobj.image_info['osinformation'][k]), result=True)
    else:
        result_msg(msg=osinfomissing, result=True)


def show_img_header(headerdata):
    """
    Show the header data.

    Parameters
    ----------
    headerdata: dict
        Dictionary containing data extracted from the image header; contents
        is dependent form image type.

    Returns
    -------
        No return value.
    """
    result_msg(msg='\n  %30s\n  %30s' % ('Image header:', '-'*30), result=True)
    for k, v in sorted(headerdata):
        result_msg(msg='  %30s : %s' % (k, v), result=True)


def show_kernel_list(kernels):
    """
    Show the kernels defined in the grub config file.
    Parameters
    ----------
    kernels: list
        List of kernels defined in the grub config file.

    Returns
    -------
        No return value.
    """
    for kver in sorted(kernels):
        result_msg(msg='   %s' % kver, result=True)


def show_lvm2_data(lvm2_data):
    """
    Show the collected lvm2 data.

    Parameters
    ----------
    lvm2_data: dict
        Dictionary containing the recognised volume groups and logical volumes.

    Returns
    -------
        No return value.
    """
    for k, v in sorted(lvm2_data.items()):
        result_msg(msg='\n  Volume Group: %s:' % k, result=True)
        for t in v:
            result_msg(msg='%40s : %-30s' % (t[0], t[1]), result=True)
    result_msg(msg='\n', result=True)


def show_network_data(networkdata):
    """
    Show the collected data on the network interfaces.

    Parameters
    ----------
    networkdata: dict
        Dictionary of dictionaries containing the network configuration data.

    Returns
    -------
        No return value.
    """
    for nic, nicdata in sorted(networkdata.items()):
        result_msg(msg='  %20s:' % nic, result=True)
        for k, v in sorted(nicdata.items()):
            result_msg(msg='  %30s = %s' % (k, v), result=True)


def show_parted_data(parted_dict):
    """
    Show the data collected by the parted command.

    Parameters
    ----------
    parted_dict: dict
        The data.

    Returns
    -------
        No return value.
    """
    for k, v in sorted(parted_dict.items()):
        if k == 'Partition List':
            result_msg(msg='%30s :' % k, result=True)
            for part in v:
                result_msg(msg='%30s : %s' % (' ', ' '.join(part)), result=True)
        else:
            result_msg(msg='%30s : %s' % (k, v), result=True)
    result_msg(msg='\n', result=True)


def show_partition_data(partition_dict):
    """
    Show the collected data on the partitions of the image file.

    Parameters
    ----------
    partition_dict: dict
        The data.

    Returns
    -------
        No return value
    """
    for k, v in sorted(partition_dict.items()):
        result_msg(msg='%30s :\n%s' % ('partition %s' % k, '-'*60), result=True)
        for x, y in sorted(v.items()):
            result_msg(msg='%30s : %s' % (x, y), result=True)
        result_msg(msg='\n', result=True)
    result_msg(msg='\n', result=True)


def show_partition_table(table):
    """
    Show the relevant data of the partition table.

    Parameters
    ----------
    table: list of dict.
        The partition table data.

    Returns
    -------
        No return value.
    """
    result_msg(msg='  %2s %5s %16s %32s' % ('nb', 'boot', 'type', 'data'), result=True)
    result_msg(msg='  %2s %5s %16s %32s' % ('-'*2, '-'*5, '-'*16, '-'*32), result=True)
    for i in range(0, 4):
        if table[i]['boot']:
            bootflag = 'YES'
        else:
            bootflag = ' NO'
        result_msg(msg='  %02d %5s %16s %32s' % (i, bootflag, table[i]['type'], table[i]['entry']), result=True)


@state_loop(3)
def unmount_imgfn(devname):
    """
    Unlink a device.

    Parameters
    ----------
    devname: str
        The device name

    Returns
    -------
        bool: True on succes, raise an exception otherwise.
    """
    _logger.debug('__ Unmount %s', devname)
    try:
        #
        # release device
        qemucmd = ['-d', devname]
        pause_msg(qemucmd, pause_flag='_OCI_MOUNT')
        qemunbd_ret = system_tools.exec_qemunbd(qemucmd)
        if qemunbd_ret == 0:
            _logger.debug('qemu-nbd %s succeeded: %d', qemucmd, qemunbd_ret)
        else:
            raise Exception('%s returned %d' % (qemucmd, qemunbd_ret))
        #
        # clear lvm cache, if necessary.
        if system_tools.exec_pvscan(['--cache']):
            _logger.debug('lvm cache updated')
        else:
            _logger.error('  Failed to clear LVM cache.')
            raise OciMigrateException('Failed to clear LVM cache.')
        #
        # remove nbd module
        if not system_tools.rm_nbd():
            raise OciMigrateException('Failed to remove nbd module.')

        _logger.debug('Successfully removed nbd module.')
    except Exception as e:
        _logger.critical('   Something wrong with removing nbd devices: %s', str(e))
        raise OciMigrateException('\nSomething wrong with removing nbd devices:') from e
    return True


def unmount_lvm2(vg):
    """
    Remove logical volume data from system.

    Parameters
    ----------
    vg: dict
        Volume group with list of logical volumes.

    Returns
    -------
        bool: True on Success, exception otherwise.
    """
    _logger.debug('__ Remove %s from system.', vg)
    try:
        #
        # make unavailable
        for vg_name in list(vg.keys()):
            vgchange_args = ['--activate', 'n', vg_name]
            vgchange_res = system_tools.exec_vgchange(vgchange_args)
            _logger.debug('vgchange: %s', vgchange_res)
        #
        # remove physical volume: clear cache, if necessary
        if system_tools.exec_pvscan(['--cache']):
            _logger.debug('pvscan clear succeeded')
        else:
            _logger.error('  pvscan failed')
    except Exception as e:
        _logger.error('  Failed to release lvms %s: %s', vg, str(e))
        error_msg('Failed to release lvms %s: %s' % (vg, str(e)))
        # raise OciMigrateException('Exception raised during release
        # lvms %s: %s' % (vg, str(e)))


@state_loop(5, 2)
def unmount_part(devname):
    """
    Unmount a partition from mountpoint from /mnt/<last part of device
    specification> and remove the mountpoint.

    Parameters
    ----------
    devname: str
        The full path of the device.

    Returns
    -------
        bool
            True on success, False otherwise.
    """
    mntpoint = migrate_data.loopback_root + '/' + devname.rsplit('/')[-1]
    cmd = ['umount', mntpoint]
    _logger.debug('__ Running %s', cmd)
    pause_msg(cmd, pause_flag='_OCI_MOUNT')
    while True:
        try:
            _logger.debug('command: %s', cmd)
            cmdret = system_tools.run_call_cmd(cmd)
            if cmdret == 0:
                _logger.debug('%s unmounted from %s', devname, mntpoint)
                #
                # remove mountpoint
                if system_tools.exec_rmdir(mntpoint):
                    _logger.debug('%s removed', mntpoint)
                    return True
                _logger.critical('   Failed to remove mountpoint %s', mntpoint)
                raise OciMigrateException('Failed to remove mountpoint %s' % mntpoint)

            _logger.critical('   Failed to unmount %s: %d', devname, cmdret)
            console_msg('Failed to unmount %s, error code %d.\n Please verify before continuing.' % (devname, cmdret))
            retry = read_yn('Something prevented to complete %s, please verify and correct if possible. '
                            'Press Y to retry, N to ignore.', waitenter=True)
            if not retry:
                break
        except Exception as e:
            _logger.critical('   Failed to unmount %s: %s', devname, str(e))
    return False


def update_cloudconfig_runcmd(runcommand):
    """
    Update the cloud.cfg file with runcmd command, to be executed at first
    boot.

    Parameters
    ----------
    runcommand: str
        full command to be executed.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('__ Update cloud config file with %s.', runcommand)
    #
    # cloud config file.
    try:
        cloudconfig = get_config_data('cloudconfig_file')
        _logger.debug('cloud.cfg file %s.', cloudconfig)
    except Exception as e:
        _logger.error('Failed to find cloud config file location: %s.', str(e))
        return False
    #
    # update runcmd
    if os.path.isfile(cloudconfig):
        #
        # read cloud config file
        with open(cloudconfig, 'r') as f:
            cloudcfg = yaml.load(f, Loader=yaml.SafeLoader)
        #
        #
        runcmd_definition = False
        if isinstance(cloudcfg, dict):
            if 'runcmd' in list(cloudcfg.keys()):
                #
                # runcmd present in cloud config file
                run_cmd = cloudcfg['runcmd']
                for yaml_key in run_cmd:
                    if isinstance(yaml_key, list):
                        for yamlval in yaml_key:
                            if runcommand in yamlval:
                                _logger.debug('%s already in cloud_init', runcommand)
                                runcmd_definition = True
                                break
                    else:
                        #
                        # is string
                        if runcommand in yaml_key:
                            _logger.debug('%s already in cloud_init', runcommand)
                            runcmd_definition = True
                            break
                if not runcmd_definition:
                    #
                    # the runcommand not yet defined in runcmd
                    run_cmd.append(runcommand)
            else:
                #
                # runcmd not yet present in cloud config file
                cloudcfg['runcmd'] = [runcommand]

            with open(cloudconfig, 'w') as f:
                yaml.dump(cloudcfg, f, width=50)
                _logger.debug('Cloud configuration file %s successfully updated.', cloudconfig)
            return True
        else:
            _logger.error('Invalid cloud config file.')
    else:
        _logger.error('Cloud config file %s does not exist.', cloudconfig)
        return False


def verify_local_fstab():
    """
    Verify if fstab file contains entries using /dev/mapper, which could cause
    an issue with logical volumes on the image file under investigation.

    Returns
    -------
        bool: True if /dev/mapper entries are foune, False otherwise.
    """
    _logger.debug('__ Running local fstab check.')
    fstab_file = '/etc/fstab'
    try:
        with open(fstab_file, 'r') as fstab:
            for fstab_line in fstab:
                if '/dev/mapper' in fstab_line.split('#', 1)[0]:
                    _logger.debug('Found a line in fstab:\n%s', fstab_line)
                    return True
    except Exception as e:
        _logger.debug("Failed to verify local fstab file: %s", str(e))
        return True
    return False
