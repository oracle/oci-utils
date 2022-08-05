#!/bin/bash
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

SUDO=$(which sudo)
#
# if dnf exists, this is OL8 or later, use dnf.
if ! command -v dnf; then
  #
  # OL7
  INSTALLRPM=$(which yum)
  ${SUDO} ${INSTALLRPM} install --assumeyes python36-libvirt
  ${SUDO} ${INSTALLRPM} install --assumeyes git
else
  #
  # OL8+
  INSTALLRPM=$(which dnf)
  ${SUDO} ${INSTALLRPM} install --assumeyes python3-libvirt
  ${SUDO} ${INSTALLRPM} install --assumeyes git
fi