Name: oci-utils
Version: 0.10.1
Release: 1%{?dist}
Url: http://cloud.oracle.com/iaas
Summary: Oracle Cloud Infrastructure utilities
License: UPL
Group: Development/Tools
Source: %{name}-%{version}.tar.gz

# Oracle Linux 8
%if 0%{?rhel} >= 8
%define __l_python %{__python3}
%define __l_python_sitelib %{python3_sitelib}
%else
%define __l_python %{__python2}
%define __l_python_sitelib %{python2_sitelib}
%endif



BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot

%{?systemd_requires}

BuildArch: noarch

BuildRequires: systemd
# Oracle Linux 8
%if 0%{?rhel} >= 8
BuildRequires: python3-devel
BuildRequires: python3-setuptools
BuildRequires: python3-flake8
Requires: python3
Requires: python3-daemon
Requires: python3-sdnotify
Requires: python3-six
Requires: python3-enum34
# Oracle Linux 7
%else
BuildRequires: python-devel
BuildRequires: python-setuptools
BuildRequires: python-flake8
Requires: python
Requires: python-daemon
Requires: python-sdnotify
Requires: python-six
%endif

Requires: cloud-utils-growpart
# for lsblk
Requires: util-linux
# for iscsiadm
Requires: iscsi-initiator-utils


%description
A package with useful scripts for querying/validating the state of Oracle Cloud Infrastructure instances running Oracle Linux and facilitating some common configuration tasks.

%package kvm
Summary: Utilitizes for managing virtualization in Oracle Cloud Infrastructure
Group: Development/Tools
Requires: %{name} = %{version}-%{release}
%if 0%{?rhel} >= 8
Requires: python3-netaddr
%else
Requires: python-netaddr
%endif
%description kvm
Utilities for creating and managing KVM guests that use Oracle Cloud Infrastructure resources, such as block storage and networking, directly.

%package outest
Summary: OCI utils tests
Group: Development/Tools
Requires: %{name} = %{version}-%{release}
%description outest
Utilities unit tests

%pre
# some old version of oci-utils, used to leave this behind.
%{__rm} -f /var/tmp/oci-utils.log*

%prep
%setup -q -n %{name}-%{version}

%build
%{__l_python} setup.py build

%install
%{__l_python} setup.py install -O1 --prefix=%{_prefix} --root=%{buildroot}
%{__mkdir_p} %{buildroot}%{_localstatedir}/lib/oci-utils
# use for outest package
%{__mkdir_p} $RPM_BUILD_ROOT/opt/oci-utils
%{__mkdir_p} $RPM_BUILD_ROOT/opt/oci-utils/lib
%{__cp} -r tests %{buildroot}/opt/oci-utils
%{__cp} -r setup.cfg %{buildroot}/opt/oci-utils
%{__cp} -r setup.py %{buildroot}/opt/oci-utils
%{__cp} -r requirements.txt %{buildroot}/opt/oci-utils
%{__cp} -r README %{buildroot}/opt/oci-utils

%if 0%{?rhel} >= 8
%{echo: "Running python3 convertion tool"}
/usr/bin/2to3 --no-diffs --write --nobackups  %{buildroot}
# force run on ones not suffixed by .py
/usr/bin/2to3 --no-diffs --write --nobackups  %{buildroot}/%{_libexecdir}/oci-utils-config-helper
%endif

# temporary workaround to EOL vnic script: move it else where
%{__mv} %{buildroot}/usr/libexec/secondary_vnic_all_configure.sh %{buildroot}%{python2_sitelib}/oci_utils/impl/.vnic_script.sh


%clean
rm -rf %{buildroot}

