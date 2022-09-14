# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.
#
# makefile for creating an instance in OCI
#
#
#
# proxy
#
export no_proxy=169.254.169.254,.oraclecloud.com
#
HOSTLOCATION=host_instance
GUESTLOCATON=guest_instance

TERRAFORM4OCIPY=create_kvm_host.py
TERRAFORM4OCI=create_kvm_host
CREATEKVMHOSTUSER=create_kvmhost_user
CREATETESTVMPY=create_guest_vm.py
CREATETESTVM=create_guest_vm

BINARIES=bin/$(CREATEKVMHOSTUSER)

HOSTBINARIES=$(HOSTLOCATION)/bin/$(TERRAFORM4OCI) $(HOSTLOCATION)/bin/$(TERRAFORM4OCIPY)

CREATEGUESTVM=$(GUESTLOCATON)/bin/$(CREATETESTVM)
CREATEGUESTVMPY=$(GUESTLOCATON)/bin/$(CREATETESTVMPY)
GUESTBINARIES=$(CREATEGUESTVM) $(CREATEGUESTVMPY)

BASEDATATF=$(HOSTLOCATION)/base_instance/data.tf
BASEMAINTF=$(HOSTLOCATION)/base_instance/main.tf
BASEOUTPUTTF=$(HOSTLOCATION)/base_instance/output.tf
BASES=$(BASEDATATF) $(BASEMAINTF) $(BASEOUTPUTTF)

TFAPITF=$(HOSTLOCATION)/tf_scripts/api_key.tf
TFRSATF=$(HOSTLOCATION)/tf_scripts/rsa_key.tf
TFRSATFPUB=$(HOSTLOCATION)/tf_scripts/rsa_pub_key.tf
TFDATATF=$(HOSTLOCATION)/tf_scripts/data.tf
TFMAINTF=$(HOSTLOCATION)/tf_scripts/main.tf
TFVERSION=$(HOSTLOCATION)/tf_scripts/version.tf
TFOUTPUTTF=$(HOSTLOCATION)/tf_scripts/output.tf
TFSCRIPTS=$(TFAPITF) $(TFDATATF) $(TFMAINTF) $(TFVERSION) $(TFOUTPUTTF) $(TFRSATF) $(TFRSATFPUB)

GUESTKICKSTARTBRIDGEOL7=$(GUESTLOCATON)/templates/kickstart_bridge_template_ol7
GUESTKICKSTARTBRIDGEOL8=$(GUESTLOCATON)/templates/kickstart_bridge_template_ol8
GUESTKICKSTARTBRIDGEOL9=$(GUESTLOCATON)/templates/kickstart_bridge_template_ol9

GUESTKICKSTARTDIRECTOL7=$(GUESTLOCATON)/templates/kickstart_direct_template_ol7
GUESTKICKSTARTDIRECTOL8=$(GUESTLOCATON)/templates/kickstart_direct_template_ol8
GUESTKICKSTARTDIRECTOL9=$(GUESTLOCATON)/templates/kickstart_direct_template_ol9
GUESTTEMPLATES=$(GUESTKICKSTARTBRIDGEOL7) $(GUESTKICKSTARTBRIDGEOL8) $(GUESTKICKSTARTBRIDGEOL9) $(GUESTKICKSTARTDIRECTOL7) $(GUESTKICKSTARTDIRECTOL8) $(GUESTKICKSTARTDIRECTOL9)

INITIALSCRIPT=$(HOSTLOCATION)/sh_scripts/initial_config.sh
SHSCRIPTS=$(INITIALSCRIPT)
#
# files involved
FILELIST=Makefile README.md $(HOSTBINARIES) $(GUESTBINARIES) $(BASES) $(TFSCRIPTS) $(SHSCRIPTS) $(GUESTTEMPLATES) $(BINARIES)
#
TARGET=create_kvm_instance
VERSION=0.11_May_05_2022
WRITE=@echo
CREATETAR=tar -cjvf
EXPANDTAR=tar -xjvf
MKDIR=-mkdir -p
RMFORCE=rm -rf
DELETE=rm -f
INSTALL=install --mode=755
COPYA=cp -a
SUDO=sudo
LINK=ln -s
#
# destinations
HOMEBINS=$(HOME)/bin
HOMETEMPLATES=$(HOME)/templates
HOMEBASES=$(HOME)/$(TARGET)/base_instance
HOMETFSCRIPTS=$(HOME)/$(TARGET)/tf_scripts
HOMESHSCRIPTS=$(HOME)/$(TARGET)/sh_scripts
#
# tarball name
TARBALL=$(TARGET).$(VERSION).bz2
# help
#
.PHONY: help
help:
	$(WRITE) "help info:"
	$(WRITE) " make help"
	$(WRITE) " make show_version"
	$(WRITE) " make tarball"
	$(WRITE) " make installhost"
	$(WRITE) " make installguest"
	$(WRITE) " make uninstallguest"
	$(WRITE) " make uninstallhost"

#
# version info
.PHONY: showversion
show_version:
	$(WRITE) "version of $(TARGET) source is $(VERSION)"
#
# create tarball
tarball:
	$(CREATETAR) $(TARBALL) $(FILELIST)
#
# create directories
bindir:
	$(MKDIR) $(HOMEBINS)

basedir:
	$(MKDIR) $(HOMEBASES)

tfscriptdir:
	$(MKDIR) $(HOMETFSCRIPTS)

shscriptdir:
	$(MKDIR) $(HOMESHSCRIPTS)

templatedir:
	$(MKDIR) $(HOMETEMPLATES)
#
# lists
$(GUESTBINARIES): bindir
	$(WRITE) $(GUESTBINARIES)

$(BASES): basedir
	$(WRITE) $(BASES)

$(TFSCRIPTS): tfscriptdir
	$(WRITE) $(TFSCRIPTS)

$(SHSCRIPTS): shscriptdir
	$(WRITE) $(SHSCRIPTS)

$(GUESTTEMPLATES): templatedir
	$(WRITE) $(TEMPLATES)
#
#
# install guest
guestbin: $(GUESTBINARIES)
	$(INSTALL) $^ $(HOMEBINS)

$(HOMEBASES): $(BASES)
	$(COPYA) $^ $@

$(HOMETFSCRIPTS): $(TFSCRIPTS)
	$(COPYA) $^ $@

$(HOMESHSCRIPTS): $(SHSCRIPTS)
	$(COPYA) $^ $@

$(HOMETEMPLATES): $(GUESTTEMPLATES)
	$(COPYA) $^ $@
	
installguest: guestbin $(HOMETEMPLATES)
	$(WRITE) "Installed Create Guest VM"
#
# uninstall guest
uninstallguest:
	$(RMFORCE) $(HOME)/$(TARGET)
	$(DELETE) $(HOME)/$(GUESTBINARIES)
	$(WRITE) "Uninstalled"
#
# install host
installhost: