#!/bin/bash

# /usr/libexec/oci-kvm-config.sh

# Copyright (c) 2017, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at http://oss.oracle.com/licenses/upl.

defaultMTU=9000
defaultMaxWait=240

# To get the default number of VFs we use the number of CPU siblings which
# corresponds to the BM model
#   BM.Standard1.36 have 36 siblings: 1 + 35 = 36 total allowable vNics
#   BM.Standard1.52 have 52 siblings: 2 + 25 = 52 total allowable vNics
#   (NOTE: Above is PhysicalNics + vNics)
# Since we do not support assigning the vNic on the physical Nic to guests
# the number of VFs end up being 35 on 1.36 and 50 on 2.52
declare -i siblings=$(head -11 /proc/cpuinfo \
                      | grep 'siblings' \
                      | awk -F: '{print $2}' \
                      | sed 's/ //g')
defaultNumVFs=$((siblings - 1))
((siblings > 36)) && defaultNumVFs=$((siblings / 2 - 1))
[[ -z "${defaultNumVFs}" ]] && defaultNumVFs=16

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

. /etc/os-release
major=`echo $VERSION_ID | ${_CUT} -d. -f1`
if [ ${major} -ge 8 ]
then
   #priority given to python3
   /usr/bin/python3  /usr/libexec/oci-kvm-upgrade
else
   /usr/bin/python2  /usr/libexec/oci-kvm-upgrade
fi

