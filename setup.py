# Copyright (c) 2017, 2020 Oracle and/or its affiliates. All rights reserved.

""" Build an rpm from oci-utils.
"""
import os
import subprocess
import sys
from distutils.core import Command
from distutils.errors import DistutilsExecError

from distutils import log

sys.path.insert(0, os.path.abspath('lib'))

try:
    from setuptools import setup, find_packages
except ImportError:
    print("oci-utils needs setuptools in order to build. Install it using "
          "your package manager (usually python-setuptools) or via pip (pip "
          "install setuptools).")
    sys.exit(1)

with open('requirements.txt') as requirements_file:
    install_requirements = requirements_file.read().splitlines()
    if not install_requirements:
        print("Unable to read requirements from the requirements.txt file "
              "That indicates this copy of the source code is incomplete.")
        sys.exit(2)


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
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


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
        log.info("runnig sdist command now...")
        self.run_command('sdist')
        log.info("tarball created, building the RPM now...")
        _cwd = os.path.dirname(os.path.abspath(__file__))
        log.info('current wd [%s]' % _cwd)
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


setup(
    name="oci-utils",
    version="0.11.0",
    author="Laszlo Peter, Qing Lin, Guido Tijskens, Emmanuel Jannetti",
    author_email="laszlo.peter@oracle.com, qing.lin@oracle.com, guido.tijskens@oracle.com, emmanuel.jannetti@oracle.com",
    description="Oracle Cloud Infrastructure utilities",
    license="UPL",
    install_requires=install_requirements,
    keywords="Oracle Cloud Infrastructure",
    url="http://github.com/oracle/oci-utils/",
    package_dir={'': 'lib'},
    packages=find_packages('lib'),
    setup_requires=["flake8"],
    long_description=read('README'),
    data_files=[("/etc/oci-utils",
                 ['data/oci-migrate-conf.yaml',
                  ]),
                (os.path.join(sys.prefix, "share", "man", "man1"),
                 ['man/man1/oci-image-migrate.1',
                  'man/man1/oci-image-migrate-import.1'
                  ]),
                  ],
    scripts=['bin/oci-image-migrate',
             'bin/oci-image-migrate-import'
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
    cmdclass={'create_rpm': create_rpm, 'sync_rpm': sync_rpm})
