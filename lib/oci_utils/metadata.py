#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2017, 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

import os
import os.path
import sys
import logging
import urllib2
import json
from datetime import datetime, timedelta
from .packages.stun import get_ip_info, log as stun_log
import cache
from cache import GLOBAL_CACHE_DIR
import oci_utils.oci_api
from oci_utils import read_config, release_thread, lock_thread


def get_by_path(dic, keys):
    """
    Access a nested object in dic by key sequence.
    """
    assert len(keys)>0, "Path key can not be an empty list."

    d = dic
    for key in keys[:-1]:
        if type(key) is int or key in d: 
            d = d[key]
        else:
            return None
    if keys[-1] in d or ( type(d) is list and keys[-1] < len(d)):    
        return d[keys[-1]]
    else:
        return None

def set_by_path(dic, keys, value, create_missing=True):
    """
    set a nested object in dic by key sequence.
    """

    d = dic
    i = 0
    nKey = len(keys) - 1
    while i < nKey:
        k = keys[i]
        if type(k) is int: 
            assert type(d) is list, "Internal Error: %s is Expected as a list for %s.\n " %(d, k)

            while len(d) <= k:
                d.insert(k, {})
            d = d[k]
        elif k in d:
            d = d[k]
        elif create_missing:
            nextKey = keys[i+1]
            if type(nextKey) is int:
                if type(d) is list:
                    d.insert(k, [])
                else:
                    d[k] = []
            else:
                d[k] = {}
            d = d[k]
        else:
            return dic
        i += 1

    if type(d) is list  and keys[-1] >= len(d):
            d.insert(keys[-1], value)
    else:
        d[keys[-1]] = value
    return dic

METADATA_ENDPOINT = '169.254.169.254'

#metadata attibute map
#get from sdk and from METADATA_ENDPOINT are different. 
#Choose to use the key format in the attribute_map.

attribute_map = {
            "lifecycle_state": "state",
            "availability_domain": "availabilityDomain",
            "display_name": "displayName",
            "compartment_id": "compartmentId",
            "defined_tags": "definedTags",
            "freeform_tags": "freeformTags",
            "time_created": "timeCreated",
            "source_details": "sourceDetails",
            "launch_options": "launchOptions",
            "image_id": "image",
            "fault_domain": "faultDomain",
            "launch_mode": "launchMode",
            "ipxe_script": "ipxeScript",
            "extended_metadata": "extendedMetadata",
            "boot_volume_type": "bootVolumeType",
            "network_type": "networkType",
            "remote_data_volume_type": "remoteDataVolumeType",

            "source_type": "sourceType",
            "boot_volume_id": "bootVolumeId",

            "is_primary": "isPrimary",
            "public_ip": "publicIp",
            "skip_source_dest_check": "skipSourceDestCheck",
            "private_ip": "privateIp",
            "mac_address": "macAddr",
            "hostname_label": "hostnameLabel",
            "subnet_cidr_block": "subnetCidrBlock",
            "vnic_id":     "vnicId",
            "virtual_router_ip" : "virtualRouterIp",
            "nic_index": "nicIndex",
            "vlan_tag": "vlanTag"
        }

inv_attribute_map = {v.lower(): k for k, v in attribute_map.iteritems()}

# oci-utils configuration defaults
__oci_utils_defaults = """
[auth]
auth_method = auto
oci_sdk_user = opc
[iscsi]
enabled = true
scan_interval = 60
max_volumes = 8
auto_resize = true
auto_detach = true
detach_retry = 5
[vnic]
enabled = true
scan_interval = 60
vf_net = false
[public_ip]
enabled = true
refresh_interval = 600
"""

def get_path_keys(metadata,key_path, newkey_list):
    '''
    Parameters:
        metadata: a dict that the key_path can apply.
        key_path: is a list of key sequence, it may contain wildcard.
        newkey_list: the result concret keys after parsing the key path.
    Return:
        Parameter newkey_list will be updated.
        None.
    '''
    if len(key_path)==0:
        return 

    if len(newkey_list)==0:
        newkey_list.append([])

    key =key_path[0]
    if key.isdigit() and type(metadata) is list:
        nkey = int(key)
        assert nkey < len(metadata), "key(%s) in %s is out of range.\n" % (nkey, key_path)

        for nk in newkey_list:
            nk.append(nkey)
        metadata = metadata[nkey]

    elif key == "*" or key == "":
        if type(metadata) is list:
            orig = []
            orig += newkey_list
            for nk in orig:
                newkey_list.remove(nk)
                for i in range(len(metadata)):
                    nkey = nk + [i]
                    newkey_list.append(nkey)
            metadata = metadata[0]
        else:
            pass
    else:
        lower_keys={k.lower():k for k in metadata}
        if key not in metadata and key in lower_keys:
            #lower case key, get original
            key = lower_keys[key]

        for nk in newkey_list:
            nk.append(key)

        assert key in metadata, "Invalid key '%s'  in %s.\n" % (key, str(metadata)) 
        metadata = metadata[key]

    if len(key_path)>1:    
        get_path_keys(metadata,key_path[1:], newkey_list) 
    else:
        return


