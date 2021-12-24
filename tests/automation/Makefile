# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.
#
# makefile for oci-utils-automation
#
#
TARGET=oci-utils-automation
CONFIGDIR=git_repo/tests/automation/configuration
# CONFIGDIR=configuration
DOCFILES=$(CONFIGDIR)/README.txt $(CONFIGDIR)/BUILD.txt
USRFILES=$(CONFIGDIR)/oci-utils-automation.repo-7 $(CONFIGDIR)/oci-utils-automation.repo-8
DISTRIBUTIONS=OL7 OL8
GPGFILES=$(CONFIGDIR)/RPM-GPG*
RELDATA=$(CONFIGDIR)/oci-utils-automation.spec
#
VER=$(shell sed -n "/Version:/p" ${RELDATA} |sed -e 's/Version:\ *//')
REL=$(shell sed -n "/Release:/p" ${RELDATA} |sed -e 's/Release:\ *//'| sed -e 's/\%.*//')
VERSION=${VER}-${REL}
VERSIONRPM=${VER}
TMPDIR="oci-utils-automation-$(VERSIONRPM)"
NOW=$(shell date +%d%m%Y_%H%M)
#
DESTDIR=/var/www/html/channel_rpms/$(USER)
YUMDIR=/var/www/html/yum/$(USER)
ISODIR=/var/www/html/isos
#
MKDIR=-mkdir -p
SUMKDIR=sudo mkdir -p
SURMDIR=sudo rm -rf
CHMODEXEC=chmod 755
CURL=curl
SUCHOWN=sudo chown -R
CHANGEDIR=cd
WRITE=@echo
INSTALL=install -m 644 -t ${DESTDIR}
REMOVE=@-rm -f
RECREM=@-rm -rf
COPYR=cp -a --parents
COPYA=cp -a
COPYANOFAIL=-cp -a
BACKUP=cp --preserve
TAR=tar -czvf
RPMBUILD=rpmbuild -v -ba 
THISDIR=${PWD}
SED=sed -i
GREP=egrep
AWKFOR=awk -F: '{print $$4}'
CREATEREPO=createrepo -q -c 
THISIP=$(shell hostname -I|tr -d '[:space:]')
THISGROUP=$(shell ${GREP} $(USER): /etc/passwd | $(AWKFOR))
#
# help
#
.PHONY: help
help:
	$(WRITE) "help info:"
	$(WRITE) " for the install of $(TARGET) version ${VERSION}"
	$(WRITE) " make help"
	$(WRITE) " make showversion"
	$(WRITE) " make distro"
	$(WRITE) " make directorystructure"
	$(WRITE) " make rpms"
	$(WRITE) " make repos"
	$(WRITE) " make publish"
	$(WRITE) " make clean"
	$(WRITE) " for adding rpm $(RPM) to repository for distro ${DISTR}"
	$(WRITE) " make copyrpm RPM=[path|url to rpm] DISTRO=[OL7|OL8]"
	$(WRITE) " make isodir"
	$(WRITE) " make cleanrepo"

#
# version info
.PHONY: showversion ${SOURCEFILES}
showversion:
	$(WRITE) "version of $(TARGET) source is $(VERSION)"
#
#
# create tarball and update repofiles with $USER
distro: $(USRFILES)
	${RECREM} $(TMPDIR)
	${MKDIR} $(TMPDIR)
	${SED} s/_UUUU_/$(USER)/ $^
	${SED} s/_IPIP_/$(THISIP)/ $^
	${COPYR} ${USRFILES} $(TMPDIR)
	$(COPYA) ${RELDATA} $(TMPDIR)
	$(COPYA) Makefile $(TMPDIR)
	$(COPYA) ${DOCFILES} $(TMPDIR)
	$(COPYA) ${GPGFILES} $(TMPDIR)
	${TAR} $(TARGET)-$(VERSIONRPM).tar.gz $(TMPDIR)/*
	${RECREM} $(TMPDIR)/
	$(WRITE) "Distribution package created as $(TARGET)-$(VERSION).tar.gz"
#
#
# create directories
directorystructure: distro
	${MKDIR} rpmbuild/RPMS/noarch
	${MKDIR} rpmbuild/SOURCES
	${MKDIR} rpmbuild/SRPMS
	${MKDIR} rpmbuild/RPMS
	${MKDIR} rpmbuild/BUILD
	${MKDIR} rpmbuild/BUILDROOT
	${MKDIR} rpmbuild/SPECS
	$(COPYA) $(TARGET)-$(VERSIONRPM).tar.gz rpmbuild/SOURCES
	$(COPYA) $(CONFIGDIR)/$(TARGET).spec rpmbuild/SPECS
	$(WRITE) "created directory structure"
#
#
# buildrpms
rpms: directorystructure
	${RPMBUILD} --define '_topdir $(PWD)/rpmbuild' rpmbuild/SPECS/$(TARGET).spec --define "dist .el7" 
	${RPMBUILD} --define '_topdir $(PWD)/rpmbuild' rpmbuild/SPECS/$(TARGET).spec --define "dist .el8" 
	$(WRITE) "rpms build"
#
#
# repos
repos: 
	$(foreach distro,$(DISTRIBUTIONS), ${SUMKDIR} $(YUMDIR)/$(distro)/x86_64/getPackage;)
	$(foreach distro,$(DISTRIBUTIONS), ${SUCHOWN} $(USER):${THISGROUP} $(YUMDIR)/$(distro);)
#
#
# publish
publish: repos rpms
	$(WRITE) "${DESTDIR}"
	${SUMKDIR} ${DESTDIR}
	sudo $(COPYA) rpmbuild/RPMS/noarch/* ${DESTDIR}
	sudo chcon -R -t httpd_sys_content_t $(dir $(DESTDIR))
	$(WRITE) "moved rpms to ${DESTDIR}"
#
#
# clean
clean:
	${RECREM} rpmbuild
	${REMOVE} oci-utils-automation*tar.gz
	$(WRITE) "cleaned up"
#
#
# copy rpm to repo
copyrpm: repos
ifdef RPM
	$(WRITE) $(RPM)
ifdef DISTRO
	$(WRITE) $(DISTRO)
ifneq (,$(findstring http, $(RPM)))
	$(WRITE) "$(RPM) is a URL"
	$(CURL) $(RPM) --output $(YUMDIR)/$(DISTRO)/x86_64/getPackage/$(notdir $(RPM))
else
	$(WRITE) "$(RPM) is a FILE"
	$(COPYA) $(RPM) $(YUMDIR)/$(DISTRO)/x86_64/getPackage
endif
	$(CREATEREPO) $(YUMDIR)/$(DISTRO)/x86_64/.cache $(YUMDIR)/$(DISTRO)/x86_64
	sudo chcon -R -t httpd_sys_content_t $(dir $(YUMDIR)/$(DISTRO))
else
	$(WRITE) "DISTRO missing"
endif
else
	$(WRITE) "RPM missing"
endif
#
#
# make directory for storing iso's with respect to oci-kvm rpm and oci-kvm image tests
isodir:
	${SUMKDIR} $(ISODIR)
	sudo chcon -R -t httpd_sys_content_t $(ISODIR)
#
#
# clean up repositories
cleanrepo:
	$(foreach distro,$(DISTRIBUTIONS), ${SURMDIR} $(YUMDIR)/$(distro)/x86_64/getPackage;)