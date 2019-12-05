# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

__all__ = ['_kvm_network_script_tmpl']


_kvm_network_script_tmpl = """
KVM_NETWORK_NAME=${__KVM_NETWORK_NAME__}
KVM_NET_ADDRESS_SPACE=${__KVM_NET_ADDRESS_SPACE__}
KVM_NET_BRIDGE_NAME=${__KVM_NET_BRIDGE_NAME__}
VNIC_DEFAULT_GW=${__VNIC_DEFAULT_GW__}
NET_DEV=${__NET_DEV__}
RT_TABLE_NAME=${__RT_TABLE_NAME__}
VNIC_PRIVATE_IP=${__VNIC_PRIVATE_IP__}

start() {
    echo "Adding default route to ${VNIC_DEFAULT_GW}"
    /usr/sbin/ip route add default via ${VNIC_DEFAULT_GW} dev ${NET_DEV} table ${RT_TABLE_NAME}
    if [ $? -ne 0 ]
    then
        echo "Cannot add route : default ${VNIC_DEFAULT_GW} via dev ${NET_DEV} table ${RT_TABLE_NAME}"
        return 1
    fi
    echo "Adding rule for ${VNIC_PRIVATE_IP}"
    /usr/sbin/ip rule add from ${VNIC_PRIVATE_IP} lookup ${RT_TABLE_NAME}
    if [ $? -ne 0 ]
    then
        echo "Cannot add rule : from ${VNIC_PRIVATE_IP} lookup ${RT_TABLE_NAME}"
        return 1
    fi
    # Start the KVM network
    echo "Starting the network"
    /bin/virsh net-start --network ${KVM_NETWORK_NAME}
    if [ $? -ne 0 ]
    then
        echo "Cannot start kvm network"
        return 1
    fi
    echo "network started"

    # Add routes for KVM
    echo "Adding routes for KVM network"
    /usr/sbin/ip route add ${KVM_NET_ADDRESS_SPACE} dev ${KVM_NET_BRIDGE_NAME} scope link proto kernel table ${RT_TABLE_NAME}
    if [ $? -ne 0 ]
    then
        echo "Cannot add route : ${KVM_NET_ADDRESS_SPACE} dev ${KVM_NET_BRIDGE_NAME} scope link proto kernel table ${RT_TABLE_NAME}"
        return 1
    fi
    /usr/sbin/ip rule add from ${KVM_NET_ADDRESS_SPACE} lookup ${RT_TABLE_NAME}
    # Add firewall rules
    echo "Adding iptables rules routes for KVM network"
    /usr/sbin/iptables -t nat -A POSTROUTING -s ${KVM_NET_ADDRESS_SPACE} -d 224.0.0.0/24 -j ACCEPT
    /usr/sbin/iptables -t nat -A POSTROUTING -s ${KVM_NET_ADDRESS_SPACE} -d 255.255.255.255/32 -j ACCEPT
    /usr/sbin/iptables -t nat -A POSTROUTING -s ${KVM_NET_ADDRESS_SPACE} ! -d ${KVM_NET_ADDRESS_SPACE}  -j MASQUERADE
    return 0
}

stop() {
   /usr/bin/virsh net-destroy --network ${KVM_NETWORK_NAME}
   return $?
}

status() {
    /usr/bin/virsh net-info --network ${KVM_NETWORK_NAME}
    /usr/bin/virsh net-dhcp-leases --network ${KVM_NETWORK_NAME}
}


"""