class OCIMetadata(dict):
    """
    a class representing all OCI metadata
    """
    _metadata = None

    def __init__(self, metadata, convert=False):
        assert type(metadata) is dict, "metadata must be a dict"
        if convert:
            self._metadata = self._name_convert_camelCase(metadata)
            self._post_process(self._metadata)
        else:
            self._metadata = metadata
        self._fix_metadata()
        
    def _name_convert_underscore(self, meta):
        """
        convert name format from nameXyz into name_xyz 
        """
        if type(meta) is list:
            new_meta = []
            for m in meta:
                new_meta.append(self._name_convert_underscore(m))

        elif type(meta) is dict:
            new_meta = {}
            for (key, value) in meta.iteritems():
                nkey = key.lower()
                try:
                    n_key = inv_attribute_map[nkey]
                except:
                    n_key = nkey
                new_meta[n_key] = self._name_convert_underscore(value)
        else:
                new_meta = meta 

        return new_meta

    def _post_process(self, metadata):
        '''
        Due to the different attribute names from the instance metadata
        service and from the SDK, we need to convert the names from the
        SDK to the names from the instance metadata service.
        '''
        # merge extendedMetadata into metadata
        if 'instance' in metadata:
            if 'metadata' in metadata['instance']:
                if 'extendedMetadata' in metadata['instance']:
                    v = metadata['instance'].pop('extendedMetadata')
                    metadata['instance']['metadata'].update(v)
            else:
                if 'extendedMetadata' in metadata['instance']:
                    v = metadata.pop('extendedMetadata')
                    metadata['metadata'] = v

        # change vnic's id to vnicId
        if 'vnics' in metadata:
            for i in range(len(metadata['vnics'])):
                v = metadata['vnics'][i].pop('id')
                metadata['vnics'][i]['vnicId'] = v
        return metadata

                
    def _name_convert_camelCase(self, meta):
        """
        convert name_xyz into nameXyz 
        """
        if type(meta) is list:
            new_meta = []
            for m in meta:
                new_meta.append(self._name_convert_camelCase(m))

        elif type(meta) is dict:
            new_meta = {}
            for (key, value) in meta.iteritems():
                try:
                    n_key = attribute_map[key]
                except:
                    n_key = key
                new_meta[n_key] = self._name_convert_camelCase(value)
        else:
                new_meta = meta 

        return new_meta

                        
    def _filter_new(self, metadata, keys):
        """
        filter metadata based on keys, including keypath.
        """
        single_key_list = []
        key_path_list = []
        new_meta = {}
        for key in keys:
            key = key.replace("extendedMetadata","metadata").replace("extendedmetadata","metadata")
            if key.find('-') >= 0:
                key = key.replace('-','_')

            if key.find('/') >= 0:
                #key is a path
                new_keys = []
                key_l = key.split("/")
                meta = metadata
                get_path_keys(meta, key_l, new_keys) 
                key_path_list += new_keys 
                for nkey in new_keys:
                    value = get_by_path(metadata, nkey)
                    new_meta[str(nkey)] = value
            else:
                single_key_list.append(key)
        if len(single_key_list) > 0:        
            ret_meta =  self._filter(metadata, single_key_list) 
        else:
            ret_meta = {}

        for key_path in key_path_list:
            set_by_path(ret_meta, key_path, new_meta[str(key_path)])

        return ret_meta


    def _filter(self, metadata, keys):
        """
        filter metadata return only the selected simple keys
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
                if k in keys:
                    new_metadata[k] = metadata[k]
                elif k.lower() in keys:
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

        return self._filter_new(self._metadata, keys)

    def _fix_metadata(self):
        """
        Apply workarounds where the data returned is incorrect.
        At present, the metadata API always returns "Provisioning" for state

        if 'instance' in self._metadata:
            if 'state' in self._metadata['instance']:
                self._metadata['instance']['state'] = 'Running'

        """
        pass

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
    _md_cache_timeout = timedelta(minutes=2)
    _pub_ip_cache = GLOBAL_CACHE_DIR + "/public_ip-cache"
    _pub_ip_timeout = timedelta(minutes=10)


    def __init__(self, instance_id=None, get_public_ip=False, debug=False, oci_metadata=None):
        '''
        This is used to get  metadata of the instance it is running on.
        :param get_public_ip:
        :param debug:
        '''
        self.logger = logging.getLogger('oci-metadata')
        if debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        self.logger.addHandler(handler)

        if instance_id is not None:
            oci_metadata = oci_utils.oci_api.OCISession(debug=debug).get_instance(instance_id=instance_id).get_metadata()

        if oci_metadata is not None:
            assert type(oci_metadata) is OCIMetadata, "input should be an OCIMetadata object"
            self._metadata = oci_metadata
        else:
            self.refresh(get_public_ip=get_public_ip, debug=debug)

        cfg = read_config()
        try:
            secs = int(cfg.get('public_ip', 'refresh_interval'))
            _pub_ip_timeout = timedelta(seconds=secs)
        except:
            pass
            

    def refresh(self, debug=False, get_public_ip=False):
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
            inst = None
            try:
                sess = oci_utils.oci_api.OCISession()
                inst = sess.this_instance()    
                if inst is not None:
                    for vnic in inst.all_vnics():
                        public_ip = vnic.get_public_ip()
                        if public_ip is not None:
                            break
            except Exception as e:
                self.logger.error(e)
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
        assert self._metadata is not None, "Metadata is None. Check your input, config, and connection."
        return self._metadata.filter(keys)

    def get(self, silent=False):
        if self._metadata is None and not silent:
            if not self.refresh():
                for e in self._errors:
                    self.logger.error(e)

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

