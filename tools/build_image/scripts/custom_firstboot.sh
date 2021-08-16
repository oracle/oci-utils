#!/bin/bash

# Add the libvirt group to the opc user to allow easier virsh usage
sudo usermod -aG libvirt opc
echo 'export LIBVIRT_DEFAULT_URI="qemu:///system"' >> /home/opc/.bashrc