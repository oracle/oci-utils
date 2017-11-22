#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2017 Oracle and/or its affiliates. All rights reserved.
#
# The Universal Permissive License (UPL), Version 1.0
#
# Subject to the condition set forth below, permission is hereby granted to
# any person obtaining a copy of this software, associated documentation
# and/or data (collectively the "Software"), free of charge and under any
# and all copyright rights in the Software, and any and all patent rights
# owned or freely licensable by each licensor hereunder covering either
# (i) the unmodified Software as contributed to or provided by such licensor, or
# (ii) the Larger Works (as defined below), to deal in both
# (a) the Software, and
# (b) any piece of software and/or hardware listed in the lrgrwrks.txt
# file if one is included with the Software (each a "Larger Work" to which
# the Software is contributed by such licensors),
#
# without restriction, including without limitation the rights to copy,
# create derivative works of, display, perform, and distribute the Software
# and make, use, sell, offer for sale, import, export, have made, and have
# sold the Software and the Larger Work(s), and to sublicense the foregoing
# rights on either these or other terms.
#
# This license is subject to the following condition:
#
# The above copyright notice and either this complete permission notice or
# at a minimum a reference to the UPL must be included in all copies or
# substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

import os
import sys
import logging
import urllib2
import posixfile
import json
from datetime import datetime, timedelta
from .packages.stun import get_ip_info, log as stun_log
from cache import GLOBAL_CACHE_DIR

# file with a list IQNs to ignore
__ignore_file = "/var/run/oci-utils/ignore_iqns"

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
    _oci_metadata_api_url = 'http://169.254.169.254/opc/v1/'

    # error log
    _errors = []

    # time of last metadata update
    _metadata_update_time = None

    # cache files
    _global_cache = GLOBAL_CACHE_DIR + "/metadata-cache"
    _user_cache = "~/.cache/oci-utils/metadata-cache"
    _cache_timeout = timedelta(minutes = 2)

    def __init__(self, debug=False):
        self._user_cache = os.path.expanduser(self._user_cache)
        self.logger = logging.getLogger('oci-metadata')
        if debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        self.logger.addHandler(handler)
        (cache_timestamp, cache_content) = cache.load_cache(
            self._global_cache, self._user_cache, self._cache_timeout)
        if cache_content is None:
            self.logger.debug("Cache not found or not usable, "
                              "refreshing metadata")
            self.refresh(debug=debug)
        else:
            self._metadata = OCIMetadata(cache_content)
            self._metadata_update_time = datetime.fromtimestamp(
                cache_timestamp)
            
    def refresh(self, debug=False):
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
        try:
            api_conn = urllib2.urlopen(self._oci_metadata_api_url +
                                       'instance/')
            instance_metadata = json.loads(api_conn.read().decode())
            metadata['instance'] = instance_metadata
        except IOError as e:
            self._errors.append("Error connecting to metadata server: %s\n" % \
                                e[0])
            result = False

        # get the VNIC info
        try:
            api_conn = urllib2.urlopen(self._oci_metadata_api_url +
                                       'vnics/')
            vnic_metadata = json.loads(api_conn.read().decode())
            metadata['vnics'] = vnic_metadata
        except IOError as e:
            self._errors.append("Error connecting to metadata server: %s\n" % \
                                e[0])
            result = False

        # get public_ip
        public_ip = get_ip_info(source_ip='0.0.0.0')[1]
        if public_ip is None:
            self._errors.append("Failed to determine public IP address.\n")
            result = False
        else:
            metadata['publicIp']=public_ip

        if metadata:
            self._metadata = OCIMetadata(metadata)

        cache.write_cache(cache_content=self._metadata.get(),
                          cache_fname=self._global_cache,
                          fallback_fname=self._user_cache)
        return result

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
