# Copyright (c) 2017, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

import re
import unittest

from tools.decorators import skipUnlessOCI
from oci_utils.metadata import InstanceMetadata as InstanceMetadata
from tools.oci_test_case import OciTestCase

oci_regions = {
    'phx': 'phx - us-phoenix-1 (Phoenix, AZ, USA)',
    'iad': 'iad - us-ashburn-1 (Ashburn, VA, USA)',
    'fra': 'fra - eu-frankfurt-1 (Frankfurt, Germany)',
    'lhr': 'lhr - uk-london-1 (London, UK)',
    'ams': 'ams - eu-amsterdam-1 (Amsterdam, The Netherlands)',
    'bom': 'bom - ap-mumbai-1 (Mumbai, India)',
    'cwl': 'cwl - uk-cardiff-1 (Newport, UK)',
    'dxb': 'dxb - me-dubai-1 (Duabi, UAE)',
    'gru': 'gru - sa-saopaulo-1 (Sao Paulo, Brazil)',
    'hyd': 'hyd - ap-hyderabad-1 (Hyderabad, India)',
    'icn': 'icn - ap-seoul-1 (Seoul, South Korea)',
    'jed': 'jed - me-jeddah-1 (Jeddah, Saoudi Arabia)',
    'kix': 'kix - ap-osaka-1 (Osaka, Japan)',
    'mel': 'mel - ap-melbourne-1 (Melbourne, Australia)',
    'nrt': 'nrt - ap-tokyo-1 (Tokyo, Japan)',
    'sjc': 'sjc - us-sanjose-1 (San Jose, CA, USA)',
    'syd': 'syd - ap-sydney-1 (Sydney, Australia)',
    'yny': 'yny - ap-chuncheon-1 (Chuncheon, South Korea)',
    'yul': 'yul - ca-montreal-1 (Montreal, Canada)',
    'yyz': 'yyz - ca-toronto-1 (Toronto, Canada)',
    'zrh': 'zrh - eu-zurich-1 (Zurich, Switzerland)'}


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
        self.assertTrue(metadata['instance'], 'instance key of metadata should be True')
        self.assertIn('region', metadata['instance'], 'metadata does not contain region information')
        self.assertIn(metadata['instance']['region'], regionlist,
                      'instance region [%s] not part of possible values [%s]'
                      % (metadata['instance']['region'], regionlist))
        self.assertIn('state', metadata['instance'], 'Returned instance metadata do not contain any \'state\' key')
        self.assertEqual(metadata['instance']['state'], 'Running',
                         'execute state of OCI instance should  be running. [%s]'
                         % metadata['instance']['state'])
        self.assertTrue(metadata['instance']['displayname'], 'displayname key of metadata shoudl be True')
        self.assertTrue(metadata['instance']['availabilitydomain'],
                        'availability domain key of metadata shoudl be True')
        self.assertTrue(metadata['instance']['id'], 'OCID key of metadata shoudl be True')
        self.assertTrue(metadata['instance']['compartmentid'], 'compartment OCID key of metadata shoudl be True')

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
        self.assertIn('instance', metadata,
                      '\'instance\' not part of filtered metadata')
        self.assertIn('compartmentId', metadata['instance'],
                      '\'compartmentId\' not part of filtered instance '
                      'metadata')
        self.assertIn('ocid1.compartment.oc1..',
                      metadata['instance']['compartmentId'],
                      'Not expected value of \'compartmentId\'  of filtered '
                      'instance metadata')
        self.assertIn('vnics', metadata,
                      '\vnics\' not part of filtered instance metadata')
        self.assertIn('macAddr', metadata['vnics'][0],
                      'first VNIC of metatada do nto contain \'macAddr\' key')
        self.assertNotIn('vnicId', metadata['vnics'][0],
                         'first VNIC of metatada do nto contain \'vnicId\' key')


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOciMetadata)
    unittest.TextTestRunner().run(suite)
