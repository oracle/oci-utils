# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module to manage oci-image-migrate settings and configuration data.
"""
import yaml

from oci_migrate.migrate import gen_tools

ocimigrateconffile = '/etc/oci-utils/oci-migrate-conf.yaml'


# flag and reason if upload can proceed.
migrate_preparation = True
migrate_non_upload_reason = ''

class OciMigrateConfParam(object):
    """
    Retrieve oci-image-migrate configuration data from the
    oci-image-migrate configuration file, in yaml format.
    """
    def __init__(self, yamlconf, tag):
        """
        Initialisation of the oci image migrate configuration retrieval.

        Parameters:
        ----------
            yamlconf: str
                The full path of the oci-image-migrate configuration file.
            tag: str
                The configuration structure to collect.
        """
        self.yc = yamlconf
        self.tg = tag

    def __enter__(self):
        """
        OciMigrateConfParam entry.
        """
        with open(self.yc, 'r') as f:
            self.confdata = yaml.load(f, Loader=yaml.SafeLoader)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        OciMigrateConfParam cleanup and exit.
        """
        pass

    def values(self):
        """
        Retrieve the configuration data.
        """
        return(self.confdata[self.tg])


def get_config_data(key):
    """
    Get configuration data.

    Parameters:
    ----------
    key: str
        Key from the configuration data.

    Return:
       The configuration data, type varies.
    """
    try:
        with OciMigrateConfParam(ocimigrateconffile, key) as config:
            return config.values()
    except Exception as e:
        gen_tools.exit_msg('Failed to get data for %s, unable to '
                               'continue:\n  %s' % (key, str(e)))

