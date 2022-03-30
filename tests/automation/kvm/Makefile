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

TERRAFORM4OCI=create_instance.py
CREATETESTVM=create_test_vm.py

HOSTBINARIES=$(HOSTLOCATION)/bin/$(TERRAFORM4OCI)
GUESTBINARIES=$(GUESTLOCATON)/bin/$(CREATETESTVM)

BASEDATATF=$(HOSTLOCATION)/base_instance/data.tf
BASEMAINTF=$(HOSTLOCATION)/base_instance/main.tf
BASEOUTPUTTF=$(HOSTLOCATION)/base_instance/output.tf
BASES=$(BASEDATATF) $(BASEMAINTF) $(BASEOUTPUTTF)

TFAPITF=$(HOSTLOCATION)/tf_scripts/api_key.tf
TFDATATF=$(HOSTLOCATION)/tf_scripts/data.tf
TFMAINTF=$(HOSTLOCATION)/tf_scripts/main.tf
TFVERSION=$(HOSTLOCATION)/tf_scripts/version.tf
TFOUTPUTTF=$(HOSTLOCATION)/tf_scripts/output.tf
TFSCRIPTS=$(TFAPITF) $(TFDATATF) $(TFMAINTF) $(TFVERSION) $(TFOUTPUTTF)

GUESTKICKSTARTBRIDGEOL7=$(GUESTLOCATON)/templates/kickstart_bridge_template_ol7
GUESTKICKSTARTBRIDGEOL8=$(GUESTLOCATON)/templates/kickstart_bridge_template_ol8
GUESTKICKSTARTDIRECTOL7=$(GUESTLOCATON)/templates/kickstart_direct_template_ol7
GUESTKICKSTARTDIRECTOL8=$(GUESTLOCATON)/templates/kickstart_direct_template_ol8
GUESTTEMPLATES=$(GUESTKICKSTARTBRIDGEOL7) $(GUESTKICKSTARTBRIDGEOL8) $(GUESTKICKSTARTDIRECTOL7) $(GUESTKICKSTARTDIRECTOL8)

INITIALSCRIPT=$(HOSTLOCATION)/scripts/initial_config.sh
SHSCRIPTS=$(INITIALSCRIPT)
#
# files involved
FILELIST=Makefile README.md $(HOSTBINARIES) $(GUESTBINARIES) $(BASES) $(TFSCRIPTS) $(SHSCRIPTS) $(GUESTTEMPLATES)
#
TARGET=create_instance
VERSION=0.10_Feb_23_2022
WRITE=@echo
CREATETAR=tar -cjvf
EXPANDTAR=tar -xjvf
MKDIR=-mkdir -p
RMFORCE=rm -rf
DELETE=rm -f
INSTALL=install --mode=755
COPYA=cp -a
SUDO=sudo
#
# destinations
HOMEBINS=$(HOME)/bin
HOMEBASES=$(HOME)/$(TARGET)/base_instance
HOMETFSCRIPTS=$(HOME)/$(TARGET)/tf_scripts
HOMESHSCRIPTS=$(HOME)/$(TARGET)/sh_scripts
#
# tarball name
TARBALL=$(TARGET).$(VERSION).bz
# help
#
.PHONY: help
help:
	$(WRITE) "help info:"
	$(WRITE) " make help"
	$(WRITE) " make show_version"
	$(WRITE) " make tarball"
	$(WRITE) " make install"
	$(WRITE) " make uninstall"

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
#
# lists
$(BINARIES): bindir
	$(WRITE) $(BINARIES)

$(BASES): basedir
	$(WRITE) $(BASES)

$(TFSCRIPTS): tfscriptdir
	$(WRITE) $(TFSCRIPTS)

$(SHSCRIPTS): shscriptdir
	$(WRITE) $(SHSCRIPTS)
#
# install
BIN: $(BINARIES)
	$(INSTALL) $^ $(HOMEBINS)

$(HOMEBASES): $(BASES)
	$(COPYA) $^ $@

$(HOMETFSCRIPTS): $(TFSCRIPTS)
	$(COPYA) $^ $@

$(HOMESHSCRIPTS): $(SHSCRIPTS)
	$(COPYA) $^ $@

install: BIN $(HOMETFSCRIPTS) $(HOMEBASES) $(HOMESHSCRIPTS)
	$(WRITE) "Installed"
#
# uninstall
uninstall:
	$(RMFORCE) $(HOME)/$(TARGET)
	$(DELETE) $(HOME)/$(BINARIES)
	$(WRITE) "Uninstalled"