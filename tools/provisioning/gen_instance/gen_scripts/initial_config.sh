#!/bin/bash -x
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http:/oss.oracle.com/licenses/upl.

RPM=$(command -v rpm)
GREP=$(command -v grep)
FIND=$(command -v find)
SED=$(command -v sed)
MKDIR=$(command -v mkdir)
CHMOD=$(command -v chmod)
DNF=dnf
YUM=yum
SYSTEMCTL=$(command -v systemctl)
SUDO=$(command -v sudo)
INITIALLOG=/logs/initial.log
REDHATRELEASE=/etc/redhat-release
OSRELEASE=/etc/os-release
RMF="rm -rf"
HTTP_PROXY=http://www-proxy.us.oracle.com:80
HTTPS_PROXY=http://www-proxy.us.oracle.com:80
NO_PROXY=69.254.169.254,.oracle.com,osdevelopm1lhr.oraclevcn.com
SHEBANG='#!/bin/bash'
TAILOCILOG="/usr/local/sbin/tailocilog"

${SUDO} --login mkdir -p /logs
${SUDO} --login mkdir /logs
${SUDO} --login chmod 777 /logs

if [ -f "${OSRELEASE}" ]; then
  OSNAME=$(grep "^NAME=" "${OSRELEASE}"| cut -d'=' -f2 | tr -d '"')
  OSPRETTYNAME=$(grep "^PRETTY_NAME=" "${OSRELEASE}"| cut -d'=' -f2 | tr -d '"')
  OSVERSION=$(grep "^VERSION_ID=" "${OSRELEASE}"| cut -d'=' -f2 | tr -d '"')
  OSTYPE=$(grep "^ID=" "${OSRELEASE}"| cut -d'=' -f2 | tr -d '"')
else
  OSNAME=none
  OSPRETTYNAME=none
  OSVERSION=0
  OSTYPE=none
fi

${SUDO} --login echo ${OSNAME} > ${INITIALLOG} 2>&1
${SUDO} --login echo ${OSPRETTYNAME} >> ${INITIALLOG} 2>&1
${SUDO} --login echo ${OSTYPE} >> ${INITIALLOG} 2>&1
${SUDO} --login echo ${OSVERSION} >> ${INITIALLOG} 2>&1

# ${SUDO} --login echo "export no_proxy=${NO_PROXY}" >> /etc/bash.bashrc
# ${SUDO} --login echo "export http_proxy=${HTTP_PROXY}" >> /etc/bash.bashrc
# ${SUDO} --login echo "export https_proxy=${HTTPS_PROXY}" >> /etc/bash.bashrc

if [ "${OSTYPE}" = "ol" ] || [ "${OSTYPE}" = "fedora" ] || [ "${OSTYPE}" = "redhat" ]; then
  if ! command -v dnf; then
    installrpm=$(command -v yum)
    ${SUDO} --login "${installrpm}"-config-manager --enablerepo ol${OSVERSION}_developer >> ${INITIALLOG} 2>&1
  else
    installrpm=$(command -v dnf)
    ${SUDO} --login "${installrpm}" config-manager --set-enabled ol${OSVERSION}_developer >> ${INITIALLOG} 2>&1
  fi
  RET=1
  while [ ${RET} -ne 0 ]
  do
    sleep 5
    ${SUDO} --login "${installrpm}" repolist >> ${INITIALLOG} 2>&1
    RET=${?}
  done
  ${SUDO} --login "${installrpm}" --assumeyes install tree strace tmux iotop psmisc net-tools git traceroute >> ${INITIALLOG} 2>&1
  RPMLIST=("python3-pip" "python3-setuptools" "python3-wheel" "python3-netaddr" "python3-daemon" "python3-sdnotify" )
  for rpmpack in "${RPMLIST[@]}"
  do
    RET=1
    # while [ ${RET} -ne 0 ]
    # do
      sleep 5
      echo "${rpmpack}"
      ${SUDO} --login "${installrpm}" --assumeyes install "${rpmpack}" >> ${INITIALLOG} 2>&1
      RET=${?}
    # done
  done
  ${SUDO} --login "${installrpm}" --assumeyes install  git python3-pip python3-setuptools python3-wheel python3-netaddr python3-daemon python3-sdnotify traceroute >> ${INITIALLOG} 2>&1
elif [ "${OSTYPE}" = "debian" ] || [ "${OSTYPE}" = "ubuntu" ]; then
  installdeb=$(command -v apt)
  installdebprox="https_proxy=${HTTP_PROXY} http_proxy=${HTTP_PROXY} ${installdeb}"
  APTLIST=( "tree" "strace" "tmux" "iotop" "psmisc" "net-tools" "git" "python3-pip" "python3-setuptools" "python3-wheel" "python3-netaddr" "python3-daemon" "python3-sdnotify" "traceroute")
  PIPLIST=( "cryptography" "oci")
  RET=1
  while [ ${RET} -ne 0 ]
  do
    sleep 5
    ${SUDO} --login "${installdebprox}" update >> ${INITIALLOG} 2>&1
    RET=${?}
  done
  RET=1
  while [ ${RET} -ne 0 ]
  do
    sleep 5
    ${SUDO} --login "${installdebprox}" upgrade --yes >> ${INITIALLOG} 2>&1
    RET=${?}
  done
  RET=1
  while [ ${RET} -ne 0 ]
  do
    sleep 5
    ${SUDO} --login "${installdebprox}" update >> ${INITIALLOG} 2>&1
    RET=${?}
  done
  for aptpack in "${APTLIST[@]}"
  do
    RET=1
    while [ ${RET} -ne 0 ]
    do
      sleep 5
      echo "${aptpack}"
      ${SUDO} --login "${installdebprox}" install "${aptpack}" --yes >> ${INITIALLOG} 2>&1
      RET=${?}
    done
  done

  pip3=pip3
  pip3prox="https_proxy=${HTTP_PROXY} http_proxy=${HTTP_PROXY} ${pip3}"
  RET=1
  while [ ${RET} -ne 0 ]
  do
    sleep 5
    ${SUDO} --login "${pip3prox}" install --upgrade pip >> ${INITIALLOG} 2>&1
    RET=${?}
  done

  for pippack in "${PIPLIST[@]}"
  do
    RET=1
    while [ ${RET} -ne 0 ]
    do
      sleep 5
      ${SUDO} --login "${pip3prox}" install "${pippack}" >> ${INITIALLOG} 2>&1
      RET=${?}
    done
  done
else
  ${SUDO} --login echo "not a supported os" >> ${INITIALLOG} 2>&1
fi

#
# excluding the kernel can cause the install failing
# ${SUDO} --login ${installrpm} --assumeyes update --exclude=kernel*,oci-utils* >> ${INITIALLOG} 2>&1

${SUDO} -i <<EOF
${RMF} ${TAILOCILOG}
echo "${SHEBANG}" > ${TAILOCILOG}
echo "rm -f /var/tmp/oci-utils.log ; touch /var/tmp/oci-utils.log ; clear; tail -f /var/tmp/oci-utils.log" >> ${TAILOCILOG}
EOF
${CHMOD} 755 ${TAILOCILOG}
