#!/usr/bin/env python

# Copyright (c) 2017, 2018 Oracle and/or its affiliates. All rights reserved.

import os
import sys
from setuptools import setup

sys.path.insert(0, os.path.abspath('lib'))

try:
    from setuptools import setup, find_packages
except ImportError:
    print("oci-utils needs setuptools in order to build. Install it using"
            " your package manager (usually python-setuptools) or via pip (pip"
            " install setuptools).")
    sys.exit(1)

with open('requirements.txt') as requirements_file:
    install_requirements = requirements_file.read().splitlines()
    if not install_requirements:
        print("Unable to read requirements from the requirements.txt file"
                "That indicates this copy of the source code is incomplete.")
        sys.exit(2)

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "oci-utils",
    version = "0.6",
    author = "Laszlo Peter",
    author_email = "laszlo.peter@oracle.com",
    description = ("Oracle Cloud Infrastructure utilities"),
    license = "UPL",
    install_requires=install_requirements,
    keywords = "Oracle Cloud Infrastructure",
    url = "http://github.com/oracle/oci-utils/",
    package_dir={'': 'lib'},
    packages=find_packages('lib'),
    long_description=read('README'),
    data_files=[(os.path.join(sys.prefix, 'libexec'),
                 ['libexec/ocid',
                  'libexec/secondary_vnic_all_configure.sh',
                  'libexec/oci-image-cleanup',
                  'libexec/oci-utils-config-helper']),
                ("/etc/systemd/system", ['data/ocid.service']),
                ("/etc/oci-utils.conf.d",
                 ['data/00-oci-utils.conf',
                  'data/10-oci-kvm.conf',
                 ]),
                (os.path.join(sys.prefix, "share", "man", "man1"),
                 ['man/man1/oci-public-ip.1',
                  'man/man1/oci-metadata.1',
                  'man/man1/oci-iscsi-config.1',
                  'man/man1/oci-network-config.1',
                  'man/man1/oci-kvm.1',
                 ]),
                (os.path.join(sys.prefix, "share", "man", "man5"),
                 ['man/man5/oci-utils.conf.d.5',
                 ]),
                (os.path.join(sys.prefix, "share", "man", "man8"),
                 ['man/man8/ocid.8',
                  'man/man8/oci-image-cleanup.8',
                 ])],
    scripts=['bin/oci-public-ip',
             'bin/oci-metadata',
             'bin/oci-iscsi-config',
             'bin/oci-network-config',
             'bin/oci-kvm',
            ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'Natural Language :: English',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 2.7',
        'Topic :: System :: Installation/Setup',
        'Topic :: System :: Systems Administration',
        'Topic :: Utilities',
        'License :: OSI Approved :: Universal Permissive License (UPL)'
    ],
)
