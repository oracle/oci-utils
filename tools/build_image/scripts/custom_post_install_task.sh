#!/bin/bash
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

SUDO=$(which sudo)
SED=$(which sed)
COPY=cp
WRITE=echo
NOW=$(date +"%Y%m%d_%H%M")
#
# if dnf exists, this is OL8 or later, use dnf.
if ! command -v dnf; then
  #
  # OL7
  INSTALLRPM=$(which yum)
  #
  # Enable KVM channel
  yum-config-manager --enable ol7_kvm_utils
  #
  # Install oci-utils-kvm, qemu, libvirt, and virt-install packages
  ${SUDO} ${INSTALLRPM} --assumeyes install oci-utils-kvm \
                                            qemu-kvm \
                                            qemu-img \
                                            libvirt \
                                            libvirt-python \
                                            libvirt-client \
                                            virt-install \
                                            virt-viewer
else
  #
  # OL8+
  INSTALLRPM=$(which dnf)
  # Install oci-utils-kvm, qemu, libvirt, and virt-install packages
  ${SUDO} ${INSTALLRPM} --assumeyes install oci-utils-kvm \
                                            qemu-kvm \
                                            qemu-img \
                                            libvirt \
                                            python3-libvirt \
                                            libvirt-client \
                                            virt-install \
                                            virt-viewer \
                                            @virt
fi
#
# Disable lvm devices
${SUDO} ${COPY} /etc/lvm/lvm.conf /etc/lvm/lvm.conf.${NOW}
${SUDO} ${SED} -i '/# global_filter =/a\\tglobal_filter = [ "r|/dev/sd*|" ]' /etc/lvm/lvm.conf
#
# Preparing the KVM Server for virtualization
# Backup Grub File
${SUDO} ${COPY} /etc/default/grub /etc/default/grub.${NOW}
#
# Edit grub and include the following options
GRUB_FILE=/etc/default/grub
GRUB_STRING="intel_iommu=on amd_iommu=on"
${SUDO} ${SED} -i "/^GRUB_CMDLINE_LINUX=/s/\"$/ ${GRUB_STRING}\"/" ${GRUB_FILE}
#
# Enable nested virt (Intel only AMD is not suported yet)
${WRITE} 'options kvm-intel nested=Y'|${SUDO} tee /etc/modprobe.d/kvm_intel.conf >/dev/null
#
# Enable tuned
${SUDO} systemctl enable tuned
${SUDO} systemctl start tuned
${SUDO} tuned-adm profile virtual-host
#
# Recreate grub to validate all the changes
${SUDO} ${COPY} /boot/efi/EFI/redhat/grub.cfg /boot/efi/EFI/redhat/grub.cfg.${NOW}
${SUDO} grub2-mkconfig -o /boot/efi/EFI/redhat/grub.cfg
#
# Allow the opc user to use virsh without the need for sudo
${SUDO} ${COPY} /etc/libvirt/libvirtd.conf /etc/libvirt/libvirtd.conf.${NOW}
${SUDO} ${SED} -i\
         -e 's/^#unix_sock_group .*/unix_sock_group = "libvirt"/'\
         -e 's/^#unix_sock_ro_perms .*/unix_sock_ro_perms = "0770"/'\
         -e 's/^#unix_sock_rw_perms .*/unix_sock_rw_perms = "0770"/'\
         /etc/libvirt/libvirtd.conf
${SUDO} ${SED} -i\
         -e 's,^#uri_default \(.*\),uri_default \1,'\
         /etc/libvirt/libvirt.conf
#
# Enable ocid service
${SUDO} systemctl enable ocid.service

