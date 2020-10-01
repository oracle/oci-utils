# oci-utils
#
# Copyright (c) 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.


import subprocess


def _call(cmd, log_output=True):
    """
    Executes a comand and returns the exit code
    """
    cmd.insert(0, 'sudo')
    try:
        subprocess.check_call(cmd, stderr=subprocess.STDOUT)
    except OSError as e:
        return 404
    except subprocess.CalledProcessError as e:
        if log_output:
            print("Error executing {}: {}\n{}\n".format(cmd, e.returncode, e.output))
        return e.returncode
    return 0


def _call_output(cmd, log_output=True):
    """
    Executes a command and returns stdout and stderr in a single string
    """
    cmd.insert(0, 'sudo')
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except OSError as e:
        return 404
    except subprocess.CalledProcessError as e:
        if log_output:
            print("Error execeuting {}: {}\n{}\n".format(cmd, e.returncode, e.output))
        return None
    return None


def _call_popen_output(cmd, log_output=True):
    """
    Executes a command and returns stdout and stderr in a single string
    """
    cmd.insert(0, 'sudo')
    try:
        p = subprocess.Popen(' '.join(cmd), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return p.communicate()[0]
    except OSError as e:
        return 404
    except subprocess.CalledProcessError as e:
        if log_output:
            print("Error executing {}: {}\n{}\n".format(cmd, e.returncode, e.output))
        return None
    return None