%files
%exclude %dir %{__l_python_sitelib}/oci_utils/kvm
%exclude %{__l_python_sitelib}/oci_utils/kvm/*
%exclude %{_bindir}/oci-kvm
%exclude %{_datadir}/man/man1/oci-kvm.1.gz
%defattr(-,root,root)
%{__l_python_sitelib}/oci_utils*
%{_bindir}/oci-*
%exclude %{_bindir}/oci-kvm
%{_libexecdir}/
%{_sysconfdir}/systemd/system/ocid.service
%{_prefix}/lib/systemd/system-preset/91-oci-utils.preset
%dir %attr(0755,root,root) %{_sysconfdir}/oci-utils.conf.d
%config %{_sysconfdir}/oci-utils.conf.d/00-oci-utils.conf
%dir %attr(0755,root,root) %{_sysconfdir}/oci-utils
%config %{_sysconfdir}/oci-utils/oci-image-cleanup.conf
%{_datadir}/man
%exclude %{_datadir}/man/man1/oci-kvm.1.gz
%dir %{_localstatedir}/lib/oci-utils
%doc LICENSE.txt PKG-INFO

%files kvm
%{_bindir}/oci-kvm
%{_libexecdir}/oci-kvm-config.sh
%{_libexecdir}/oci-kvm-network-script
%{__l_python_sitelib}/oci_utils/kvm*
%{_datadir}/man/man1/oci-kvm.1.gz
%{_sysconfdir}/systemd/system/oci-kvm-config.service
%{_prefix}/lib/systemd/system-preset/91-oci-kvm.preset
%config %{_sysconfdir}/oci-utils.conf.d/10-oci-kvm.conf

%files outest
/opt/oci-utils

%post kvm
%systemd_post oci-kvm-config.service

%preun kvm
%systemd_preun oci-kvm-config.service

%changelog
* Mon Sep 9 2019 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.10.1
- Added support of libvirt network for KVM guests

* Mon Apr 08 2019 Wiekus Beukes <wiekus.beukes@oracle.com> --0.10.0
- Added flake8 build requirement
- Changed all remaining /usr/bin/python entries to python2.7

* Wed Mar 27 2019 Wiekus Beukes <wiekus.beukes@oracle.com> --0.9.1
- Updated the to be able build under Oracle Linux 8 Beta 1

* Fri Feb 1 2019  Qing Lin <qing.lin@oracle.com> --0.9.0
- oci-metadata - added support for --value-only, which works with one get option, return the value only.
- LINUX-498 -oci-metadata added --value-only option, which works with one get option, return the value only.
- LINUX-560 - Cleanup utility not preserving permissions/ownerships (fixed)
              same as bug-29260959.


* Fri Oct 26 2018  Qing Lin <qing.lin@oracle.com> --0.8
- OLOCITOOLS-11 - implemented method for retrieving metadata for other compute instances.
- OLOCITOOLS-12 - implemented oci-metadata --export
- OLOCITOOLS-10 - added support for updating instance metadata for a specified instance.

* Tue Oct 02 2018  Qing Lin <qing.lin@oracle.com> --0.7.1-3
- bug-28643343 - fixed most of the exceptions for oci config error.
- bug-28599902 - enhanced oci-public-ip to return all public ips with new option "-a|--all".
- bug-28048699 - oci-utils needs to handle multiple physical NICs when creating secondary vnics

* Wed Sep 19 2018 Laszlo (Laca) Peter <laszlo.peter@oracle.com> --0.7.1-1
- fix bug 28668447 - ocid needs to allow time for iSCSI connection to recover

* Wed Sep 19 2018  Qing Lin <qing.lin@oracle.com> --0.7-4
- fix bug 28653583 - private ips assigned on wrong vnic.

* Fri Aug 31 2018 Qing Lin <qing.lin@oracle.com>  --0.7
- bump version to 0.7
- added oci-network-inspector to listing networking information.(OLOCITOOLS-5)
- added oci-growfs to support to grow filesystems (OLOCITOOLS-7)
  Currently only / boot volume is expendable.
- fixed bugs in oci-iscsi-config:
  1. fixed: mis-list sdaa.. as partition of sda. It should be a seperate volume.(bug-28433320)
  2. fixed: max_volumes usage in create and attach.
  3. fixed: should not create a volume if it failed to attach (bug-28513898)
  4. privilege adjustment for create and destroy(root+oci), attach and detach(root)
  5. some code cleanup.
- fixed bug oci-network-config
  1. fixed secondary ips on secondary VNICs not reachable issue.(bug-28498139)
- expanded 'OCI' to 'Oracle Cloud Infrastructure' in man pages, specfiles (OLOCITOOLS-8)

* Thu May 10 2018 Daniel Krasinski <daniel.krasinski@oracle.com>  --16
- merged latest oci-kvm code into mainline version

* Wed May 09 2018 Qing Lin <qing.lin@oracle.com>   --11
- move the oci-image-cleanup.conf to /etc/oci-utils/.

* Thu May 03 2018 Qing Lin <qing.lin@oracle.com>   --8
- merged changes from Sweekar: force,restore, backup-dir option.
- enhanced force option with value support: y for delete all; n for dryrun.
- added configuration file support for oci-image-cleanup
- fixed history cleanup bug.

* Wed Apr 25 2018 Qing Lin <qing.lin@oracle.com>   --5
- fixed history not clean bug.
- added running requirement for root privileges.
- move oci-image-cleanup from /usr/bin to /usr/libexec/
- move its manual from man1 to man8.

* Fri Apr 20 2018 Qing Lin <qing.lin@oracle.com>   --4
- added oci-image-cleanup and its manual.

* Tue Apr 17 2018 Laszlo (Laca) Peter <laszlo.peter@oracle.com>
- added oci-utils-kvm package

* Fri Mar 23 2018 Daniel Krasinski <daniel.krasinski@oracle.com>
- migrated kvm-specific features into oci-utils-kvm

* Wed Mar  7 2018 Daniel Krasinski <daniel.krasinski@oracle.com>
- added empty oci-utils-kvm package to facilitate splitting oci-kvm from oci-utils

* Fri Oct  6 2017 Laszlo (Laca) Peter <laszlo.peter@oracle.com>
- initial spec file for oci-utils
