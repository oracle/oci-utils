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

echo "Default MTU for interfaces:  ${vfMTU}"
echo "Default max virtual function count for interfaces:  ${numVFs}"

netSysPath=/sys/class/net
for nic in ${netSysPath}/*
do
  numVFDevPath=${nic}/device/sriov_numvfs
  if test -f "${numVFDevPath}"
  then
    nic_name=$(basename ${nic})
    is_up=`/bin/cat ${nic}/carrier 2>/dev/null`
    if [ $? -ne 0 ] || [ "is_up" == 0 ]
    then
      # we have failed to open or content is '0', this means down
      echo "Bringing ${nic_name} link up"
      /sbin/ip link set ${nic_name} up
      if [ $? -ne 0 ]
      then
        echo "ERROR: Failed to bring up ${nic_name}" >&2
        exit 1
      fi
    fi
    echo "setting ${numVFs} as number of VFs for ${nic}"
    echo "${numVFs}" >${numVFDevPath}
    echo "setting hwmode node to vepa for ${nic}"
    /sbin/bridge link set dev ${nic_name} hwmode vepa
    vfNum=0
    echo "Waiting for VFs to appear"
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
      echo "Setting default MTU on VF ${vfName}"
      [[ -n "${vfName}" ]] && /sbin/ip link set dev ${vfName} mtu ${vfMTU}
      ((vfNum++))
    done
  fi
done

echo "Calling /usr/libexec/oci-kvm-upgrade"
/usr/bin/python3 /usr/libexec/oci-kvm-upgrade

