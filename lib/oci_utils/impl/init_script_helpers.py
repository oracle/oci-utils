#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os.path
import sudo_utils

import logging

from init_script_templates import _kvm_network_script_tmpl

_logger = logging.getLogger('oci-utils.init-script')


class InitScriptBase(object):
    _BASE_DIR = '/etc/init.d'


class InitScriptManager(InitScriptBase):
    """
    helpers class to manage init scrip
    """

    def __init__(self, name):
        self.name = name
        self.path = os.path.join(InitScriptBase._BASE_DIR, self.name)

    def start(self):
        """
        start the init script
        raise
          StandardError if start has failed
        """
        _logger.debug('calling start on %s' % self.path)
        if sudo_utils.call([self.path, 'start']):
            raise StandardError('start of init script has failed')

    def stop(self):
        """
        stop the init script
        raise
          StandardError if stop has failed
        """
        _logger.debug('calling stop on %s' % self.path)
        if sudo_utils.call([self.path, 'stop']):
            raise StandardError('stop of init script has failed')

    def remove(self):
        """
        removes the init script from the system
        """
        _logger.debug('removing file  %s' % self.path)
        return sudo_utils.delete_file(self.path)


class InitScriptGenerator(InitScriptBase):

    def __init__(self, name, description):
        self.name = name
        self.decription = description
        self.provides = None
        self.requiredDependencies = []
        self.start_levels = []
        self.stop_levels = []

    def _write_header(self, file):
        """
        write script header to file
        parameter:
           file : file to write to
        """

        file.write('#! /bin/bash\n\n')

        file.write('### BEGIN INIT INFO\n')
        file.write('# Provides: %s\n' % self.name)
        if self.requiredDependencies:
            file.write('# Should-Start: %s\n' % ' '.join(self.requiredDependencies))
            file.write('# Should-Stop: %s\n' % ' '.join(self.requiredDependencies))
        if len(self.start_levels) != 0:
            file.write('# Default-Start:  %s\n' % ' '.join([str(level) for level in self.start_levels]))
        if len(self.stop_levels) != 0:
            file.write('# Default-Stop:  %s\n' % ' '.join([str(level) for level in self.stop_levels]))

        file.write('# Short-Description: %s\n' % self.decription)
        file.write('# Description: %s\n' % self.decription)

        file.write('### END INIT INFO\n')

        file.write('\n\n. /etc/init.d/functions\n')


class SimpleInitScriptGenerator(InitScriptGenerator):
    """
    Helper class used to generate init scripts
    """

    def __init__(self, name, description):
        InitScriptGenerator.__init__(self, name, description)
        self.start_method_body = None
        self.stop_method_body = None
        self.status_method_body = None

    def addRequiredDependency(self, dependencyName):
        """
        add a dependency to this service
        Required-Start attribute in the LSB header
        parameters:
            dependencyName : dependency name
        """
        self.requiredDependencies.append(dependencyName)

    def setMethodsBody(self, methodsBody):
        """
        Set the code of  methods execution
        parameters:
            cmd : command as list of string
        """
        self.methods_implementations = methodsBody

    def setStartRunlevels(self, levels):
        """
        add run levels the service should be started
        Default-Start attribute in the LSB header
        parameters:
            levels : list of levels as number
        """
        self.start_levels = levels

    def setStopRunlevels(self, levels):
        """
        add run levels the service should be stopped
        Default-Stop attribute in the LSB header
        If not specified will be the same as start level
        parameters:
            levels : list of levels as number
        raise :
           Standard : file creation has failed
        """
        self.stop_levels = levels

    def generate(self):
        """
        generates the script
        raise
         StandardError : error about file creation
        """
        _ouput_file = os.path.join(InitScriptBase._BASE_DIR, self.name)

        if self.methods_implementations is None:
            raise StandardError('No methods defined')

        res = sudo_utils.create_file(_ouput_file, '666')
        if res != 0:
            raise StandardError('Cannot create the script file')

        file = open(_ouput_file, "w")

        self._write_header(file)

        file.write('\n\n')

        file.write(self.methods_implementations)

        file.write("""case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    status)
        status
        ;;
    *)
        exit 1
        ;;
esac
exit $?
""")
        file.write('\n')
        file.close()
        sudo_utils.set_file_mode(_ouput_file, '755')
