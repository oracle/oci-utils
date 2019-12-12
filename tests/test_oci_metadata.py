# Copyright (c) 2017, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

import unittest

from decorators import skipUnlessOCI
from oci_utils.metadata import InstanceMetadata as InstanceMetadata


class TestOciMetadata(unittest.TestCase):
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
        metadata = InstanceMetadata().get()
        self.assertNotEqual(metadata, [], 'Instanciated metatde is empty')
        self.assertTrue(metadata['instance'],
                        'instance key of metadata should be True')
        self.assertIn(u'region', metadata['instance'],
                      'metadata do not contain region information')
        self.assertIn(metadata['instance']['region'],
                      ['phx', 'iad', 'fra', 'lhr', 'uk-london-1'],
                      'instance region [%s] not part of possible values [%s]'
                      % (
                      metadata['instance']['region'],
                      ['phx', 'iad', 'fra', 'lhr']))
        self.assertIn(u'state', metadata['instance'],
                      'Returned instance metadata do not contain any '
                      '\'state\' key')
        self.assertEquals(metadata['instance']['state'], 'Running',
                          'exepcetd statte of OCI instance to be running. ['
                          '%s]' %
                          metadata['instance']['state'])

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
        self.assertIn(u'instance', metadata,
                      '\'instance\' not part of filtered metadata')
        self.assertIn(u'compartmentId', metadata['instance'],
                      '\'compartmentId\' not part of filtered instance '
                      'metadata')
        self.assertIn('ocid1.compartment.oc1..',
                      metadata['instance']['compartmentId'],
                      'Not expected value of \'compartmentId\'  of filtered '
                      'instance metadata')
        self.assertIn(u'vnics', metadata,
                      '\vnics\' not part of filtered instance metadata')
        self.assertIn(u'macAddr', metadata['vnics'][0],
                      'first VNIC of metatada do nto contain \'macAddr\' key')
        self.assertNotIn(u'vnicId', metadata['vnics'][0],
                         'first VNIC of metatada do nto contain \'vnicId\' key')


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOciMetadata)
    unittest.TextTestRunner().run(suite)
