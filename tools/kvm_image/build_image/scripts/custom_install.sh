#!/bin/bash
# Copyright (c) 2021, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

CMDPATH="command -v"
SUDO=$($CMDPATH sudo)
DNF=$($CMDPATH dnf)
YUM=$($CMDPATH yum)
#
# if dnf exists, this is OL8 or later, use dnf.
if [ ! ${DNF} ]
then
  #
  # OL7
  ${SUDO} "${YUM}" install --assumeyes python36-libvirt
  ${SUDO} "${YUM}" install --assumeyes git
else
  #
  # OL8+
  ${SUDO} "${DNF}" install --assumeyes python3-libvirt
  ${SUDO} "${DNF}" install --assumeyes git
fi