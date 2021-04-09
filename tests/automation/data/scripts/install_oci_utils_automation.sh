#!/bin/bash
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http:/oss.oracle.com/licenses/upl.

RPM=$(which rpm)
GREP=$(which grep)
FIND=$(which find)
SED=$(which sed)
MKDIR=$(which mkdir)
DNF=dnf
SYSTEMCTL=$(which systemctl)
SUDO=$(which sudo)
if ! command -v dnf; then
installrpm=$(which yum)
else
installrpm=$(which dnf)
fi

OSVERSION=$(${SED} -rn 's/.*([0-9])\.[0-9].*/\1/p' /etc/redhat-release)
${SUDO} --login ${installrpm} config-manager --enable ol${OSVERSION}_developer

${SUDO} --login ${MKDIR} -p /root/test_data/test_rpms
${SUDO} --login ${MKDIR} -p /root/test_data/install_rpms

${SUDO} --login ${installrpm} --assumeyes erase oci-utils
${SUDO} --login ${installrpm} --assumeyes erase oci-utils-kvm
${SUDO} --login ${installrpm} --assumeyes erase oci-utils-migrate
${SUDO} --login ${installrpm} --assumeyes erase oci-utils-outest
${SUDO} --login ${installrpm} --assumeyes erase oci-utils-oumtest
${SUDO} --login ${installrpm} --assumeyes update --exclude=kernel*,oci-utils*
${SUDO} --login ${installrpm} --assumeyes install tree strace tmux

el=el$(rpm -q --queryformat '%{RELEASE}' rpm | grep -o [[:digit:]]*\$)
${SUDO} --login "${FIND}" /tmp -name "oci-utils*${el}*rpm" -exec ${installrpm} -y localinstall {} \;

${SUDO} --login  ${installrpm} clean all
${SUDO} --login  ${installrpm} repolist
${SUDO} --login  ${installrpm} repository-packages oci-utils-automation install --assumeyes --nogpgcheck


${SUDO} --login ${SYSTEMCTL} enable ocid
${SUDO} --login ${SYSTEMCTL} start ocid
