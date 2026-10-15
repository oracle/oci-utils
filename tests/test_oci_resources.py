# Copyright (c) 2026 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from oci_utils.impl.oci_resources import OCIInstance


class TestOCIInstanceAllVnics(unittest.TestCase):
    def test_skips_attachments_without_vnic_ids(self):
        session = Mock()
        network_client = session.get_network_client.return_value
        instance = OCIInstance.__new__(OCIInstance)
        instance._oci_session = session
        instance._data = SimpleNamespace(compartment_id='compartment')
        instance._ocid = 'instance'

        first_attached = SimpleNamespace(vnic_id='vnic-1', lifecycle_state='ATTACHED')
        detached = SimpleNamespace(vnic_id=None, lifecycle_state='DETACHED')
        detaching = SimpleNamespace(vnic_id='vnic-detaching', lifecycle_state='DETACHING')
        missing_id = SimpleNamespace(vnic_id=None, lifecycle_state='ATTACHED')
        empty_id = SimpleNamespace(vnic_id='', lifecycle_state='ATTACHED')
        blank_id = SimpleNamespace(vnic_id=' ', lifecycle_state='ATTACHED')
        second_attached = SimpleNamespace(vnic_id='vnic-2', lifecycle_state='ATTACHED')
        attachments = [first_attached, detached, detaching, missing_id, empty_id, blank_id, second_attached]
        network_client.get_vnic.side_effect = lambda vnic_id: SimpleNamespace(data=vnic_id)

        with patch('oci_utils.impl.oci_resources.oci_sdk.pagination.list_call_get_all_results',
                   return_value=SimpleNamespace(data=attachments)) as list_attachments, \
                patch('oci_utils.impl.oci_resources.OCIVNIC',
                      side_effect=lambda *args, **kwargs: kwargs['attachment_data']):
            vnics = instance.all_vnics()

        list_attachments.assert_called_once_with(session.get_compute_client.return_value.list_vnic_attachments,
                                                 compartment_id='compartment', instance_id='instance')
        self.assertEqual([call('vnic-1'), call('vnic-2')], network_client.get_vnic.call_args_list)
        self.assertEqual([first_attached, second_attached], vnics)


if __name__ == '__main__':
    unittest.main()
