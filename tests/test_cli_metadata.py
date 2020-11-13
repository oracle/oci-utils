# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest
from tools.oci_test_case import OciTestCase


class TestCliOciMetadata(OciTestCase):
    """ oci-metadata tests.
    """

    def setUp(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.

        Raises
        ------
        unittest.Skiptest
            If the metadata_cli does not exist.
        """

        super().setUp()
        self.oci_metadata_path = self.properties.get_property('oci-metadata')
        if not os.path.exists(self.oci_metadata_path):
            raise unittest.SkipTest("%s not present" % self.oci_metadata_path)

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--help'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_human_readable(self):
        """
        Test displaying metadata values .

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--human-readable'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_display_json(self):
        """
        Test displaying metadata values in JSON .

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--json'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_metadata(self):
        """
        Test displaying 'instance' metadata

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--get', 'instance'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_metadata_only_values(self):
        """
        Test displaying 'instance' metadata

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--get', 'instance', '--value-only'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_all_vnics(self):
        """
        Test displaying instance VNICs metadata

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--get', 'vnics', '--value-only', '--trim'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_single_key(self):
        """
        Test displaying data fro single key

        Returns
        -------
        No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/privateip', '--trim'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/privateip',
                                         '--get', '/instance/id', '--trim'])
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics/*/privateip',
                                         '--trim', '--value-only'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_update_key(self):
        """
        Test update an instance metadata key

        Returns
        -------
        No return value.
        """
        try:
            this_displayname = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/displayName',
                                                        '--value-only', '--trim']).decode('utf-8')
            _ = subprocess.check_output([self.oci_metadata_path, '--update', 'displayName=AutoTest'])
            _ = subprocess.check_output([self.oci_metadata_path, '--update', 'displayName=%s' % this_displayname])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))

    def test_get_instance_id_data(self):
        """
        Test metadata retrieval via instance id
        """
        try:
            instance_ocid = subprocess.check_output([self.oci_metadata_path, '--get', '/instance/id',
                                                     '--value-only', '--trim']).decode('utf-8')
            _ = subprocess.check_output([self.oci_metadata_path, '--get', '/vnics', '--instance-id', instance_ocid])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))
