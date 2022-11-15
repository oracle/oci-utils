
# Copyright (c) 2020, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Build an rpm from oci-utils.
"""
import fnmatch
import os
import subprocess
import sys
import logging
from distutils.core import Command
from distutils.dist import Distribution
from distutils.errors import DistutilsExecError
from setuptools.command.test import test as TestCommand

from distutils import log


def get_reloc_path(path):
    """
    For relative path get the absolute path computed
    against the current nodule path.

    Parameters
    ----------
    path : str
          path to be computed

    Returns
    -------
        The absolute path
    """
    if os.path.isabs(path):
        return path
    return os.path.join(os.path.dirname(__file__), path)


sys.path.insert(0, get_reloc_path('lib'))
sys.path.insert(0, get_reloc_path('tools'))

try:
    from setuptools import setup, find_packages
except ImportError:
    print("oci-utils needs setuptools in order to build. Install it using "
          "your package manager (usually python-setuptools) or via pip (pip "
          "install setuptools).")
    sys.exit(1)


def read(fname):
    """
    Read a file.

    Parameters
    ----------
    fname : str
        The full path of the file.

    Returns
    -------
        The contents of the file.
    """
    return open(get_reloc_path(fname)).read()


install_requirements = read('requirements.txt').splitlines()


def get_content(base, pattern, recursive=True):
    """
    Get all python files in dir and subdir.

    Parameters
    ----------
        base: str
           basedirectory
        pattern: str
            filename pattern like *.py
        recursive: boolean
            do search down to subdirs
    return
    -------
        List of files
    """
    tools_l = []
    if recursive:
        for (dirpath, dirnames, filenames) in os.walk(base):
            for filename in filenames:
                if fnmatch.fnmatch(filename, pattern):
                    tools_l.append(os.path.join(dirpath, filename))

    else:
        for entry in os.listdir(base):
            if os.path.isfile(os.path.join(base, entry)) and fnmatch.fnmatch(entry, pattern):
                tools_l.append(os.path.join(base, entry))
    return tools_l


class oci_tests(TestCommand):
    """ Test class.
    """
    description = 'run OCI unittest'

    TestCommand.user_options.extend([
        ('tests-base=', None, 'Specify the namespace for test properties')
    ])

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.tests_base = None

    def finalize_options(self):
        TestCommand.finalize_options(self)
        if self.tests_base is None or not os.path.isdir(self.tests_base):
            self.tests_base = None
            log.warn('Warning: tests_base not found or missing !!')
        else:
            from tools.execution.store import (setCommandStore, Store)
            setCommandStore(Store(os.path.join(self.tests_base, 'commands.xml')))
        if self.test_runner:
            import tools.decorators
            tools.decorators._run_under_recorder = True

    def run(self):
        logging.basicConfig(level=logging.WARNING)
        if self.tests_base:
            import tools.oci_test_case
            tools.oci_test_case.OciTestCase._set_base(self.tests_base)
        TestCommand.run(self)


class oci_validation_tests(Command):
    """ Runs all OCI tests on newly provisionned instance
    """
    description = 'run OCI production tests'
    user_options = [('rpm-dir=', None, 'directory where to find oci-utils rpms, of not provided, rpmn are created automatically'),
                    ('tf-config=', None, 'path to provisionning and tests variables'),
                    ('keep-instance', None, 'By default, when validation is successful, the oci instance is deleted. ')]
    boolean_options = ['keep-instance']

    def finalize_options(self):
        """
        No action.

        Returns
        -------
            No return value.
        """
        if self.tf_config is None:
            raise Exception("Parameter --tf-config is missing")

    def initialize_options(self):
        """
        Initialisation.

        Returns
        -------
            No return value.
        """
        self.rpm_dir = None
        self.tf_config = None
        self.keep_instance = False

    def run(self):
        """
        Run the validation

        Returns
        -------
            No return value.

        Raises
        ------
            DistutilsExecError
                On any error.
        """
        log.info("Runnig oci_validation_tests command now...")

        if self.rpm_dir is None:
            log.info("Creating RPMs now...")
            self.run_command('create_rpm')
            self.rpm_dir = self.distribution.get_option_dict('create_rpm')['rpm_top_dir'][1]
            self.rpm_dir = "%s/RPMS/noarch/" % self.rpm_dir

        ec = subprocess.call(('/usr/local/bin/terraform', 'init', 'tools/provisionning/test_instance'))
        if ec != 0:
            raise DistutilsExecError("Terraform configuration initialisation failed")
        ec = subprocess.call(('/usr/local/bin/terraform', 'apply', '-var', 'oci_utils_rpms_dir=%s' % self.rpm_dir, '-var-file=%s' %
                              self.tf_config, '-auto-approve', 'tools/provisionning/test_instance/'))
        if ec != 0:
            raise DistutilsExecError("validation execution failed")

        if not self.keep_instance:
            subprocess.call(('/usr/local/bin/terraform', 'destroy', '-var', 'oci_utils_rpms_dir=%s' % self.rpm_dir, '-var-file=%s' %
                             self.tf_config, '-auto-approve', 'tools/provisionning/test_instance/'))


class oci_migrate_tests(TestCommand):
    """ Run oci-image-migrate unittests
    """
    description = 'run OCI image migrate unittest'
    TestCommand.user_options.extend([
        ('tests-base=', None, 'Specify the namespace for test properties')
    ])

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.tests_base = None

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.tests_base = None

    def run(self):
        logging.basicConfig(level=logging.WARNING)
        if self.tests_base:
            import tools.oci_test_case
            tools.oci_test_case.OciTestCase._set_base(self.tests_base)
        TestCommand.run(self)


class print_recorded_commands(Command):
    description = 'pretty print of recorded commands'
    user_options = [
        ('tests-base=', None, 'Specify the namespace for test properties')
    ]

    def finalize_options(self):
        if self.tests_base and not os.path.isdir(self.tests_base):
            self.tests_base = None
            log.warn('Warning: tests_base not found')

    def initialize_options(self):
        self.tests_base = None

    def run(self):
        import xml.dom.minidom
        print((xml.dom.minidom.parse(os.path.join(self.tests_base, 'commands.xml')).toprettyxml()))


class create_rpm(Command):
    """
    Build an RPM of oci_utils.
    Setuptools provides bdist_rpm command but it does not (as we speak) support
    custom spec file
    The run() method call sdist command to build the tarbal and then rpmbuild
    against our own spec file

    Attributes
    ----------
        rpm_top_dir : str
            Root directory for rpmbuild.
        spec_file_path : str
            Path for spec files.
    """
    description = 'Build an RPM base on tarball generated by sdist command'
    user_options = [('rpm-top-dir=', 'D', 'rpm to directory'), ('spec-file-path=', 'S', 'path to spec file')]

    def finalize_options(self):
        """
        No action.

        Returns
        -------
            No return value.
        """
        pass

    def initialize_options(self):
        """
        Initialisation.

        Returns
        -------
            No return value.
        """
        self.rpm_top_dir = None
        self.spec_file_path = None

    def run(self, do_cleanup=True):
        """
        Run the actual sdist command and create the tarball under tarball_dir.

        Returns
        -------
            No return value.

        Raises
        ------
            DistutilsExecError
                On any error.
        """
        log.info("Running sdist command now...")
        self.run_command('sdist')
        log.info("Tarball created, building the RPM now...")
        _cwd = os.path.dirname(os.path.abspath(__file__))
        log.info('Current wd [%s]' % _cwd)
        redefined_top_dir = os.path.join(_cwd, self.rpm_top_dir)
        spec_file_abs_path = os.path.join(_cwd, self.spec_file_path)
        v_opt = '--quiet'
        if self.verbose:
            v_opt = '-v'

        if do_cleanup:
            rpmbuild_cmd = ('/bin/rpmbuild',
                            v_opt,
                            '--define',
                            '_topdir %s' % redefined_top_dir,
                            '-ba',
                            spec_file_abs_path)
        else:
            rpmbuild_cmd = ('/bin/rpmbuild',
                            v_opt,
                            '--define',
                            '_topdir %s' % redefined_top_dir,
                            '--noclean',
                            '-ba',
                            spec_file_abs_path)

        log.info('executing %s' % ' '.join(rpmbuild_cmd))
        ec = subprocess.call(rpmbuild_cmd)
        if ec != 0:
            raise DistutilsExecError("rpmbuild execution failed")


class sync_rpm(create_rpm):

    create_rpm.user_options.append(('remote-ip=', 'R', 'ip of remote instance to send files to'))

    def initialize_options(self):
        """
        Initialisation.

        Returns
        -------
            No return value.
        """
        create_rpm.initialize_options(self)
        self.remote_ip = None

    def finalize_options(self):
        create_rpm.finalize_options(self)
        if not self.remote_ip:
            raise Exception('missing ip option')

    def run(self):
        create_rpm.run(self, False)
        # we have one dir under BUILDROOT
        # we move under the buildroot/pkg-name dir as we do not want then to be part of remote sync
        _cwd = os.path.join(self.rpm_top_dir, 'BUILDROOT', os.listdir(os.path.join(self.rpm_top_dir, 'BUILDROOT'))[0])
        _cmd = (
            '/usr/bin/rsync', '-rltvz', '--no-times', '-e', 'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null', '--progress',
            '.', 'opc@%s:/tmp/rsynced' % str(self.remote_ip))
        ec = subprocess.call(_cmd, cwd=_cwd)
        if ec != 0:
            raise DistutilsExecError("rpmbuild execution failed")


if sys.version_info.major < 3:
    print('Only python verison 3 or above is supported')
    sys.exit(1)

setup(
    name="oci-utils",
    version="0.14.0",
    author="Laszlo Peter, Qing Lin, Guido Tijskens, Emmanuel Jannetti",
    author_email="laszlo.peter@oracle.com, qing.lin@oracle.com, guido.tijskens@oracle.com, emmanuel.jannetti@oracle.com",
    description="Oracle Cloud Infrastructure utilities",
    license="UPL",
    install_requires=install_requirements,
    keywords="Oracle Cloud Infrastructure",
    url="http://github.com/oracle/oci-utils/",
    package_dir={'': 'lib'},
    packages=find_packages('lib'),
    setup_requires=[],
    long_description=read('README.md'),
    test_suite="tests",
    data_files=[(os.path.join(sys.prefix, 'libexec'),
                 ['libexec/ocid',
                  'libexec/oci-image-cleanup',
                  'libexec/oci-utils-config-helper',
                  'libexec/oci_vcn_iface.awk',
                  'libexec/oci-kvm-upgrade',
                  'libexec/oci-growfs',
                  'libexec/oci-kvm-config.sh',
                  'libexec/oci-kvm-network-script'
                  ]),
                ("/etc/systemd/system",
                 ['data/ocid.service', 'data/oci-kvm-config.service']),
                ("/etc/oci-utils",
                 ['data/oci-image-cleanup.conf',
                  'data/oci-migrate-conf.yaml'
                  ]),
                ("/etc/oci-utils.conf.d",
                 ['data/00-oci-utils.conf',
                  'data/10-oci-kvm.conf',
                  ]),
                ('/usr/lib/systemd/system-preset',
                 ['data/91-oci-utils.preset', 'data/91-oci-kvm.preset']),
                (os.path.join(sys.prefix, "share", "man", "man1"),
                 ['man/man1/oci-public-ip.1',
                  'man/man1/oci-metadata.1',
                  'man/man1/oci-network-inspector.1',
                  'man/man1/oci-iscsi-config.1',
                  'man/man1/oci-network-config.1',
                  'man/man1/oci-kvm.1',
                  'man/man1/oci-image-migrate.1',
                  'man/man1/oci-image-migrate-import.1',
                  'man/man1/oci-image-migrate-upload.1',
                  'man/man1/oci-notify.1',
                  'man/man1/oci-instanceid.1',
                  'man/man1/oci-compartmentid.1',
                  'man/man1/oci-volume-data.1',
                  'man/man1/oci-attached-volumes.1',
                  ]),
                (os.path.join(sys.prefix, "share", "man", "man5"),
                 ['man/man5/oci-utils.conf.d.5',
                  ]),
                (os.path.join(sys.prefix, "share", "man", "man8"),
                 ['man/man8/ocid.8',
                  'man/man8/oci-growfs.8',
                  'man/man8/oci-image-cleanup.8',
                  ]),
                (os.path.join("/opt", "oci-utils", "tools"), get_content(get_reloc_path('tools'), '*.py', False)),
                (os.path.join("/opt", "oci-utils", "tools", "execution"), get_content(get_reloc_path('tools/execution'), '*', False)),
                (os.path.join("/opt", "oci-utils", "tests"), get_content(get_reloc_path('tests'), '*', False)),
                (os.path.join("/opt", "oci-utils", "tests", "data"), get_content(get_reloc_path('tests/data'), '*')),
                #(os.path.join("/opt", "oci-utils", "tests", "automation"), get_content(get_reloc_path('tests/automation'), '*')),
                ],
    scripts=['bin/oci-public-ip',
             'bin/oci-show-config',
             'bin/oci-metadata',
             'bin/oci-iscsi-config',
             'bin/oci-network-config',
             'bin/oci-network-inspector',
             'bin/oci-kvm',
             'bin/oci-image-migrate',
             'bin/oci-image-migrate-import',
             'bin/oci-image-migrate-upload',
             'bin/oci-notify',
             'bin/oci-compartmentid',
             'bin/oci-instanceid',
             'bin/oci-test-ip-auth',
             'bin/oci-volume-data',
             'bin/oci-attached-volumes',
             ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'Natural Language :: English',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3',
        'Topic :: System :: Installation/Setup',
        'Topic :: System :: Systems Administration',
        'Topic :: Utilities',
        'License :: OSI Approved :: Universal Permissive License (UPL)'],
    cmdclass={'create_rpm': create_rpm,
              'sync_rpm': sync_rpm,
              'print_rcmds': print_recorded_commands,
              'oci_tests': oci_tests,
              'oci_validation_tests': oci_validation_tests,
              'oci_migrate_tests': oci_migrate_tests,
              })
