
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
        raise StandardError('subclass must implement this')

    def getKey(self):
        """
        Return the unique identifier of this instance
        """
        raise StandardError('subclass must implement this')
