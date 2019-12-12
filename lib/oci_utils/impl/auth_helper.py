# oci-utils
#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Communicate with the auth helper script.
"""

import json
import os
import subprocess
import sys
from ..exceptions import OCISDKError

_HELPER_SCRIPT = '/usr/libexec/oci-utils-config-helper'


class OCIAuthProxy(object):
    """
    Read the OCI config and authenticate with OCI services as another user
    """

    def __init__(self, user):
        """
        Initialisation of a OCIAuthProxy object.

        Parameters
        ----------
        user : str
            user name to be used for delegation

        Raises
        ------
        OCISDKError
            Proxy authentication failed
        """
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
        """
        Execute sub script; changing user using /bin/su.

        Raises
        ------
        OCISDKError
            Execution has failed.
        """
        try:
            dev_null = open(os.devnull, 'w')
            self.helper = subprocess.Popen(['/usr/bin/su',
                                            '-',
                                            self.user,
                                            '-c',
                                            '%s %s' % (sys.executable, _HELPER_SCRIPT)],
                                           stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE,
                                           stderr=dev_null,
                                           universal_newlines=True)
            self.is_open = True
        except Exception as e:
            raise OCISDKError('Failed to start auth helper script: %s' % e)

    def _receive(self):
        """
        Receive a response from proxy.

        Raises
        ------
        OCISDKError
            Error executing helper process.
        OCISDKError
            API error.

        Returns
        -------
            tuple
                The response,
        """
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
        """
        Terminate the helper process.

        Returns
        -------
            No return value.
        """
        if not self.is_open:
            return
        helper = self.helper
        self.is_open = False
        try:
            helper.terminate()
        except Exception:
            pass

    def get_config(self):
        """
        Get the OCI config data.

        Returns
        -------
            object
               The OCI configuration.
        """
        return self.config
