#!/bin/bash

# Enable KVM channel
yum-config-manager --enable ol7_kvm_utils

# Install oci-utils-kvm, qemu, libvirt, and virt-install packages
sudo yum --assumeyes\
         install oci-utils-kvm\
                 qemu-kvm\
                 qemu-img\
                 libvirt\
                 libvirt-client\
                 virt-install\
                 virt-viewer

# Disable lvm devices
sudo sed -i '/# global_filter =/a\\tglobal_filter = [ "r|/dev/sd*|" ]' /etc/lvm/lvm.conf

# Preparing the KVM Server for virtualization
# Backup Grub File
sudo cp /etc/default/grub /etc/default/grub.bck

# Edit grub and include the following options
GRUB_FILE=/etc/default/grub
GRUB_STRING="intel_iommu=on amd_iommu=on"
sudo sed -i "/^GRUB_CMDLINE_LINUX=/s/\"$/ ${GRUB_STRING}\"/" ${GRUB_FILE}

# Enable nested virt (Intel only AMD is not suported yet)
echo 'options kvm-intel nested=Y'|sudo tee /etc/modprobe.d/kvm_intel.conf >/dev/null

# Enable tuned
sudo systemctl enable tuned
sudo systemctl start tuned
sudo tuned-adm profile virtual-host

# Recreate grub to validate all the changes
sudo cp /boot/efi/EFI/redhat/grub.cfg /boot/efi/EFI/redhat/grub.cfg.orig
sudo grub2-mkconfig -o /boot/efi/EFI/redhat/grub.cfg

# Allow the opc user to use virsh without the need for sudo
sudo sed -i\
         -e 's/^#unix_sock_group .*/unix_sock_group = "libvirt"/'\
         -e 's/^#unix_sock_ro_perms .*/unix_sock_ro_perms = "0770"/'\
         -e 's/^#unix_sock_rw_perms .*/unix_sock_rw_perms = "0770"/'\
         /etc/libvirt/libvirtd.conf
sudo sed -i\
         -e 's,^#uri_default \(.*\),uri_default \1,'\
         /etc/libvirt/libvirt.conf

# Enable ocid service
sudo systemctl enable ocid.service

