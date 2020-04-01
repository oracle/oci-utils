# Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

__all__ = ['Storable']


class Storable(object):
    """
    Base class for object storable in store
    """

    def toXMLElement(self):
        """
        return an XMLElement of this instance
        Storable object are expected to implement this
        Returned element is expected to have an attribute named 'key'

        Returns
        -------
        xml.etree.ElementTree.Element
            this as XML element
        """
        raise Exception('subclass must implement this')

    def getKey(self):
        """
        Return the unique identifier of this instance
        """
        raise Exception('subclass must implement this')
