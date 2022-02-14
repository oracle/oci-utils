#
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.
#
# makefile for oci-utils-automation
#
===================================================
oci-utils-automation - For Oracle Internal Use Only
===================================================
The oci-utils-automation rpms define the repofiles for
accessing rpms to test and creates the repository
directories if they do not exist yet.

usage:
- pull the software tree
- change directory to the software root
- run 'make publish'
- run 'make clean'
- run 'make copyrpm RPM=[path|url] DISTRO=[OL7|OL8]'
- run 'make cleanrepo'

copy rpms to the repositories:
 make copyrpm RPM=<path to rpm> DISTRO=<valid distro, OL7|OL8>
