# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.


import os
import socket
import unittest

import oci_utils
import oci_utils.oci_api
from tools.decorators import skipUnlessOCI, skipUnlessOCISDKInstalled, skipUnlessRoot, skipItAsUnresolved
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'


def cmp(a, b):
    return (a > b) - (a < b)


class TestOCISession(OciTestCase):
    """ OCI session Test case.
    """

    def setUp(self):
        super(TestOCISession, self).setUp()
        self._session = None

    def setUpSession(self):
        if self._session is None:
            self._session = oci_utils.oci_api.OCISession(
                authentication_method=oci_utils.oci_api.IP)
        #
        # session is not enough
        if self._session.this_instance() is None:
            self._session = oci_utils.oci_api.OCISession(
                authentication_method=oci_utils.oci_api.DIRECT)
        #
        # session is not enough
        if self._session.this_instance() is None:
            self._session = oci_utils.oci_api.OCISession(
                authentication_method=oci_utils.oci_api.PROXY)
        #
        # session is not enough
        if self._session.this_instance() is None:
            #
            # no way to create a correct session, all tests will fail.
            pass
        return self._session

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_config_file_auth(self):
        """
        Session creation test for DIRECT mode.

        Returns
        -------
            No return value.
        """
        s = oci_utils.oci_api.OCISession(authentication_method=oci_utils.oci_api.DIRECT)
        self.assertIsNotNone(s, 'fail to get session using DIRECT mode.')
        self.assertEqual(s.auth_method, oci_utils.oci_api.DIRECT, 'Auth mode of returned session is not DIRECT.')
        self.assertIsNone(s.signer, 'Expected signer for DIRECT auth mode to be None.')
        i = s.this_instance()
        self.assertIsNotNone(i, 'DIRECT session\'s OCI instance is None.')
        self.assertEqual(i.get_display_name().replace('_', '-').lower(), socket.gethostname(),
                         'Not expected instance hostname [%s <> %s].'
                         % (i.get_display_name().replace('_', '-').lower(), socket.gethostname()))

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_instance_principal_auth(self):
        """
        Session creation test for IP mode.

        Returns
        -------
            No return value.
        """
        s = oci_utils.oci_api.OCISession(authentication_method=oci_utils.oci_api.IP)
        self.assertIsNotNone(s, 'Fail to get session using IP mode')
        self.assertEqual(s.auth_method, oci_utils.oci_api.IP, 'Auth mode of returned session is not IP.')
        self.assertIsNotNone(s.signer, 'Expected signer for IP auth mode to be None.')
        i = s.this_instance()
        self.assertIsNotNone(i, 'IP session\'s OCI instance is None.')
        self.assertEqual(i.get_display_name().replace('_', '-').lower(), socket.gethostname(),
                         'Not expected instance hostname [%s <> %s].'
                         % (i.get_display_name().replace('_', '-').lower(), socket.gethostname()))

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
        s = oci_utils.oci_api.OCISession(authentication_method=oci_utils.oci_api.PROXY)
        self.assertIsNotNone(s, 'Fail to get session using PROXY mode.')
        self.assertEqual(s.auth_method, oci_utils.oci_api.PROXY,
                         'Auth mode of returned session is not PROXY [%s].' % str(s.auth_method))
        i = s.this_instance()
        self.assertIsNotNone(i, 'PROXY session\'s OCI instance is None.')
        self.assertEqual(i.get_display_name().replace('_','-'), socket.gethostname(),
                         'Not expected instance hostname [%s <> %s].' % (i.get_display_name().replace('_','-'), socket.gethostname()))

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session(self):
        """
        Test OCI session with wrong configuration.

        Returns
        -------
            No return value.
        """
        # invalid config file -> should fail
        with self.assertRaisesRegex(Exception, 'Failed to authenticate.'):
            s = oci_utils.oci_api.OCISession(
                config_file='/dev/null',
                authentication_method=oci_utils.oci_api.DIRECT)

        # any form of auth
        s = oci_utils.oci_api.OCISession()
        self.assertIsNotNone(s)
        i = s.this_instance()
        self.assertIsNotNone(i)
        self.assertEqual(i.get_display_name().replace('_','-'), socket.gethostname())

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
        self.assertIsNotNone(_all, 'None list of compartment returned.')
        _this_compartment = self.setUpSession().this_compartment()
        self.assertIsNotNone(_this_compartment, 'Cannot fetch our compartment.')
        _my_compartment_ocid = _this_compartment.get_ocid()
        _found = False
        for _c in _all:
            self.assertTrue(isinstance(_c, oci_utils.impl.oci_resources.OCICompartment),
                            'Wrong type returned as part of compartment list.')
            if _c.get_ocid() == _my_compartment_ocid:
                _found = True

        self.assertTrue(_found, 'Did not find our compartment in the list.')

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
        self.assertIsNotNone(_c, 'Cannot fetch our compartment.')
        _c_list = self.setUpSession().find_compartments(_c.get_display_name())
        self.assertTrue(len(_c_list) == 1, 'Wrong list length returned.')
        self.assertTrue(_c_list[0] == _c, 'Wrong self compartment returned.')

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
        self.assertTrue(len(_c_list) == 0, 'Wrong list length returned, should be empty.')

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
        self.assertIsNotNone(_all, 'None list of VCNS returned.')
        for _c in _all:
            self.assertTrue(isinstance(_c, oci_utils.impl.oci_resources.OCIVCN),
                            'Wrong type returned as part of compartment list.')

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
            self.assertTrue(len(_c_list) == 1, 'Wrong list length returned.')
            self.assertTrue(_c_list[0] == _all[0], 'Wrong self compartment returned.')

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
        self.assertTrue(len(_c_list) == 0, 'Wrong list length returned, should be empty.')



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
            self.assertEqual(_s[0], _all[0], 'Wrong subnet returned by search.')

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
        self.assertIsNotNone(_s, 'None returned empty list expected.')
        self.assertTrue(len(_s) == 0, 'Not empty list returned empty list expected.')

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
        self.assertIsNotNone(_all, 'None list of instances returned.')
        self.assertTrue(len(_all) >= 1, 'zempyy list of instances returned.')
        self.assertTrue(self.setUpSession().this_instance() in _all,
                        'Our instance not returned as part of all instances.')

    @skipUnlessOCI()
    @skipUnlessOCISDKInstalled()
    def test_oci_session_find_instances(self):
        """
        Test OCISession.find_instance.

        Returns
        -------
            No return value.
        """
        _f = self.setUpSession().find_instances(self.setUpSession().this_instance().get_display_name())
        self.assertIsNotNone(_f, 'None list of instances returned.')
        self.assertTrue(_f[0] == self.setUpSession().this_instance())

        _all_wildcard = sorted(self.setUpSession().find_instances('.*'))
        _all = sorted(self.setUpSession().all_instances())
        self.assertFalse(cmp(_all_wildcard, _all))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOCISession)
    unittest.TextTestRunner().run(suite)
