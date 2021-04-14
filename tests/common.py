# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

# Common utility functions for tests

import os
import subprocess
import oci_utils


def get_hostname():
    return os.popen("hostname").read().strip()


def get_instance_id():
    return oci_utils.metadata()['instance']['id']


def run_cmd(cmd):
    """
    Run a [command, with, its, args] and return (exit code, output)
    """
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return 0, output
    except OSError as e:
        return 255, str(e)
    except subprocess.CalledProcessError as e:
        return e.returncode, e.output
