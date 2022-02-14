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
CREATEKVMINSTANCEPY=bin/create_kvm_instance.py
CREATEKVMINSTANCESH=bin/create_kvm_instance
BINARIES=$(CREATEKVMINSTANCESH) $(CREATEKVMINSTANCEPY)

BASEDATATF=base_instance/data.tf
BASEMAINTF=base_instance/main.tf
BASEOUTPUTTF=base_instance/output.tf
BASES=$(BASEDATATF) $(BASEMAINTF) $(BASEOUTPUTTF)

TFAPITF=tf_scripts/api_key.tf
TFDATATF=tf_scripts/data.tf
TFMAINTF=tf_scripts/main.tf
TFVERSION=tf_scripts/version.tf
TFOUTPUTTF=tf_scripts/output.tf
TFSCRIPTS=$(TFAPITF) $(TFDATATF) $(TFMAINTF) $(TFVERSION) $(TFOUTPUTTF)

INITIALSCRIPT=gen_scripts/initial_config.sh
SHSCRIPTS=$(INITIALSCRIPT)
#
# files involved
FILELIST=Makefile README.md $(BINARIES) $(BASES) $(TFSCRIPTS) $(SHSCRIPTS)
#
TARGET=create_kvm_instance
VERSION=0.1_Dec_09_2021
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
uninstallbins: $(BINARIES)
	$(foreach var,$(BINARIES),$(DELETE) $(HOME)/$(var);)

uninstalldata:
	$(RMFORCE) $(HOME)/$(TARGET)

uninstall: uninstallbins uninstalldata
	$(WRITE) "Uninstalled"