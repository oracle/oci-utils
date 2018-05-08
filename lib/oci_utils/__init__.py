#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2017, 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

import os
import os.path
import sys
import io
import logging
import urllib2
import subprocess
import threading
import json
from datetime import datetime, timedelta
from time import sleep
from ConfigParser import ConfigParser
from .packages.stun import get_ip_info, log as stun_log
from .exceptions import OCISDKError
from cache import GLOBAL_CACHE_DIR
import oci_utils.oci_api

# file with a list IQNs to ignore
__ignore_file = "/var/lib/oci-utils/ignore_iqns"
# file with chap user names and passwords
__chap_password_file = "/var/lib/oci-utils/chap_secrets"

# endpoint of the metadata service
METADATA_ENDPOINT = '169.254.169.254'

# oci-utils configuration defaults
__oci_utils_defaults = """
[auth]
auth_method = auto
oci_sdk_user = opc
[iscsi]
enabled = true
scan_interval = 60
[vnic]
enabled = true
scan_interval = 60
vf_net = false
[public_ip]
enabled = true
refresh_interval = 600
"""

# oci-utils config file
__oci_utils_conf_d = "/etc/oci-utils.conf.d"
oci_utils_config = None

oci_utils_thread_lock = None
def lock_thread(timeout=30):
    global oci_utils_thread_lock

    # the oci sdk is not thread safe, so need to synchronize sdk calls
    # each sdk call must call OCISession.lock() first and call
    # OCISession.release() when done.
    if oci_utils_thread_lock is None:
        oci_utils_thread_lock = threading.Lock()

    if timeout > 0:
        max_time = datetime.now() + timedelta(seconds=timeout)
        while True:
            # non-blocking
            if oci_utils_thread_lock.acquire(False):
                break
            if max_time < datetime.now():
                raise OCISDKError("Timed out waiting for API thread lock")
            else:
                sleep(0.1)
    else:
        # blocking
        oci_utils_thread_lock.acquire(True)

def release_thread():
    global oci_utils_thread_lock
    oci_utils_thread_lock.release()

def set_proxy():
    # metadata service (and instance principal auth) won't work through
    # a proxy
    global oci_utils_config
    if 'NO_PROXY' in os.environ:
        os.environ['NO_PROXY'] += ',%s' % METADATA_ENDPOINT
    else:
        os.environ['NO_PROXY'] = METADATA_ENDPOINT

    # check if there are proxy settings in the config files
    if oci_utils_config is None:
        oci_utils_config = read_config()
    try:
        proxy = oci_utils_config.get('network', 'http_proxy')
        os.environ['http_proxy'] = proxy
    except:
        pass

    try:
        proxy = oci_utils_config.get('network', 'https_proxy')
        os.environ['https_proxy'] = proxy
    except:
        pass

def read_config():
    """
    read the oci-utils config file and return a ConfigParser object
    """
    global oci_utils_config
    if oci_utils_config is not None:
        return oci_utils_config
    oci_utils_config = ConfigParser()
    try:
        oci_utils_config.readfp(io.BytesIO(oci_utils.__oci_utils_defaults))
    except:
        raise

    if not os.path.exists(__oci_utils_conf_d):
        return oci_utils_config

    conffiles = [os.path.join(__oci_utils_conf_d, f)
                 for f in os.listdir(__oci_utils_conf_d)
                 if os.path.isfile(os.path.join(__oci_utils_conf_d, f))]
    oci_utils_config.read(conffiles)
    return oci_utils_config

