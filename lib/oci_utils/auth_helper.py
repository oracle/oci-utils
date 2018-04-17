#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

"""
communicate with the auth helper script
"""

import sys
import os
import subprocess
import json
import oci as oci_sdk
import base64
from .exceptions import OCISDKError

HELPER_SCRIPT = '/usr/libexec/oci-utils-config-helper'

class OCIAuthProxy(object):
    """
    Read the OCI config and authenticate with OCI services as another user
    """
    def __init__(self, user):
        self.is_open = False
        self.user = user
        self.helper = None
        self._open()
        resp = self._receive()
        self._close()
        if resp['status'] != 'OK':
            raise OCISDKError('Proxy authentication failed: %s' % resp['data'])
        self.config = resp['data']

    def _open(self):
        try:
            DEVNULL = open(os.devnull, 'w')
            self.helper = subprocess.Popen(['/usr/bin/su',
                                            '-',
                                            self.user,
                                            '-c',
                                            HELPER_SCRIPT],
                                           stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE,
                                           stderr=DEVNULL,
                                           universal_newlines=True)
            self.is_open = True
        except Exception as e:
            raise OCISDKError('Failed to start auth helper script: %s' % e)

    def _receive(self):
        if not self.is_open or self.helper.poll() is not None:
            raise OCISDKError('Internal error: helper process pipe not open')
        # skip debug lines
        resp = {'status': 'DEBUG'}
        while resp['status'] == 'DEBUG':
            line = self.helper.stdout.readline()
            resp = json.loads(line.strip())
            if resp['status'] == 'ERROR':
                raise OCISDKError('API Proxy error: %s' % resp['data'])
        return resp

    def _close(self):
        if not self.is_open:
            return
        helper = self.helper
        self.is_open = False
        try:
            helper.terminate()
        except:
            pass

    def get_config(self):
        """
        return the OCI config data
        """
        return self.config
