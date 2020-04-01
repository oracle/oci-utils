# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import unittest

from tools.decorators import skipUnlessRoot
from tools.oci_test_case import OciTestCase

class TestExecHelpers(OciTestCase):
    """ Test around lib/oci_utils/impl/sudo_utils.py.
    """
    @skipUnlessRoot()
    def test_call(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.
        """
        import oci_utils.impl.sudo_utils
        self.assertFalse(oci_utils.impl.sudo_utils.call(['/bin/ls', '/']))
