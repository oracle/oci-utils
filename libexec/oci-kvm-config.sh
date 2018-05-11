#!/bin/bash

# /usr/libexec/oci-kvm-config.sh

# Copyright (c) 2017, 2018 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

defaultNumVFs=16
defaultMTU=9000
defaultMaxWait=240

declare -i numVFs=${NUM_VFS:-${defaultNumVFs}}
((numVFs == 0)) && numVFs=${defaultNumVFs}

declare -i vfMTU=${MTU:-${defaultMTU}}
((vfMTU < 1280)) && vfMTU=${defaultMTU}

declare -i maxWait=${MAX_WAIT:-${defaultMaxWait}}
((maxWait < 5)) && maxWait=${defaultmaxWait}

netSysPath=/sys/class/net
for nic in ${netSysPath}/*
do
  numVFDevPath=${nic}/device/sriov_numvfs
  if test -f "${numVFDevPath}"
  then
    [[ "$(head -1 "${nic}/carrier" 2>/dev/null)" == "1" ]] || continue
    echo "${numVFs}" >${numVFDevPath}
    bridge link set dev $(basename ${nic}) hwmode vepa
    vfNum=0
    while ((vfNum < numVFs))
    do
      vfNetDir="${nic}/device/virtfn${vfNum}/net/"
      while ((maxWait > 0)) && ! test -d ${vfNetDir}
      do
        sleep 0.25
        ((maxWait--))
      done
      if ! test -d ${vfNetDir}
      then
        echo "ERROR: Virtual Function ${vfNum} never appeared!" >&2
        exit 1
      fi
      vfName="$(ls -1 ${vfNetDir} | head -1)"
      [[ -n "${vfName}" ]] && ip link set dev ${vfName} mtu ${vfMTU}
      ((vfNum++))
    done
  fi
done

# Perform any necessary upgrades
python /usr/libexec/oci-kvm-upgrade
