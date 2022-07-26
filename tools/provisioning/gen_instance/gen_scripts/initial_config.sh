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
REDHATRELEASE=/etc/redhat-release
OSRELEASE=/etc/os-release

HTTP_PROXY=http://www-proxy.us.oracle.com:80
HTTPS_PROXY=http://www-proxy.us.oracle.com:80
NO_PROXY=69.254.169.254,.oracle.com,osdevelopm1lhr.oraclevcn.com

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

${SUDO} --login echo ${OSNAME} 2>&1 > ${INITIALLOG}
${SUDO} --login echo ${OSPRETTYNAME} 2>&1 >> ${INITIALLOG}
${SUDO} --login echo ${OSTYPE} 2>&1 >> ${INITIALLOG}
${SUDO} --login echo ${OSVERSION} 2>&1 >> ${INITIALLOG}

# ${SUDO} --login echo "export no_proxy=${NO_PROXY}" >> /etc/bash.bashrc
# ${SUDO} --login echo "export http_proxy=${HTTP_PROXY}" >> /etc/bash.bashrc
# ${SUDO} --login echo "export https_proxy=${HTTPS_PROXY}" >> /etc/bash.bashrc

if [ "${OSTYPE}" = "ol" ] || [ "${OSTYPE}" = "fedora" ] || [ "${OSTYPE}" = "redhat" ]; then
  if ! command -v dnf; then
    installrpm=$(which yum)
    ${SUDO} --login ${installrpm}-config-manager --enablerepo ol${OSVERSION}_developer 2>&1 >> ${INITIALLOG}
  else
    installrpm=$(which dnf)
    ${SUDO} --login ${installrpm} config-manager --set-enabled ol${OSVERSION}_developer 2>&1 >> ${INITIALLOG}
  fi
  RET=1
  while [ ${RET} -ne 0 ]
  do
    sleep 5
    ${SUDO} --login ${installrpm} repolist 2>&1 >> ${INITIALLOG}
    RET=${?}
  done
  ${SUDO} --login ${installrpm} --assumeyes install tree strace tmux iotop psmisc net-tools git traceroute 2>&1 >> ${INITIALLOG}
  RPMLIST=("python3-pip" "python3-setuptools" "python3-wheel" "python3-netaddr" "python3-daemon" "python3-sdnotify" )
  for rpmpack in "${RPMLIST[@]}"
  do
    RET=1
    # while [ ${RET} -ne 0 ]
    # do
      sleep 5
      echo ${rpmpack}
      ${SUDO} --login ${installrpm} --assumeyes install ${rpmpack} 2>&1 >> ${INITIALLOG}
      RET=${?}
    # done
  done
  ${SUDO} --login ${installrpm} --assumeyes install  git python3-pip python3-setuptools python3-wheel python3-netaddr python3-daemon python3-sdnotify traceroute 2>&1 >> ${INITIALLOG}
elif [ "${OSTYPE}" = "debian" ] || [ "${OSTYPE}" = "ubuntu" ]; then
  installdeb=$(which apt)
  installdebprox="https_proxy=${HTTP_PROXY} http_proxy=${HTTP_PROXY} ${installdeb}"
  APTLIST=( "tree" "strace" "tmux" "iotop" "psmisc" "net-tools" "git" "python3-pip" "python3-setuptools" "python3-wheel" "python3-netaddr" "python3-daemon" "python3-sdnotify" "traceroute")
  PIPLIST=( "cryptography" "oci")
  RET=1
  while [ ${RET} -ne 0 ]
  do
    sleep 5
    ${SUDO} --login ${installdebprox} update 2>&1 >> ${INITIALLOG}
    RET=${?}
  done
  RET=1
  while [ ${RET} -ne 0 ]
  do
    sleep 5
    ${SUDO} --login ${installdebprox} upgrade --yes 2>&1 >> ${INITIALLOG}
    RET=${?}
  done
  RET=1
  while [ ${RET} -ne 0 ]
  do
    sleep 5
    ${SUDO} --login ${installdebprox} update 2>&1 >> ${INITIALLOG}
    RET=${?}
  done
  for aptpack in "${APTLIST[@]}"
  do
    RET=1
    while [ ${RET} -ne 0 ]
    do
      sleep 5
      echo ${aptpack}
      ${SUDO} --login ${installdebprox} install ${aptpack} --yes 2>&1 >> ${INITIALLOG}
      RET=${?}
    done
  done

  pip3=pip3
  pip3prox="https_proxy=${HTTP_PROXY} http_proxy=${HTTP_PROXY} ${pip3}"
  RET=1
  while [ ${RET} -ne 0 ]
  do
    sleep 5
    ${SUDO} --login ${pip3prox} install --upgrade pip 2>&1 >> ${INITIALLOG}
    RET=${?}
  done

  for pippack in "${PIPLIST[@]}"
  do
    RET=1
    while [ ${RET} -ne 0 ]
    do
      sleep 5
      ${SUDO} --login ${pip3prox} install "${pippack}" 2>&1 >> ${INITIALLOG}
      RET=${?}
    done
  done
else
  ${SUDO} --login echo "not a supported os" 2>&1 >> ${INITIALLOG}
fi

#
# excluding the kernel can cause the install failing
# ${SUDO} --login ${installrpm} --assumeyes update --exclude=kernel*,oci-utils* 2>&1 >> ${INITIALLOG}