class VNICUtils(object):
    """
    Class for managing VNICs
    """
    # file with saved vnic information
    __vnic_info_file = "/var/lib/oci-utils/vnic_info"
    # OBSOLETE: file with VNICs and stuff to exclude from automatic
    # configuration
    __net_exclude_file = "/var/lib/oci-utils/net_exclude"
    
    def __init__(self, debug=False, logger=None):
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger('oci-metadata')
            handler = logging.StreamHandler()
            handler.setLevel(logging.DEBUG)
            self.logger.addHandler(handler)

        if debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

        self.vnic_info = None
        self.vnic_info_ts = 0
        self.config = read_config()

    @staticmethod
    def __new_vnic_info():
        vnic_info = {
            'ns': None,
            'sshd': False,
            'exclude': [],
            'sec_priv_ip': []
        }
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
            except:
                pass

        # can we make API calls?
        oci_sess = None
        if oci_utils.oci_api.HAVE_OCI_SDK:
            try:
                oci_sess = oci_utils.oci_api.OCISession()
            except:
                pass
        if oci_sess is not None:
            p_ips = oci_sess.this_instance().all_private_ips(refresh=True)
            sec_priv_ip = \
                [[ip.get_address(),ip.get_vnic_ocid()] for ip in p_ips]
            vnic_info['sec_priv_ip']=sec_priv_ip
            vnic_info_ts = \
                cache.write_cache(cache_content=vnic_info,
                                  cache_fname=VNICUtils.__vnic_info_file)
        return (vnic_info_ts, vnic_info)

    @staticmethod
    def get_vnic_info_timestamp():
        return cache.get_timestamp(VNICUtils.__vnic_info_file)

    def get_vnic_info(self):
        """
        Load the vnic_info file or create a new one if there isn't one
        """
        self.vnic_info_ts, self.vnic_info = \
            cache.load_cache(VNICUtils.__vnic_info_file)
        if self.vnic_info is None:
            self.vnic_info_ts, self.vnic_info = VNICUtils.__new_vnic_info()

        return self.vnic_info_ts, self.vnic_info

    def save_vnic_info(self):
        """
        Save self.vnic_info in the vnic_info file.
        Return the timestamp for success, None for failure
        """
        self.logger.debug("Saving vnic_info.")
        vnic_info_ts = cache.write_cache(cache_content=self.vnic_info,
                                         cache_fname=VNICUtils.__vnic_info_file)
        if vnic_info_ts is not None:
            self.vnic_info_ts = vnic_info_ts
        else:
            self.logger.warn("Failed to save VNIC info to %s" % \
                             VNICUtils.__vnic_info_file)
        return vnic_info_ts
        
    def __run_sec_vnic_script(self, script_args):
        '''
        Run the secondary_vnic_all_configure.sh script with the given arguments
        and additional details in vnic_info, which is a dict in the format
        returned by get_vnic_info().
        '''
        TRUE = ['true', 'True', 'TRUE']
        vf_net = self.config.get('vnic', 'vf_net') in TRUE
        if vf_net and '-s' not in script_args:
            self.logger.debug('Skipping execution of the secondary vnic script')
            return (0, 'Info: vf_net is enabled in the oci-utils configuration')
        all_args = ['/usr/libexec/secondary_vnic_all_configure.sh']
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
    
        self.logger.debug('Executing "%s"' % " ".join(all_args))
        try:
            output = subprocess.check_output(all_args, stderr=subprocess.STDOUT)
        except OSError as e:
            self.logger.error('failed to execute '
                              '/usr/libexec/secondary_vnic_all_configure.sh')
            return (404, 'failed to execute secondary VNIC script')
        except subprocess.CalledProcessError as e:
            self.logger.error('Error running command "%s":' % ' '.
                              join(all_args))
            self.logger.error(e.output)
            return (e.returncode, e.output)

        return (0, output)

    def set_namespace(self, ns):
        self.vnic_info['ns'] = ns
        self.save_vnic_info()

    def set_sshd(self, val):
        self.vnic_info['sshd'] = val
        self.save_vnic_info()

    def add_private_ip(self, ipaddr, vnic_id):
        """
        Add the given secondary private IP to vnic_info and save
        vnic info to the vnic_info file
        """
        if [ipaddr,vnic_id] not in self.vnic_info['sec_priv_ip']:
            self.vnic_info['sec_priv_ip'].append([ipaddr,vnic_id])
        self.save_vnic_info()

    def set_private_ips(self, priv_ips):
        self.vnic_info['sec_priv_ip'] = priv_ips
        self.save_vnic_info()

    def delete_all_private_ips(self, vnic_id):
        """
        delete all private IPs attached to a given VNIC.
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
        Delete the given secondary private IP from vnic_info and save
        vnic_info to the vnic_info file.
        Run the secondary vnic script to deconfigure the secondary vnic script.
        Return the result of running the sec vnic script
        """
        if [ipaddr,vnic_id] in self.vnic_info['sec_priv_ip']:
            self.vnic_info['sec_priv_ip'].remove([ipaddr,vnic_id])
        self.include(ipaddr, save=False)
        self.save_vnic_info()
        return self.__run_sec_vnic_script(['-d', '-e', ipaddr, vnic_id])

    def exclude(self, item, save=True):
        """
        Add item to the "exclude" list.  (ip addresses or interfaces that
        are excluded from automatic configuration)
        """
        if item not in self.vnic_info['exclude']:
            self.logger.debug('Adding %s to "exclude" list' % item)
            self.vnic_info['exclude'].append(item)
            if save:
                self.save_vnic_info()

    def include(self, item, save=True):
        """
        Remove item from the "exclude" list.  (ip addresses or interfaces that
        are excluded from automatic configuration)
        """
        if item in self.vnic_info['exclude']:
            self.logger.debug('Removing %s from "exclude" list' % item)
            self.vnic_info['exclude'].remove(item)
            if save:
                self.save_vnic_info()

    def auto_config(self, sec_ip, quiet, show):
        """
        Run the secondary vnic script in automatic configuration mode (-c)
        """
        args = ['-c']
        if quiet:
            args += ['-q']
        if show:
            args += ['-s']
        if sec_ip:
            for si in sec_ip:
                args += ['-e', si[0], si[1]]
                if [si[0],si[1]] not in self.vnic_info['sec_priv_ip']:
                    self.vnic_info['sec_priv_ip'].append((si[0],si[1]))
                self.include(si[0], save=False)
                self.save_vnic_info()

        return self.__run_sec_vnic_script(args)

    def auto_deconfig(self, sec_ip, quiet, show):
        """
        Run the secondary vnic script in automatic configuration mode (-c)
        """
        args = ['-d']
        if quiet:
            args += ['-q']
        if show:
            args += ['-s']
        if sec_ip:
            for si in sec_ip:
                args += ['-e', si[0], si[1]]
                if [si[0],si[1]] in self.vnic_info['sec_priv_ip']:
                    self.vnic_info['sec_priv_ip'].remove([si[0],si[1]])
                self.exclude(si[0], save=False)
                self.save_vnic_info()
        return self.__run_sec_vnic_script(args)

    def get_network_config(self):
        """
        return the output of the secondary vnic script with the -s option
        """
        return self.__run_sec_vnic_script(['-s'])

