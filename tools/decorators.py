
# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

# Common decorator functions for oci-utils unit tests


import os
import os.path
from oci_utils.impl.network_helpers import is_ip_reachable
from oci_utils.impl import VIRSH_CMD
import subprocess
import unittest


from oci_utils.impl.network_helpers import is_ip_reachable
from oci_utils.metadata import InstanceMetadata

__all__ = ['skipUnlessRecorder',
           'skipUnlessRoot',
           'skipUnlessOCI',
           'needsOCICLI',
           'skipUnlessOCISDKInstalled',
           'skipUnlessVirSHInstalled',
           'skipItAsUnresolved']

__can_connect_to_oci_sap = None

_run_under_recorder = False

os.environ['LC_ALL'] = 'en_US.UTF8'


def skipUnlessRecorder():
    """skip the test unless we are running under custom test runner
        i.e OciUtilsTestRunnerRecord or OciUtilsTestRunnerReplay
        see setup.py
    """
    if not _run_under_recorder:
        return unittest.skip("custom test runner must be activated")
    return lambda func: func


def skipUnlessOCI():
    """
    Skip tests that require an OCI instance if not running on an OCI instance.
    Checks that we can connect to 169.254.169.254:80.

    Returns
    -------
    lambda function
        Decorator
    """
    global __can_connect_to_oci_sap
    if __can_connect_to_oci_sap is None:
        __can_connect_to_oci_sap = is_ip_reachable('169.254.169.254', 80)
    if not __can_connect_to_oci_sap:
        return unittest.skip("must be run on an OCI instance")
    return lambda func: func


def skipUnlessVirSHInstalled():
    """skip the test is libverit not installed

    """
    if not os.path.exists(VIRSH_CMD):
        return unittest.skip('virsh not installed')
    return lambda func: func


def skipItAsUnresolved():
    """
    just skip the test
    """
    return unittest.skip("Unresolved")


__current_user_id = None


def skipUnlessRoot():
    """
    Skip test if the user is not root.

    Returns
    -------
    lambda function
        Decorator
    """
    global __current_user_id
    if __current_user_id is None:
        # cache the value to speedup tests execution
        __current_user_id = os.geteuid()

    if __current_user_id != 0:
        return unittest.skip("Must be root")
    return lambda func: func


__sdk_installed = None


def skipUnlessOCISDKInstalled():
    """
    Skip ifOCI sdk not installed.

    Returns
    -------
    lambda function
        Decorator
    """
    global __sdk_installed
    if __sdk_installed is None:
        try:
            __sdk_installed = True
        except ImportError:
            __sdk_installed = False
    if not __sdk_installed:
        return unittest.skip("OCI SDK not installed")
    return lambda func: func


__needsOCICLI_msg = None


def needsOCICLI():
    """
    Skip test if the OCI CLI is not installed and configured:
    * checks that oci command line is present;
    * checks that we are running on OCI instance by check a call to OCI SDK;
    * checks that we can call oci instance;

    Returns
    -------
    lambda function
        Decorator
    """
    global __needsOCICLI_msg

    if __needsOCICLI_msg == '':
        # we've been here already and everything is fine
        return lambda func: func

    if __needsOCICLI_msg is not None:
        # we've been here already and something is wrong
        return unittest.skip(__needsOCICLI_msg)

    # first time here: let's do some checks.

    if not os.path.exists('/usr/bin/oci'):
        __needsOCICLI_msg = "OCI CLI client must be installed for this " \
                            "test (missing /usr/bin/oci)"
        return unittest.skip(__needsOCICLI_msg)

    # we expect metadata to host 'instance' key with 'id' information in it
    _instance_id = None
    try:
        _instance_id = InstanceMetadata().get()['instance'].get('id')
    except Exception:
        pass

    if _instance_id is None:
        __needsOCICLI_msg = "must be run on an OCI instance " \
                            "(get_instance_id() failed)"
        return unittest.skip(__needsOCICLI_msg)

    # now check that the oci client is configured
    sp = subprocess.Popen(['/usr/bin/oci', 'compute', 'instance', 'get',
                           '--instance-id', _instance_id],
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    (_, _) = sp.communicate()
    if sp.returncode != 0:
        __needsOCICLI_msg = "OCI CLI client must be configured for this " \
                            "test (oci command execution failed)"
        return unittest.skip(__needsOCICLI_msg)

    # empty means OK
    __needsOCICLI_msg = ''

    return lambda func: func
