#!/bin/bash

# /usr/libexec/oci-kvm-config.sh

# Copyright (c) 2017, 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

defaultNumVFs=16

declare -i numVFs=${NUM_VFS:-${defaultNumVFs}}
((numVFs == 0)) && numVFs=${defaultNumVFs}

netSysPath=/sys/class/net
for nic in ${netSysPath}/*
do
  numVFDevPath=${nic}/device/sriov_numvfs
  if test -f "${numVFDevPath}"
  then
    [[ "$(head -1 "${nic}/carrier" 2>/dev/null)" == "1" ]] \
      && echo "${numVFs}" >${numVFDevPath} \
      && bridge link set dev $(basename ${nic}) hwmode vepa
  fi
done

# Perform any necessary upgrades
python /usr/libexec/oci-kvm-upgrade