class OCIMetadata(dict):
    """
    a class representing all OCI metadata
    """
    _metadata = None

    def __init__(self, metadata):
        assert type(metadata) is dict, "metadata must by a dict"
        self._metadata = metadata
        self._fix_metadata()
        
    def _filter(self, metadata, keys):
        """
        filter metadata return only the selected keys
        """
        if type(metadata) is list:
            new_metadata = []
            for m in metadata:
                filtered_list = self._filter(m, keys)
                if filtered_list is not None:
                    new_metadata.append(filtered_list)
            if new_metadata == []:
                return None
            return new_metadata
        elif type(metadata) is dict:
            new_metadata = {}
            for k in metadata.keys():
                if k.lower() in keys:
                    new_metadata[k] = metadata[k]
                else:
                    filtered_dict = self._filter(metadata[k], keys)
                    if filtered_dict is not None:
                        new_metadata[k] = filtered_dict
            if new_metadata == {}:
                return None
            return new_metadata
        elif type(metadata) is tuple:
            filtered_tuple = map(lambda x: filter_results(x, keys), metadata)
            for x in filtered_tuple:
                if x is not None:
                    return tuple(filtered_tuple)
            return None
        else:
            return None
        
    def filter(self, keys):
        """
        filter all metadata, return only the selected keys
        """
        if keys is None or len(keys) == 0:
            return self._metadata

        return self._filter(self._metadata, keys)

    def _fix_metadata(self):
        """
        Apply workarounds where the data returned is incorrect.
        At present, the metadata API always returns "Provisioning" for state
        """
        if 'instance' in self._metadata:
            if 'state' in self._metadata['instance']:
                self._metadata['instance']['state'] = 'Running'

    def get(self):
        return self._metadata

    def __repr__(self):
        return self._metadata.__str__()

    def __str__(self):
        return self._metadata.__str__()

    def __getitem__(self, item):
        return self._metadata[item]
    
