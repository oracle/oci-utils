# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.


import socket
import unittest

import oci_utils
import oci_utils.oci_api
from tools.decorators import skipUnlessOCI, skipUnlessOCISDKInstalled, skipUnlessRoot, skipItAsUnresolved
from tools.oci_test_case import OciTestCase
from oci_utils.exceptions import OCISDKError


class TestOCISession(OciTestCase):
    """ OCI session Test case.
    """

    def setUp(self):
        super(TestOCISession, self).setUp()
        self._session = None

    def setUpSession(self):
        if self._session is None:
            self._session = oci_utils.oci_api.OCISession(
                auth_method=oci_utils.oci_api.DIRECT)
        return self._session

    @skipItAsUnresolved()
    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_config_file_auth(self):
        """
        Session creation test for DIRECT mode.

        Returns
        -------
            No return value.
        """
        s = oci_utils.oci_api.OCISession(auth_method=oci_utils.oci_api.DIRECT)
        self.assertIsNotNone(s, 'fail to get session using DIRECT mode')
        self.assertEqual(s.auth_method, oci_utils.oci_api.DIRECT,
                         'auth mode of returned session is not DIRECT')
        self.assertIsNone(s.signer,
                          'expected signer for DIRECT auth mode to be None')
        i = s.this_instance()
        self.assertIsNotNone(i, 'DIRECT session\'s OCI instance is None')
        self.assertEqual(i.get_display_name(), socket.gethostname(),
                         'Not expeceted instance hostname [%s <> %s]' % (
                         i.get_display_name(), socket.gethostname()))

    @skipItAsUnresolved()
    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_instance_principal_auth(self):
        """
        Session creation test for IP mode.

        Returns
        -------
            No return value.
        """
        s = oci_utils.oci_api.OCISession(auth_method=oci_utils.oci_api.IP)
        self.assertIsNotNone(s, 'fail to get session using IP mode')
        self.assertEqual(s.auth_method, oci_utils.oci_api.IP,
                         'auth mode of returned session is not IP')
        self.assertIsNotNone(s.signer,
                             'expected signer for IP auth mode to be None')
        i = s.this_instance()
        self.assertIsNotNone(i, 'IP session\'s OCI instance is None ')
        self.assertEqual(i.get_display_name(), socket.gethostname(),
                         'Not expeceted instance hostname [%s <> %s]' % (
                         i.get_display_name(), socket.gethostname()))

    @skipItAsUnresolved()
    @skipUnlessOCI()
    @skipUnlessRoot()
    @skipUnlessOCISDKInstalled()
    def test_proxy_auth(self):
        """
        Session creation test for PROXY mode.

        Returns
        -------
            No return value.
        """
        s = oci_utils.oci_api.OCISession(auth_method=oci_utils.oci_api.PROXY)
        self.assertIsNotNone(s, 'fail to get session using PROXY mode')
        self.assertEqual(s.auth_method, oci_utils.oci_api.PROXY,
                         'auth mode of returned session is not PROXY [%s]' % str(s.auth_method))
        i = s.this_instance()
        self.assertIsNotNone(i, 'PROXY session\'s OCI instance is None ')
        self.assertEqual(i.get_display_name(), socket.gethostname(),
                         'Not expeceted instance hostname [%s <> %s]' % (
                         i.get_display_name(), socket.gethostname()))

    @skipItAsUnresolved()
    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session(self):
        """
        Test OCI sessoin with wrong configuration.

        Returns
        -------
            No return value.
        """
        # invalid config file -> should fail
        with self.assertRaisesRegex(OCISDKError, 'Failed to authenticate'):
            s = oci_utils.oci_api.OCISession(
                config_file='/dev/null',
                auth_method=oci_utils.oci_api.DIRECT)

        # any form of auth
        s = oci_utils.oci_api.OCISession()
        self.assertIsNotNone(s)
        i = s.this_instance()
        self.assertIsNotNone(i)
        self.assertEqual(i.data.display_name, socket.gethostname())

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_all_compartments(self):
        """
        Test OCISession.all_compartments().

        Returns
        -------
            No return value.
        """
        _all = self.setUpSession().all_compartments()
        self.assertIsNotNone(_all, 'None list of compartment returned')
        _this_compartement = self.setUpSession().this_compartment()
        self.assertIsNotNone(_this_compartement, 'Cannot fetch our compartment')
        _my_compartment_ocid = _this_compartement.get_ocid()
        _found = False
        for _c in _all:
            self.assertTrue(
                isinstance(_c, oci_utils.impl.oci_resources.OCICompartment),
                'wrong type returned as part of compartment list')
            if _c.get_ocid() == _my_compartment_ocid:
                _found = True

        self.assertTrue(_found, 'Did not find our compartment in the list')

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_find_compartments(self):
        """
        Test OCISession.find_compartments().

        Returns
        -------
            No return value.
        """
        _c = self.setUpSession().this_compartment()
        self.assertIsNotNone(_c, 'Cannot fetch our compartment')
        _c_list = self.setUpSession().find_compartments(_c.get_display_name())
        self.assertTrue(len(_c_list) == 1, 'wrong list length returned')
        self.assertTrue(_c_list[0] == _c, 'wrong self compartment returned')

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_find_compartments_not_found(self):
        """
        Test OCISession.find_compartments() with wrong name.

        Returns
        -------
            No return value.
        """
        _c_list = self.setUpSession().find_compartments('_do_not_exits__')
        self.assertTrue(len(_c_list) == 0,
                        'wrong list length returned, shoudl be empty')

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_all_vcns(self):
        """
        Test OCISession.all_vcns().

        Returns
        -------
            No return value.
        """
        _all = self.setUpSession().all_vcns()
        self.assertIsNotNone(_all, 'None list of VCNS returned')
        for _c in _all:
            self.assertTrue(isinstance(_c, oci_utils.impl.oci_resources.OCIVCN),
                            'wrong type returned as part of compartment list')

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_find_vcns(self):
        """
        Test OCISession.find_vcns().

        Returns
        -------
             No return value.
        """
        _all = self.setUpSession().all_vcns()
        if len(_all) > 0:
            _c_list = self.setUpSession().find_vcns(_all[0].get_display_name())
            self.assertTrue(len(_c_list) == 1, 'wrong list length returned')
            self.assertTrue(_c_list[0] == _all[0],
                            'wrong self compartment returned')

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_find_vcns_not_found(self):
        """
        Test OCISession.find_vcns() with wrong name.

        Returns
        -------
            No return value.
        """

        _c_list = self.setUpSession().find_vcns('_do_not_exits__')
        self.assertTrue(len(_c_list) == 0,
                        'wrong list length returned, shoudl be empty')

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_all_subnets(self):
        """
        Test OCISession.all_subnets.

        Returns
        -------
            No return value.
        """
        _all = self.setUpSession().all_subnets()
        self.assertIsNotNone(_all, 'None list of subnets returned')

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_get_subnet(self):
        """
        Test OCISession.get_subnet.

        Returns
        -------
            No return value.
        """
        _all = self.setUpSession().all_subnets()
        if len(_all) > 0:
            _s = self.setUpSession().get_subnet(_all[0].get_ocid())
            self.assertEqual(_s, _all[0],
                             'Wrong subnet returned by search by id')

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_find_subnets(self):
        """
        Test OCISession.find_subnet.

        Returns
        -------
            No return value.
        """
        _all = self.setUpSession().all_subnets()
        if len(_all) > 0:
            _s = self.setUpSession().find_subnets('%s*' % _all[0].get_display_name())
            self.assertEqual(_s[0], _all[0], 'Wrong subnet returned by search')

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_find_subnets_not_found(self):
        """
        Test OCISession.subnet_not_found.

        Returns
        -------
            No return value.
        """
        _s = self.setUpSession().find_subnets('__do_not_exits__')
        self.assertIsNotNone(_s, 'None returned empty list expected')
        self.assertTrue(len(_s) == 0,
                        'not empty list returned empty list expected')

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_all_instances(self):
        """
        Test OCISession.all_instances.

        Returns
        -------
            No return value.
        """
        _all = self.setUpSession().all_instances()
        self.assertIsNotNone(_all, 'None list of instances returned')
        self.assertTrue(len(_all) >= 1, 'empy list of instances returned')
        self.assertTrue(self.setUpSession().this_instance() in _all,
                        'our instance not returned as part of all instances')

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_find_instances(self):
        """
        Test OCISession.find_instance.

        Returns
        -------
            No return value.
        """
        _f = self.setUpSession().find_instances(
            self.setUpSession().this_instance().get_display_name())
        self.assertIsNotNone(_f, 'None list of instances returned')
        self.assertTrue(_f[0] == self.setUpSession().this_instance())

        _all_wildcard = sorted(self.setUpSession().find_instances('.*'))
        _all = sorted(self.setUpSession().all_instances())
        self.assertFalse(cmp(_all_wildcard, _all))
