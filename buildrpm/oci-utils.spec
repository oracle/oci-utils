Name: oci-utils
Version: 0.6
Release: 11%{?dist}
Url: http://cloud.oracle.com/iaas
Summary: Oracle Cloud Infrastructure utilities
License: UPL
Group: Development/Tools
Source: %{name}-%{version}.tar.gz
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot
%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}
%{?systemd_requires}

BuildArch: noarch

BuildRequires: systemd
BuildRequires: python2-devel
BuildRequires: python-setuptools
Requires: python2
Requires: python-daemon
Requires: python-lockfile
Requires: python-sdnotify
# for lsblk
Requires: util-linux
# for iscsiadm
Requires: iscsi-initiator-utils

%description
A package with useful scripts for querying/validating the state of OCI instances running Oracle Linux and facilitating some common configuration tasks.
     
%package kvm
Summary: Utilitizes for managing virtualization in Oracle Cloud Infrastructure
Group: Development/Tools
Requires: %{name} = %{version}-%{release}
%description kvm
Utilities for creating and managing KVM guests that use Oracle Cloud Infrastructure resources, such as block storage and networking, directly.

%prep
%setup -q -n %{name}-%{version}

%build
%{__python} setup.py build

%install
%{__python} setup.py install -O1 --prefix=%{_prefix} --root=%{buildroot}
mkdir -p %{buildroot}%{_localstatedir}/lib/oci-utils

%clean
rm -rf %{buildroot}

%files
%exclude %dir %{python_sitelib}/oci_utils/kvm
%exclude %{python_sitelib}/oci_utils/kvm/*
%exclude %{_bindir}/oci-kvm
%exclude %{_datadir}/man/man1/oci-kvm.1.gz
%defattr(-,root,root)
%{python_sitelib}/oci_utils*
%{_bindir}/oci-*
%exclude %{_bindir}/oci-kvm
%{_libexecdir}/
%{_sysconfdir}/systemd/system/ocid.service
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
%{python_sitelib}/oci_utils/kvm*
%{_datadir}/man/man1/oci-kvm.1.gz
%{_sysconfdir}/systemd/system/oci-kvm-config.service
%{_prefix}/lib/systemd/system-preset/91-oci-utils.preset
%{_datadir}/man/man1/oci-kvm.1.gz
%config %{_sysconfdir}/oci-utils.conf.d/10-oci-kvm.conf

%post kvm
%systemd_post oci-kvm-config.service

%preun kvm
%systemd_preun oci-kvm-config.service

%changelog
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
