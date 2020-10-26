# Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import logging
from unittest import TestCase

from .tree_config import TreeConfigParser


class OciTestCase(TestCase):
    """Base class for OCI util test case
    """
    test_config_dir = None

    @classmethod
    def _set_base(cls, namespace):
        """Set test base directory.
        from the base we derived the path to test configuration

        Parameters
        ----------
        namespace : string
            the tests base dir

        """
        OciTestCase.test_config_dir = namespace

    def setUp(self):
        """Test setUp method
            NOTE : any subclass implementation must call it during their own
            setUp phase
        """
        self.properties = TreeConfigParser(OciTestCase.test_config_dir, self)
        self.logger = logging.getLogger('oci-utils.%s' % self.__class__.__name__)
