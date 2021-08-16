# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.
#
# makefile for building kvm image
#
#
INSTALLPACKER=install_packer.py
CONFIGUREIMAGE=configure_image.py
BINARIES=bin/$(INSTALLPACKER) bin/$(CONFIGUREIMAGE)
TEMPLATES=templates/ol-kvm-image-template.json templates/al-kvm-image-template.json
SCRIPTS=scripts/custom_firstboot.sh scripts/custom_post_install_task.sh

#
TARGET=build-kvm-image
VERSION=0.6
OLTYPE=OL
ALTYPE=AL
VALIDTYPES=$(OLTYPE) $(ALTYPE)
WRITE=@echo
CAT=cat
MKDIR=-mkdir -p
COPYA=cp -a
INSTALL=install --mode=755
PACKER=/usr/local/bin/packer
HOMEBINS=$(HOME)/bin
HOMETEMPLATES=$(HOME)/templates
HOMESCRIPTS=$(HOME)/scripts
HOMEBIN=$(HOME)/bin
SUDO=sudo
PROFILE=DEFAULT
CONFIG=$(HOME)/.oci/config
DATADIR=$(HOME)/data
VARFILENAME=image_vars
#
# proxy
#
export no_proxy=169.254.169.254,.oraclecloud.com
#
# help
#
.PHONY: help
help:
	$(WRITE) "help info:"
	$(WRITE) " make help"
	$(WRITE) " make show_version"
	$(WRITE) " make install"
	$(WRITE) " make install_packer"
	$(WRITE) " make configure PROFILE=<profile> CONFIG=<config> DATADIR=<data directory> VARFILENAME=<packer variable file name> TYPE=[$(OLTYPE)|$(ALTYPE)]"
	$(WRITE) "          only TYPE=[$(OLTYPE)|$(ALTYPE)] is mandatory"
	$(WRITE) " make configure TYPE=[$(OLTYPE)|$(ALTYPE)]"
	$(WRITE) " make show_vars"
	$(WRITE) " make build_image VARFILENAME=<packer variable file name> TYPE=[$(OLTYPE)|$(ALTYPE)] "
	$(WRITE) " make all TYPE=[$(OLTYPE)|$(ALTYPE)] "

#
# version info
.PHONY: showversion ${SOURCEFILES}
show_version:
	$(WRITE) "version of $(TARGET) source is $(VERSION)"
#
# directories
bindir:
	$(MKDIR) $(HOME)/bin

templatedir:
	$(MKDIR) $(HOME)/templates

scriptdir:
	$(MKDIR) $(HOME)/scripts
#
# lists
$(SCRIPTS): scriptdir
	$(WRITE) $(SCRIPTS)

$(TEMPLATES): templatedir
	$(WRITE) $(TEMPLATES)

$(BINARIES): bindir
	$(WRITE) $(BINARIES)
#
# install
$(HOMESCRIPTS): $(SCRIPTS)
	$(COPYA) $^ $@

$(HOMETEMPLATES): $(TEMPLATES)
	$(COPYA) $^ $@

$(HOMEBINS): $(BINARIES)
	$(INSTALL) $^ $@

install: $(HOMESCRIPTS) $(HOMETEMPLATES) $(HOMEBINS)
	$(WRITE) "Installed"
#
# install packer
install_packer: install
	sudo $(HOMEBIN)/$(INSTALLPACKER)
#
# configure build
profile:
	PROFILE=?"DEFAULT"
	$(WRITE) "profile: $(PROFILE)"

config:
	CONFIG=?"~/.oci/config"
	$(WRITE) "config: $(CONFIG)"

datadir:
	DATADIR=?"~/data"
	$(WRITE) "datadir: $(DATADIR)"

varfile:
	VARFILE=?"image_vars"

type:
	@[ "${TYPE}" ] || ( echo "TYPE [$(OLTYPE)|$(ALTYPE)] is not set"; exit 1 )

configure: install_packer profile config datadir varfile type
	$(WRITE) "$(HOMEBIN)/$(CONFIGUREIMAGE) --profile $(PROFILE) --config $(CONFIG) --data-directory $(DATADIR) --var-file $(VARFILENAME) --type $(TYPE)"
	$(HOMEBIN)/$(CONFIGUREIMAGE) --profile $(PROFILE) --config $(CONFIG) --data-directory $(DATADIR) --var-file $(VARFILENAME) --type $(TYPE)
#
# show variables file
show_vars:
	$(CAT) $(DATADIR)/$(VARFILENAME).tfvars.json
#
# build image
build_image: VARFILEPATH=$(DATADIR)/$(VARFILENAME).tfvars.json
varfilepath: datadir varfile
	$(WRITE) "variable file path: $(VARFILEPATH)"

type_validation: type
	VALIDTYPE=$(or $(filter ${TYPE},${VALIDTYPES}),$(error $$TYPE [${TYPE}] must be one of ${VALIDTYPES}))

ifeq ($(TYPE),$(OLTYPE))
TEMPLATEPATH=$(HOMETEMPLATES)/ol-kvm-image-template.json
else ifeq ($(TYPE),$(ALTYPE))
TEMPLATEPATH=$(HOMETEMPLATES)/al-kvm-image-template.json
endif

template:
	$(WRITE) $(TEMPLATEPATH)

build_image: type_validation varfilepath template
	$(WRITE) "no proxy: $${no_proxy}"
	$(WRITE) "$(PACKER) build --on-error=ask -var-file=$(VARFILEPATH) $(TEMPLATEPATH)"
	$(PACKER) build --on-error=ask -var-file=$(VARFILEPATH) $(TEMPLATEPATH)

all: configure build_image
	$(WRITE) "build $(TYPE) kvm image.}"