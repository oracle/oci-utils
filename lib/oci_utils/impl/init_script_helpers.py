# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os.path
import logging
from . import sudo_utils



from ..impl import SYSTEMCTL_CMD

_logger = logging.getLogger('oci-utils.init-script')


class InitScriptBase():
    """
    base class for sysV init helpers
    """
    _BASE_DIR = '/etc/init.d'


class ServiceManager():
    def __init__(self, name):
        """
        Instantiate a new manager for named service
        parameter:
            name : service name
        """
        self.name = name

    def start(self):
        """
        Start the init script
        raise
          Exception if start has failed
        """
        raise Exception('not implemented')

    def stop(self):
        """
        Stop the init script
        raise
          Exception if stop has failed
        """
        raise Exception('not implemented')

    def remove(self):
        """
        Removes the init script from the system
        """
        raise Exception('not implemented')


class SystemdServiceManager(ServiceManager):
    """
    Manager for systemd type of init scripts
    """

    def start(self):
        if sudo_utils.call([SYSTEMCTL_CMD, 'enable', '--now', self.name]):
            raise Exception('start of systend unit has failed')

    def stop(self):
        if sudo_utils.call([SYSTEMCTL_CMD, 'disable', '--now', self.name]):
            raise Exception('stop of systend unit has failed')

    def remove(self):
        if sudo_utils.call([SYSTEMCTL_CMD, 'disable', '--now', self.name]):
            raise Exception('stop of systend unit has failed')
        sudo_utils.delete_file('/etc/systemd/system/%s.service' % self.name)


class InitScriptManager(InitScriptBase, ServiceManager):
    """
    Manager for sysV type of init scripts
    """

    def __init__(self, name):
        """
        Instantiate a new manger
        parameter:
            name : service name , i.e filename
        """
        ServiceManager.__init__(self, name)
        self.path = os.path.join(InitScriptBase._BASE_DIR, self.name)

    def start(self):
        _logger.debug('Starting the service')
        if sudo_utils.call([self.path, 'start']):
            raise Exception('start of init script has failed')

    def stop(self):
        _logger.debug('Stopping the service')
        if sudo_utils.call([self.path, 'stop']):
            raise Exception('stop of init script has failed')

    def remove(self):
        _logger.debug('Removing file  %s' % self.path)
        return sudo_utils.delete_file(self.path)


class ServiceGenerator():
    """
    base class for service generators
    """

    def __init__(self, name, description):
        """
        Creates a new genertor

        Parameter:
        ----------
        name : str
            service name
        description: str
            service description
        """

        self.name = name
        self.decription = description
        self.requiredDependencies = []

    def addRequiredDependency(self, dependencyName):
        """
        add a dependency to this service
        Required-Start attribute in the LSB header
        parameters:
            dependencyName : dependency name
        """
        self.requiredDependencies.append(dependencyName)


class SystemdServiceGenerator(ServiceGenerator):
    """
    systemd type service generator
    """

    def __init__(self, name, description):
        ServiceGenerator.__init__(self, name, description)
        self.env = []

    def generate(self):
        """
        Generates this service.
        Add a new unit in /etc/systemd/system/ called <service name>.service

        """
        _ouput_file = '/etc/systemd/system/%s.service' % self.name

        res = sudo_utils.create_file(_ouput_file, '666')
        if res != 0:
            raise Exception('Cannot create the script file')

        file = open(_ouput_file, "w")

        file.write('[Unit]\n')
        file.write('Description=%s\n' % self.decription)
        for dep in self.requiredDependencies:
            file.write('After=%s.service\n' % dep)
        file.write('[Service]\n')
        file.write('Type=oneshot\n')
        file.write('RemainAfterExit=yes\n')
        file.write('Restart=no\n')
        for env in self.env:
            file.write('Environment=%s=%s\n' % env)
        file.write('ExecStart=/usr/libexec/oci-kvm-network-script start\n')
        file.write('ExecStop=/usr/libexec/oci-kvm-network-script stop\n')
        file.write('\n')
        file.close()
        sudo_utils.set_file_mode(_ouput_file, '755')

    def setEnvironment(self, vars):
        """
        Sets environement variable for the servivce
        parameers:
            vars: tuple of tuple ((var name,var value),...)
        """
        self.env = vars


class InitScriptGenerator(ServiceGenerator, InitScriptBase):
    """
    sysV type service generator
    """

    def __init__(self, name, description):
        ServiceGenerator.__init__(self, name, description)
        self.provides = None
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
         Exception : error about file creation
        """
        _ouput_file = os.path.join(InitScriptBase._BASE_DIR, self.name)

        if self.methods_implementations is None:
            raise Exception('No methods defined')

        res = sudo_utils.create_file(_ouput_file, '666')
        if res != 0:
            raise Exception('Cannot create the script file')

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