class metadata(object):
    """
    class for querying OCI instance metadata
    """

    # all metadata
    _metadata = None

    # metadata service URL
    _oci_metadata_api_url = 'http://%s/opc/v1/' % METADATA_ENDPOINT

    # error log
    _errors = []

    # time of last metadata update
    _metadata_update_time = None

    # cache files
    _md_global_cache = GLOBAL_CACHE_DIR + "/metadata-cache"
    _md_user_cache = "~/.cache/oci-utils/metadata-cache"
    _md_cache_timeout = timedelta(minutes=2)
    _pub_ip_cache = GLOBAL_CACHE_DIR + "/public_ip-cache"
    _pub_ip_timeout = timedelta(minutes=10)

    def __init__(self, get_public_ip=True, debug=False):
        self._md_user_cache = os.path.expanduser(self._md_user_cache)
        self.logger = logging.getLogger('oci-metadata')
        if debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        self.logger.addHandler(handler)
        (cache_timestamp, cache_content) = cache.load_cache(
            self._md_global_cache, self._md_user_cache, self._md_cache_timeout)
        if cache_content is None:
            self.logger.debug("Cache not found or not usable, "
                              "refreshing metadata")
            self.refresh(get_public_ip=get_public_ip, debug=debug)
        else:
            self._metadata = OCIMetadata(cache_content)
            self._metadata_update_time = datetime.fromtimestamp(
                cache_timestamp)
        cfg = read_config()
        try:
            secs = int(cfg.get('public_ip', 'refresh_interval'))
            _pub_ip_timeout = timedelta(seconds=secs)
        except:
            pass
            
    def refresh(self, debug=False, get_public_ip=True):
        """
        Fetch all instance metadata from all sources
        Return True for success, False for failure
        """
        if debug:
            debug_handler = logging.StreamHandler(stream=sys.stderr)
            stun_log.addHandler(debug_handler)
            stun_log.setLevel(logging.DEBUG)
            self.logger.setLevel(logging.DEBUG)

        metadata = {}
        result = True

        # read the instance metadata
        lock_thread()
        try:
            api_conn = urllib2.urlopen(self._oci_metadata_api_url +
                                       'instance/', timeout=2)
            instance_metadata = json.loads(api_conn.read().decode())
            release_thread()
            metadata['instance'] = instance_metadata
        except IOError as e:
            release_thread()
            self._errors.append("Error connecting to metadata server: %s\n" % \
                                e[0])
            result = False

        # get the VNIC info
        lock_thread()
        try:
            api_conn = urllib2.urlopen(self._oci_metadata_api_url +
                                       'vnics/', timeout=2)
            vnic_metadata = json.loads(api_conn.read().decode())
            release_thread()
            metadata['vnics'] = vnic_metadata
        except IOError as e:
            release_thread()
            self._errors.append("Error connecting to metadata server: %s\n" % \
                                e[0])
            result = False

        if get_public_ip:
            public_ip = self.get_public_ip()
            if public_ip is None:
                self._errors.append("Failed to determine public IP address.\n")
                result = False
            else:
                metadata['publicIp']=public_ip

        if metadata:
            self._metadata = OCIMetadata(metadata)

            cache.write_cache(cache_content=self._metadata.get(),
                              cache_fname=self._md_global_cache,
                              fallback_fname=self._md_user_cache)
        return result

    def get_public_ip(self, refresh=False):
        if not refresh:
            # look for a valid cache
            (cache_timestamp, cache_content) = cache.load_cache(
                self._pub_ip_cache, max_age=self._pub_ip_timeout)
            if cache_content is not None and 'publicIp' in cache_content:
                return cache_content['publicIp']
        public_ip = None
        if oci_utils.oci_api.HAVE_OCI_SDK:
            # try the OCI APIs first
            try:
                sess = oci_utils.oci_api.OCISession()
                inst = sess.this_instance()    
                for vnic in inst.all_vnics():
                    if vnic.get_public_ip() is not None:
                        public_ip = vnic.get_public_ip()
                        break
            except oci_utils.oci_api.OCISDKError:
                pass
        if public_ip is None:
            # fall back to STUN:
            public_ip = get_ip_info(source_ip='0.0.0.0')[1]
        if public_ip is not None:
            # write cache
            cache.write_cache(cache_content={'publicIp':public_ip},
                              cache_fname=self._pub_ip_cache)
        return public_ip

    def filter(self, keys):
        return self._metadata.filter(keys)

    def get(self):
        if self._metadata is None:
            if not self.refresh():
                for e in self._errors:
                    sys.stderr.write(e)

        return self._metadata

    def __repr__(self):
        return self._metadata.__str__()

    def __str__(self):
        if self._metadata is None:
            return "None"
        else:
            return self._metadata.__str__()

    def __getitem__(self, item):
        return self._metadata[item]

set_proxy()

