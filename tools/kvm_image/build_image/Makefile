# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.
#
# makefile for building kvm image
#
#
INSTALLPACKER=install_packer.py
CONFIGUREIMAGE=configure_image.py
UPLOADIMAGE=upload_image.py
BINARIES=bin/$(INSTALLPACKER) bin/$(CONFIGUREIMAGE) bin/$(UPLOADIMAGE)
TEMPLATES=templates/ol-kvm-image-template.json templates/al-kvm-image-template.json
SCRIPTS=scripts/custom_firstboot.sh scripts/custom_post_install_task.sh scripts/custom_install.sh
MAKEFILE=Makefile
MAKE=$(MAKEFILE)
README=README.md
DOCS=$(README)

#
TARGET=build-kvm-image
VERSION=0.10_September_13_2022
OLTYPE=OL
ALTYPE=AL
VALIDTYPES=$(OLTYPE) $(ALTYPE)
REL7=7
REL8=8
VALIDRELEASES=$(REL7) $(REL8)
WRITE=@echo
CAT=cat
MKDIR=-mkdir --parents
COPYA=cp --archive
PACKER=/usr/local/bin/packer
#HOMEROOT=$(HOME)/imagebuild
HOMEROOT=$(HOME)
HOMEBINS=$(HOME)/bin
HOMETEMPLATES=$(HOMEROOT)/templates
HOMESCRIPTS=$(HOMEROOT)/scripts
HOMEDOC=$(HOMEROOT)/doc
HOMEMAKE=$(HOMEROOT)
HOMEBIN=$(HOME)/bin
SUDO=sudo
PROFILE=DEFAULT
CREATETAR=tar -cjvf
INSTALL=install --verbose --mode=755 --target=${HOMEBINS}
CONFIG=$(HOME)/.oci/config
DATADIR=$(HOMEROOT)/data
VARFILENAME=image_vars
#
TARBALL=$(TARGET).$(VERSION).bz2
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
	$(WRITE) " make configure PROFILE=<profile> CONFIG=<config> DATADIR=<data directory> VARFILENAME=<packer variable file name> TYPE=[$(OLTYPE)|$(ALTYPE)] RELEASE=[7|8]"
	$(WRITE) "          TYPE=[$(OLTYPE)|$(ALTYPE)] and RELEASE=[7|8] are mandatory"
	$(WRITE) " make configure TYPE=[$(OLTYPE)|$(ALTYPE)] RELEASE=[7|8]"
	$(WRITE) " make show_vars"
	$(WRITE) " make build_image VARFILENAME=<packer variable file name> TYPE=[$(OLTYPE)|$(ALTYPE)] RELEASE=[7|8]"
	$(WRITE) " make all TYPE=[$(OLTYPE)|$(ALTYPE)] RELEASE=[7|8]"
	$(WRITE) " make tarball"

#
# version info
.PHONY: show_version
show_version:
	$(WRITE) "Version of $(TARGET) source is $(VERSION)"
#
# tarball
tarball:
	$(CREATETAR) $(TARBALL) ./*
#
# directories
bindir:
	$(MKDIR) $(HOME)/bin

templatedir:
	$(MKDIR) $(HOMEROOT)/templates

scriptdir:
	$(MKDIR) $(HOMEROOT)/scripts

docdir:
	$(MKDIR) $(HOMEROOT)/doc

makedir:
	$(MKDIR) $(HOMEROOT)
#
# lists
$(SCRIPTS): scriptdir
	$(WRITE) $(SCRIPTS)

$(TEMPLATES): templatedir
	$(WRITE) $(TEMPLATES)

$(BINARIES): bindir
	$(WRITE) $(BINARIES)

$(DOCS): docdir
	$(WRITE) $(DOCS)

#$(MAKE): makedir
#	$(WRITE) $(MAKE)
#
# install
$(HOMESCRIPTS): $(SCRIPTS)
	$(COPYA) $^ $@

$(HOMETEMPLATES): $(TEMPLATES)
	$(COPYA) $^ $@

$(HOMEBINS): $(BINARIES)
	$(INSTALL) $^

$(HOMEDOC): $(DOCS)
	$(COPYA) $^ $@

$(HOMEMAKE): $(MAKE)
	$(COPYA) $^ $@

copymakefile:
	$(COPYA) $(MAKE) $(HOME)

install: $(HOMESCRIPTS) $(HOMETEMPLATES) $(HOMEBINS) $(HOMEDOC) copymakefile
	$(WRITE) "Installed"
#
# install packer
install_packer:
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
	DATADIR=?"~/imagebuild/data"
	$(WRITE) "datadir: $(DATADIR)"

varfile:
	VARFILE=?"image_vars"

type:
	@[ "$(TYPE)" ] || ( echo "TYPE [$(OLTYPE)|$(ALTYPE)] is not set"; exit 1 )

release:
	@[ "$(RELEASE)" ] || ( echo "RELEASE [7|8] is not set"; exit 1 )

# configure: install_packer profile config datadir varfile type release
configure: profile config datadir varfile type release
	$(WRITE) "$(HOMEBIN)/$(CONFIGUREIMAGE) --profile $(PROFILE) --config $(CONFIG) --data-directory $(DATADIR) --var-file $(VARFILENAME) --type $(TYPE) --release $(RELEASE)"
	$(HOMEBIN)/$(CONFIGUREIMAGE) --profile $(PROFILE) --config $(CONFIG) --data-directory $(DATADIR) --var-file $(VARFILENAME) --type $(TYPE) --release $(RELEASE)
#
# show variables file
show_vars:
	$(CAT) $(DATADIR)/$(VARFILENAME).tfvars.json
#
# build image
# build_image: VARFILEPATH=$(DATADIR)/$(VARFILENAME).tfvars.json
varfilepath: datadir varfile
	VARFILEPATH=$(DATADIR)/$(VARFILENAME).tfvars.json
	$(WRITE) "variable file path: $(VARFILEPATH)"

type_validation: type
	VALIDTYPE=$(or $(filter $(TYPE),$(VALIDTYPES)),$(error $$TYPE [$(TYPE)] must be one of $(VALIDTYPES)))

release_validation: release
	VALIDRELEASE=$(or $(filter $(RELEASE),$(VALIDRELEASES)),$(error $$RELEASE [$(RELEASE)] must be one of $(VALIDRELEASES)))

ifeq ($(TYPE),$(OLTYPE))
TEMPLATEPATH=$(HOMETEMPLATES)/ol-kvm-image-template.json
else ifeq ($(TYPE),$(ALTYPE))
TEMPLATEPATH=$(HOMETEMPLATES)/al-kvm-image-template.json
endif

template:
	$(WRITE) $(TEMPLATEPATH)

build_image: type_validation release_validation varfilepath template
	$(WRITE) "no proxy: $${no_proxy}"
	$(WRITE) "$(PACKER) build --on-error=ask -var-file=$(DATADIR)/$(VARFILENAME).tfvars.json $(TEMPLATEPATH)"
	$(PACKER) build --on-error=ask -var-file=$(DATADIR)/$(VARFILENAME).tfvars.json $(TEMPLATEPATH)

all: configure build_image
	$(WRITE) "build $(TYPE) kvm image."
