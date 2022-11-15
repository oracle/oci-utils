#!/bin/bash
# Copyright (c) 2021, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

CMDPATH="command -v"
SUDO=$($CMDPATH sudo)
AWK=$($CMDPATH awk)
SED=$($CMDPATH sed)
DNF=$($CMDPATH dnf)
YUM=$($CMDPATH yum)
YUMCONFIGMANAGER=$($CMDPATH yum-config-manager)
COPY="cp"
WRITE="echo"
NOW=$(date +"%Y%m%d_%H%M")
#
# if dnf exists, this is OL8 or later, use dnf.
if [ ! "${DNF}" ]
then
  #
  # OL7
  # Enable KVM channel
  ${YUMCONFIGMANAGER} --enable ol7_kvm_utils
  #
  # Install oci-utils-kvm, qemu, libvirt, and virt-install packages
  ${YUM} --assumeyes install oci-utils-kvm \
                             qemu-kvm \
                             qemu-img \
                             libvirt \
                             libvirt-python \
                             libvirt-client \
                             virt-install \
                             virt-viewer
  ${YUM} --assumeyes install redhat-lsb-core

else
  #
  # OL8+
  # Install oci-utils-kvm, qemu, libvirt, and virt-install packages
  ${DNF} --assumeyes install oci-utils-kvm \
                             qemu-kvm \
                             qemu-img \
                             libvirt \
                             python3-libvirt \
                             libvirt-client \
                             virt-install \
                             virt-viewer \
                             @virt
  ${DNF} --assumeyes install redhat-lsb-core
  #
  # Install UEKR7 kernel on OL8
  LSBRELEASE=$($CMDPATH lsb_release)
  OSREL=$(${LSBRELEASE} -rs | ${AWK} -F'.' '{print $1}')
#
# To force UEK7 kernel installed.
#  if [ "${OSREL}" == '8' ]
#  then
#    ${DNF} --enablerepo=ol8_UEKR7 --assumeyes update kernel-uek kernel-uek-devel
#  fi
  # UEKR7 is default on OL9, which is not yet supported.
fi
#
# Disable lvm devices
${SUDO} ${COPY} /etc/lvm/lvm.conf /etc/lvm/lvm.conf."${NOW}"
${SUDO} "${SED}" -i '/# global_filter =/a\\tglobal_filter = [ "a|^/dev/sda.*$|", "r|/dev/sd*|" ]' /etc/lvm/lvm.conf
#
# Preparing the KVM Server for virtualization
# Backup Grub File
${SUDO} ${COPY} /etc/default/grub /etc/default/grub."${NOW}"
#
# Edit grub and include the following options
GRUB_FILE=/etc/default/grub
GRUB_STRING="intel_iommu=on amd_iommu=on"
${SUDO} "${SED}" -i "/^GRUB_CMDLINE_LINUX=/s/\"$/ ${GRUB_STRING}\"/" ${GRUB_FILE}
#
# Enable nested virt
# Intel
${WRITE} 'options kvm-intel nested=Y'|${SUDO} tee /etc/modprobe.d/kvm_intel.conf >/dev/null
# AMD
${WRITE} 'options kvm-amd nested=1'|${SUDO} tee /etc/modprobe.d/kvm_amd.conf >/dev/null
#
# Enable tuned
${SUDO} systemctl enable tuned
${SUDO} systemctl start tuned
${SUDO} tuned-adm profile virtual-host
#
# Recreate grub to validate all the changes
${SUDO} ${COPY} /boot/efi/EFI/redhat/grub.cfg /boot/efi/EFI/redhat/grub.cfg."${NOW}"
${SUDO} grub2-mkconfig -o /boot/efi/EFI/redhat/grub.cfg
#
# Allow the opc user to use virsh without the need for sudo
${SUDO} ${COPY} /etc/libvirt/libvirtd.conf /etc/libvirt/libvirtd.conf."${NOW}"
${SUDO} "${SED}" -i\
         -e 's/^#unix_sock_group .*/unix_sock_group = "libvirt"/'\
         -e 's/^#unix_sock_ro_perms .*/unix_sock_ro_perms = "0770"/'\
         -e 's/^#unix_sock_rw_perms .*/unix_sock_rw_perms = "0770"/'\
         /etc/libvirt/libvirtd.conf
${SUDO} "${SED}" -i\
         -e 's,^#uri_default \(.*\),uri_default \1,'\
         /etc/libvirt/libvirt.conf
#
# Enable ocid service
${SUDO} systemctl enable ocid.service
