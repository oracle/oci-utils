# oci-utils
#
# Copyright (c) 2017, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Managing the metadata.
"""

import json
import logging
import urllib.request, urllib.error, urllib.parse
from datetime import timedelta

from . import cache
from oci_utils import _METADATA_ENDPOINT
from oci_utils.impl import lock_thread, release_thread

_logger = logging.getLogger('oci-utils.oci-metadata')


def _get_by_path(dic, keys):
    """
    Access a nested object in dic by key sequence.

    Parameters
    ----------
    dic : dict
        The dictionary.
    keys : list
        The key sequence.

    Returns
    -------
        dict
            The dictionary object if found, None otherwise

    """
    assert len(keys) > 0, "Path key can not be an empty list."

    d = dic
    for key in keys[:-1]:
        if type(key) is int or key in d:
            d = d[key]
        else:
            return None
    if keys[-1] in d or (type(d) is list and keys[-1] < len(d)):
        return d[keys[-1]]
    else:
        return None


def _set_by_path(dic, keys, value, create_missing=True):
    """
    Set a nested object in dic by key sequence.

    Parameters
    ----------
    dic : dict
        The dictionary object.
    keys : list
        The key sequence.
    value : dict
        To be added.
    create_missing : bool
        Flag if set, to create if not present yet.

    Returns
    -------
        dict
            The resulting dictionary object.
    """
    d = dic
    i = 0
    n_key = len(keys) - 1
    while i < n_key:
        k = keys[i]
        if type(k) is int:
            assert type(
                d) is list, \
                "Internal Error: %s is Expected as a list for %s.\n " % (d, k)

            while len(d) <= k:
                d.insert(k, {})
            d = d[k]
        elif k in d:
            d = d[k]
        elif create_missing:
            next_key = keys[i + 1]
            if type(next_key) is int:
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

    if type(d) is list and keys[-1] >= len(d):
        d.insert(keys[-1], value)
    else:
        d[keys[-1]] = value
    return dic


# metadata attibute map
# get from sdk and from METADATA_ENDPOINT are different.
# Choose to use the key format in the attribute_map.

_attribute_map = {
    "lifecycle_state": "state",
    "availability_domain": "availabilityDomain",
    "display_name": "displayName",
    "compartment_id": "compartmentId",
    "defined_tags": "definedTags",
    "freeform_tags": "freeformTags",
    "time_created": "timeCreated",
    "source_details": "sourceDetails",
    "launch_options": "launchOptions",
    "image_id": "imageId",
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
    "vnic_id": "vnicId",
    "virtual_router_ip": "virtualRouterIp",
    "nic_index": "nicIndex",
    "vlan_tag": "vlanTag"}

_inv_attribute_map = {v.lower(): k for k, v in _attribute_map.items()}


def _get_path_keys(metadata, key_path, newkey_list):
    """
    Parsing key path.

    Parameters
    ----------
    metadata : dict
        A dict that the key_path can apply.
    key_path : list
        A list of key sequence, it may contain wildcard.
    newkey_list : list
        The result concrete keys after parsing the key path.

    Returns
    -------
        No return value, exit on failure.
        Parameter newkey_list will be updated.

    """
    if len(key_path) == 0:
        return

    if len(newkey_list) == 0:
        newkey_list.append([])

    key = key_path[0]
    if key.isdigit() and type(metadata) is list:
        nkey = int(key)
        assert nkey < len(metadata), \
            "key(%s) in %s is out of range.\n" % (nkey, key_path)

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
        lower_keys = {k.lower(): k for k in metadata}
        if key not in metadata and key in lower_keys:
            # lower case key, get original
            key = lower_keys[key]

        for nk in newkey_list:
            nk.append(key)

        assert key in metadata, \
            "Invalid key '%s'  in %s.\n" % (key, str(metadata))
        metadata = metadata[key]

    if len(key_path) > 1:
        _get_path_keys(metadata, key_path[1:], newkey_list)
    else:
        return


class OCIMetadata(dict):
    """
    A class representing all OCI metadata.

    Attributes
    ----------
    _metadata : dict
        The metadata.
    """
    _metadata = None

    def __init__(self, metadata, convert=False):
        """
        Class OCIMetadata initialization.

        Parameters
        ----------
        metadata : dict
            The metadata dictionary.
        convert : bool
            The conversion flag.
        """
        assert type(metadata) is dict, "metadata must be a dict"
        if convert:
            self._metadata = self._name_convert_camel_case(metadata)
            self._post_process(self._metadata)
        else:
            self._metadata = metadata

    def _name_convert_underscore(self, meta):
        """
        Convert name format from nameXyz into name_xyz.
        Parameters
        ----------
        meta : list or dict
            The metadata.

        Returns
        -------
            list or dictionary
                Updated list or dictionary.
        """
        if type(meta) is list:
            new_meta = []
            for m in meta:
                new_meta.append(self._name_convert_underscore(m))

        elif type(meta) is dict:
            new_meta = {}
            for (key, value) in meta.items():
                nkey = key.lower()
                try:
                    n_key = _inv_attribute_map[nkey]
                except Exception:
                    n_key = nkey
                new_meta[n_key] = self._name_convert_underscore(value)
        else:
            new_meta = meta

        return new_meta

    def _post_process(self, metadata):
        """
        Due to the different attribute names from the instance metadata
        service and from the SDK, we need to convert the names from the SDK
        to the names from the instance metadata service.

        Parameters
        ----------
        metadata: dict
           The metadata.

        Returns
        -------
            dict
                The converted metadata.
        """
        # merge extendedMetadata into metadata
        if 'instance' in metadata and metadata['instance'] is not None:
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

    def _name_convert_camel_case(self, meta):
        """
        Convert name to camelcase, name_xyz into nameXyz.

        Parameters
        ----------
        meta: some structure
            The metadata.

        Returns
        -------
            The converted metadata.
        """
        if type(meta) is list:
            new_meta = []
            for m in meta:
                new_meta.append(self._name_convert_camel_case(m))

        elif type(meta) is dict:
            new_meta = {}
            for (key, value) in meta.items():
                try:
                    n_key = _attribute_map[key]
                except Exception:
                    n_key = key
                new_meta[n_key] = self._name_convert_camel_case(value)
        else:
            new_meta = meta

        return new_meta

    def _filter_new(self, metadata, keys):
        """
        Filter metadata based on keys, including keypath.

        Parameters
        ----------
        metadata: dict
            The metadata.
        keys: list
            The list of filter keys.

        Returns
        -------
            dict
                The filtered metadata.
        """
        single_key_list = []
        key_path_list = []
        new_meta = {}
        for key in keys:
            key = key.replace("extendedMetadata", "metadata").replace(
                "extendedmetadata", "metadata")
            #
            # fixing issues with oci-metadata not working with hyphenated
            # keys; this was done initially to be consistent with the OCI SDK.
            # if key.find('-') >= 0:
            #     key = key.replace('-', '_')

            if key.find('/') >= 0:
                # key is a path
                new_keys = []
                key_l = key.split("/")
                meta = metadata
                _get_path_keys(meta, key_l, new_keys)
                key_path_list += new_keys
                for nkey in new_keys:
                    value = _get_by_path(metadata, nkey)
                    new_meta[str(nkey)] = value
            else:
                single_key_list.append(key)
        if len(single_key_list) > 0:
            ret_meta = self._filter(metadata, single_key_list)
        else:
            ret_meta = {}

        for key_path in key_path_list:
            _set_by_path(ret_meta, key_path, new_meta[str(key_path)])

        return ret_meta

    def _filter(self, metadata, keys):
        """
        Filter metadata, return only the selected simple keys.

        Parameters
        ----------
        metadata : dict
            The metadata.
        keys : list
            The list of keys.

        Returns
        -------
            The filtered metadata.
        """
        if type(metadata) is list:
            new_metadata = []
            for m in metadata:
                filtered_list = self._filter(m, keys)
                if filtered_list is not None:
                    new_metadata.append(filtered_list)
            if not new_metadata:
                return None
            return new_metadata
        elif type(metadata) is dict:
            new_metadata = {}
            for k in list(metadata.keys()):
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
            filtered_tuple = [filter_results(x, keys) for x in metadata]
            for a in filtered_tuple:
                if a is not None:
                    return tuple(filtered_tuple)
            return None
        else:
            return None

    def filter(self, keys):
        """
        Filter all metadata, return only the selected keys.

        Parameters
        ----------
        keys: list
            The list of keys.

        Returns
        -------
            list
                The list of selectef keys
        """
        if keys is None or len(keys) == 0:
            return self._metadata

        return self._filter_new(self._metadata, keys)

    def get(self):
        """
        Return the metadata.

        Returns
        -------
            dict
                The metadata.
        """
        return self._metadata

    def __repr__(self):
        """
        Overwrite __repr__.

        Returns
        -------
            str
                String representation is this instance.
        """
        return self._metadata.__str__()

    def __str__(self):
        """
        Overwrite __str__.

        Returns
        -------
            str
                String version of this instance.

    """
        return self._metadata.__str__()

    def __getitem__(self, item):
        """
        Overwrite dict.get. see dict.get().

        Parameters
        ----------
            item : str
                The key to look for.

        Returns
        -------
            object
                the value of given key
        """
        return self._metadata[item]


class InstanceMetadata(object):
    """
    Class for querying OCI instance metadata.

    Attributes
    ----------
        _metadata : dict
            All metadata.
        _oci_metadata_api_url: str
            The metadata service URL.
        _metadata_update_time : datetime
            The time of last metadata update.
        _md_user_cache : str
            The filename for the metadata user cache.
        _md_global_cache : str
            The filename for the global metadata cache.
        _md_cache_timeout : timedelta
            Timeout for collecting the metadata and writing to the file.
        _pub_ip_cache : str
            The filename for the public IP cache.
        _pub_ip_timeout : timedelta
            Timeout for collecting the public IP cache and writing to the file.
    """
    # all metadata
    _metadata = None

    # metadata service URL
    _oci_metadata_api_url = 'http://%s/opc/v1/' % _METADATA_ENDPOINT

    # error log
    _errors = []

    # time of last metadata update
    _metadata_update_time = None

    # cache files
    _md_cache_timeout = timedelta(minutes=2)
    _pub_ip_cache = cache.get_cache_file_path("public_ip-cache")
    _pub_ip_timeout = timedelta(minutes=10)
    _logger = logging.getLogger('oci-utils.metadata')

    def __init__(self, instance_id=None, get_public_ip=False,
                 oci_metadata=None, debugflag=False):
        """
        The initialisation of the metadata class.

            Parameters
            ----------
            instance_id : OCID
                The OCI instance id.
            get_public_ip : bool
                Flag, collect the public IP addresses if set.
            oci_metadata : dict
                The metadata dictionary; if not specified, pull the metadata.
        """
        if oci_metadata is None:
            self.refresh()
        else:
            assert type(oci_metadata) is \
                OCIMetadata, "input should be an OCIMetadata object"
            self._metadata = oci_metadata

    def refresh(self, get_public_ip=False):
        """
        Fetch all instance metadata from all sources.

        Parameters
        ----------
        get_public_ip : bool
            The flag to collect the public ip address of the instance.

        Returns
        -------
            boolean
                True for success, False for failure.
        """
        _logger.debug('refreshing metada')
        metadata = {}
        result = True

        # read the instance metadata
        lock_thread()
        try:
            api_conn = urllib.request.urlopen(
                self._oci_metadata_api_url + 'instance/', timeout=2)
            instance_metadata = json.loads(api_conn.read().decode('utf-8'))
            metadata['instance'] = instance_metadata
        except IOError as e:
            self._errors.append(
                "Error connecting to metadata server: %s\n" % e[0])
            result = False
        finally:
            release_thread()

        # get the VNIC info
        lock_thread()
        try:
            api_conn = urllib.request.urlopen(
                self._oci_metadata_api_url + 'vnics/', timeout=2)
            vnic_metadata = json.loads(api_conn.read().decode('utf-8'))
            metadata['vnics'] = vnic_metadata
        except IOError as e:
            self._errors.append(
                "Error connecting to metadata server: %s\n" % e[0])
            result = False
        finally:
            release_thread()

        if metadata:
            self._metadata = OCIMetadata(metadata)

        _logger.debug('metadata after refresh [%s]' % str(self._metadata))
        return result

    def filter(self, keys):
        """
        Filter metadata keys

        Parameters
        ----------
        keys : list
            The list of keys.

        Returns
        -------
            dict
                The filtered metadata.
        """

        assert self._metadata is not None, "Metadata is None. Check your " \
                                           "input, config, and connection."
        return self._metadata.filter(keys)

    def get(self, silent=False):
        """
        Get the metadata

        Returns
        -------
        dict
            The metadata or None if they are not loaded and refesh is off.
        """

        if self._metadata is None and not silent:
            if not self.refresh():
                for e in self._errors:
                    _logger.error(e)

        return self._metadata

    def __repr__(self):
        """
        Overwrite __repr__.

        Returns
        -------
        str
            String representation is this instance.
        """

        return self._metadata.__str__()

    def __str__(self):
        """
        Overwrite __str__.

        Returns
        -------
        str
            String version of this instance.
        """
        if self._metadata is None:
            return "None"
        else:
            return self._metadata.__str__()

    def __getitem__(self, item):
        """
        Overwrite dict.__getitem__.
        Parameters
        ----------
        item : str
            The key to look for.

        Returns
        -------
        object
            The value of given key.
        """

        return self._metadata[item]
