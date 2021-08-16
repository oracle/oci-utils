# Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import xml.etree.ElementTree as ET

import os
import logging

__all__ = ['getCommandStore', 'setCommandStore']

_logger = logging.getLogger('oci-utils-tests')

_default_repo_path = '/tmp/commands.xml'
_store = None


def setCommandStore(store):
    global _store
    _store = store


def getCommandStore():
    global _store
    if _store is None:
        _store = Store(_default_repo_path)
    return _store


class Store(object):
    def __init__(self, repo_filename):
        self.repo_filename = repo_filename
        if os.path.exists(self.repo_filename) and os.stat(self.repo_filename).st_size > 0:
            # load it first
            _logger.info('load command from [%s]', self.repo_filename)
            self.commandRoot = ET.parse(self.repo_filename).getroot()
        else:
            self.commandRoot = ET.ElementTree(ET.Element('commands')).getroot()

    def _getCommandByKey(self, key):
        _logger.debug('fetching command [%s]' % key)
        for command in self.commandRoot.findall('command'):
            if command.get('key') == key:
                _logger.debug('fetched command [%s]' % str(command))
                return command
        _logger.warning('unknown command key [%s]' % key)
        return None

    def store(self, storableObject):
        """
        Store to the repository a Storable instance
        see Storable.toXMLElement()
        if the storable with the same key is already present the store
        is ignored

        Parameters
        ----------
        storableObject : storable.Storable
            a Storable object
        Returns
        -------
        boolean
          True if store has happend False otherwise (command already exists)
        """
        if self._getCommandByKey(storableObject.getKey()) is not None:
            _logger.debug('new store aborted key [%s] already found' % storableObject.getKey())
            return False

        _toxml = storableObject.toXMLElement()

        self.commandRoot.append(_toxml)

        return True

    def fetch(self, key):
        return self._getCommandByKey(key)

    def flush(self):
        """flush the tree into repository file
        """

        ET.ElementTree(self.commandRoot).write(self.repo_filename)
