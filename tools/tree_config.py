
# Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.


import os.path
import configparser

import logging

_logger = logging.getLogger('oci-utils.TreeConfigParser')


class TreeConfigParser(configparser.ConfigParser):
    """
    Wrapper around ConfigParser.ConfigParser()
    Objects to handle a hierarchy of configuration
    Configuration are organized as a directory based hierarchy
    Each stage may contain a property.cfg file
    Hierarchy is built based on class and module name
    ex:
       for class foo.bar.Foo properties can be found at 4 different
       levels Foo, foo.bar , foo and <root>
        /properties.cfg
        /foo/properties.cfg
        /foo/bar/properties.cfg
        /foo/bar/Foo/properties.cfg
    For a given property, all stage are checked from
    """

    def __init__(self, base, obj):
        """Creates a new TreeConfig

        Parameters
        ----------
        base : string
            base directory of config hierarchy
        obj : object
            entity from which the hierarchy will be built.
            obj.__name__
            obj.__class__.__name__
            obj.__module__.split('.')
        """
        assert isinstance(obj, object), 'Invalid object passed'
        configparser.ConfigParser.__init__(self)

        if base is None or not os.path.isdir(base):
            _logger.info('Invalid base : [%s], skipping load', base)
        else:
            _elems = [base]
            _elems.extend(obj.__module__.split('.'))
            _elems.append(obj.__class__.__name__)
            if hasattr(obj, '__name__'):
                _elems.append(obj.__name__)
            _p = ''
            _all_files = []
            while True:
                try:
                    _p = os.path.join(_p, _elems.pop(0))
                    _all_files.append(os.path.join(_p, 'properties.cfg'))
                except IndexError:
                    # end of elems list
                    break
            _logger.debug('all properties files read : %s', self.read(_all_files))

    def get_property(self, key):
        try:
            return self.get('DEFAULT', key)
        except configparser.NoOptionError as e:
            _logger.warning('Missing option [%s] in test configuration', key)

    def get(self, section, option, **kargs):
        try:
            return configparser.ConfigParser.get(self, section, option, **kargs)
        except(configparser.NoOptionError, configparser.NoSectionError) as e:
            _logger.warning('Missing option [%s/%s] in test configuration', section, option)

    def items(self, section):
        try:
            return configparser.ConfigParser.items(self, section)
        except configparser.NoSectionError as e:
            _logger.warning('Missing option [%s] in test configuration', section)

    def write(self, fileobject):
        raise NotImplementedError('Not supported operation')


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    c = TreeConfigParser('/var/tmp/', configparser.ConfigParser())

    for s in c.sections():
        print('SECTION %s' % s)
        for (name, value) in c.items(s):
            print('\t%s=%s' % (name, value))
