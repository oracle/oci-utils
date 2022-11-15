#!/bin/bash
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http:/oss.oracle.com/licenses/upl.

RPM=$(command -v rpm)
GREP=$(command -v grep)
FIND=$(command -v find)
SED=$(command -v sed)
MKDIR=$(command -v mkdir)
DNF=dnf
SYSTEMCTL=$(command -v systemctl)
SUDO=$(command -v sudo)
OSVERSION=$(${SED} -rn 's/.*([0-9])\.[0-9].*/\1/p' /etc/redhat-release)
if ! command -v dnf; then
installrpm=$(command -v yum)
${SUDO} --login ${installrpm}-config-manager --enablerepo ol${OSVERSION}_developer
else
installrpm=$(command -v dnf)
${SUDO} --login ${installrpm} config-manager --set-enabled ol${OSVERSION}_developer
fi

${SUDO} --login ${MKDIR} -p /root/test_data/test_rpms
${SUDO} --login ${MKDIR} -p /root/test_data/install_rpms

${SUDO} --login ${installrpm} --assumeyes erase oci-utils
${SUDO} --login ${installrpm} --assumeyes erase oci-utils-kvm
${SUDO} --login ${installrpm} --assumeyes erase oci-utils-migrate
${SUDO} --login ${installrpm} --assumeyes erase oci-utils-outest
${SUDO} --login ${installrpm} --assumeyes erase oci-utils-oumtest
#
# excluding the kernel can cause the update failing
# ${SUDO} --login ${installrpm} --assumeyes update --exclude=kernel*,oci-utils*
${SUDO} --login ${installrpm} --assumeyes install tree strace tmux

el=el$(rpm -q --queryformat '%{RELEASE}' rpm | grep -o [[:digit:]]*\$)
${SUDO} --login "${FIND}" /tmp -name "oci-utils*el${OSVERSION}*rpm" -exec ${installrpm} -y localinstall {} \;

${SUDO} --login  ${installrpm} clean all
${SUDO} --login  ${installrpm} repolist
${SUDO} --login  ${installrpm} repository-packages oci-utils-automation install --assumeyes --nogpgcheck

${SUDO} --login ${SYSTEMCTL} enable ocid
${SUDO} --login ${SYSTEMCTL} start ocid

#
# kvm specific
${SUDO} --login ${MKDIR} -p /isos
