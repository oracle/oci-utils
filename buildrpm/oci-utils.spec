Name: oci-utils
Version: 0.5.3kvm
Release: 1%{?dist}
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
%{_libexecdir}/ocid
%{_libexecdir}/secondary_vnic_all_configure.sh
%{_sysconfdir}/systemd/system/ocid.service
%{_datadir}/man
%doc LICENSE.txt PKG-INFO

%files kvm
%{_bindir}/oci-kvm
%{_libexecdir}/oci-vmnet
%{python_sitelib}/oci_utils/kvm*
%{_datadir}/man/man1/oci-kvm.1.gz
%{_sysconfdir}/systemd/system/oci-vmnet.service
%{_sysconfdir}/systemd/system/ocid.service.d/oci-vmnet.conf
%{_prefix}/lib/systemd/system-preset/91-oci-utils.preset

%post kvm
%systemd_post oci-vmnet.service

%preun kvm
%systemd_preun oci-vmnet.service

%changelog
* Fri Mar 23 2018 Daniel Krasinski <daniel.krasinski@oracle.com>
- migrated kvm-specific features into oci-utils-kvm

* Wed Mar  7 2018 Daniel Krasinski <daniel.krasinski@oracle.com>
- added empty oci-utils-kvm package to facilitate splitting oci-kvm from oci-utils

* Fri Oct  6 2017 Laszlo (Laca) Peter <laszlo.peter@oracle.com>
- initial spec file for oci-utils
