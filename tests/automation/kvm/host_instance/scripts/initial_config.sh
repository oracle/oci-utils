#!/bin/bash -x
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http:/oss.oracle.com/licenses/upl.

RPM=$(which rpm)
GREP=$(which grep)
FIND=$(which find)
SED=$(which sed)
MKDIR=$(which mkdir)
DNF=dnf
YUM=yum
SYSTEMCTL=$(which systemctl)
SUDO=$(which sudo)
INITIALLOG=/logs/initial.log
OSVERSION=$(${SED} -rn 's/.*([0-9])\.[0-9].*/\1/p' /etc/redhat-release)
${SUDO} --login mkdir -p /logs
${SUDO} --login mkdir /logs
${SUDO} --login chmod 777 /logs
${SUDO} --login echo ${OSVERSION} 2>&1 > ${INITIALLOG}
if ! command -v dnf; then
installrpm=$(which yum)
${SUDO} --login ${installrpm}-config-manager --enablerepo ol${OSVERSION}_developer
else
installrpm=$(which dnf)
${SUDO} --login ${installrpm} config-manager --set-enabled ol${OSVERSION}_developer
fi

#
# excluding the kernel can cause the install failing
# ${SUDO} --login ${installrpm} --assumeyes update --exclude=kernel*,oci-utils* 2>&1 >> ${INITIALLOG}
${SUDO} --login ${installrpm} --assumeyes install tree strace tmux iotop psmisc net-tools 2>&1 >> ${INITIALLOG}