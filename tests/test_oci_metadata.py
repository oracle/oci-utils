# Copyright (c) 2017, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

import os
import re
import unittest

from oci_utils import oci_regions
from oci_utils.metadata import InstanceMetadata as InstanceMetadata
from tools.decorators import skipUnlessOCI
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'


class TestOciMetadata(OciTestCase):
    """ OCI client metadata tests.
    """

    @skipUnlessOCI()
    def test_oci_metadata__get(self):
        """
        Test metadata class get.

        Returns
        -------
            No return value.
        """
        regionlist = list()
        for region in oci_regions.values():
            regionlist += re.split(' - | \(', region.replace(')',''))
        metadata = InstanceMetadata().get()
        self.assertNotEqual(metadata, [], 'Instanciated metadata is empty')
        self.assertTrue('instance' in metadata, 'instance key should be in metadata')
        self.assertIn('region', metadata['instance'], 'metadata does not contain region information')
        self.assertIn(metadata['instance']['region'], regionlist,
                      'instance region [%s] not part of possible values [%s]'
                      % (metadata['instance']['region'], regionlist))
        self.assertIn('state', metadata['instance'], 'Returned instance metadata do not contain any \'state\' key')
        self.assertEqual(metadata['instance']['state'], 'Running',
                         'execute state of OCI instance should  be running. [%s]'
                         % metadata['instance']['state'])
        self.assertIn('displayName' , metadata['instance'], 'displayname key should be in metadata')
        self.assertIn('availabilityDomain', metadata['instance'],
                        'availability domain key should be in metadata')
        self.assertIn('id' , metadata['instance'], 'OCID key should be in metadata')
        self.assertIn('compartmentId', metadata['instance'], 'compartment OCID key should be in metadata')

    @skipUnlessOCI()
    def test_oci_metadata_refresh(self):
        """
        Test metadata refresh.

        Returns
        -------
            No return value.
        """
        self.assertTrue(InstanceMetadata().refresh(), 'Metadata refresh failed.')

    @skipUnlessOCI()
    def test_oci_metadata__filter(self):
        """
        Test metadata filter.

        Returns
        -------
            No return value.
        """
        metadata = InstanceMetadata().filter(['macaddr', 'instance'])
        self.assertTrue(metadata, 'empty filtered metadata returned')
        self.assertIn('instance', metadata, '\'instance\' not part of filtered metadata')
        self.assertIn('compartmentId', metadata['instance'], '\'compartmentId\' not part of filtered instance metadata')
        self.assertIn('ocid1.compartment.oc1..', metadata['instance']['compartmentId'],
                      'Not expected value of \'compartmentId\'  of filtered instance metadata')
        self.assertIn('vnics', metadata, '\vnics\' not part of filtered instance metadata')
        self.assertIn('macAddr', metadata['vnics'][0], 'first VNIC of metatada do not contain \'macAddr\' key')
        self.assertNotIn('vnicId', metadata['vnics'][0], 'first VNIC of metatada do not contain \'vnicId\' key')


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOciMetadata)
    unittest.TextTestRunner().run(suite)
