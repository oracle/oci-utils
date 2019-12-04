
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import unittest

from decorators import (skipUnlessOCI,skipUnlessRoot)


class TestVnicUtils(unittest.TestCase):
    """
    VNICUtils Test cases.
    """

    @skipUnlessOCI()
    def test_create_instance(self):
        """
        Test VNICUtils.new.

        Returns
        -------
            No return value.
        """
        import oci_utils.vnicutils
        self.assertIsNotNone(oci_utils.vnicutils.VNICUtils())

    @skipUnlessRoot()
    def test_run_script(self):
        """
        Test VNICUtils._run_sec_vcni_script()

        Returns
        -------
            No return value.
        """
        import oci_utils.vnicutils
        (code,_) = oci_utils.vnicutils.VNICUtils()._run_sec_vnic_script([])
        self.assertEqual(code,0,'script did not exit on 0')

    @skipUnlessRoot()
    def test_run_script_show(self):
        """
        Test VNICUtils._run_sec_vcni_script(['-s'])

        Returns
        -------
            No return value.
        """
        import oci_utils.vnicutils
        vu = oci_utils.vnicutils.VNICUtils()
        vu.get_vnic_info()
        (code,out) = vu._run_sec_vnic_script(['-s'])
        if code != 0:
            print ('script output: %s' % out)
            self.fail('script did not exit on 0')
        
