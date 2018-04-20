Name: oci-utils
Version: 0.6
Release: 4%{?dist}
Url: http://cloud.oracle.com/iaas
Summary: Oracle Cloud Infrastructure utilities
License: UPL
Group: Development/Tools
Source: %{name}-%{version}.tar.gz
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot
%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}

BuildArch: noarch

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
mkdir -p %{buildroot}%{_localstatedir}/lib/oci-utils

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root)
%{python_sitelib}/oci_utils*
%{_bindir}/oci-*
%exclude %{_bindir}/oci-kvm
%{_libexecdir}/ocid
%{_libexecdir}/oci-utils-config-helper
%{_libexecdir}/secondary_vnic_all_configure.sh
%{_sysconfdir}/systemd/system/ocid.service
%dir %attr(0755,root,root) %{_sysconfdir}/oci-utils.conf.d
%config %{_sysconfdir}/oci-utils.conf.d/00-oci-utils.conf
%{_datadir}/man
%exclude %{_datadir}/man/man1/oci-kvm.1.gz
%dir %{_localstatedir}/lib/oci-utils
%doc LICENSE.txt PKG-INFO

%files kvm
%{_bindir}/oci-kvm
%{_datadir}/man/man1/oci-kvm.1.gz
%config %{_sysconfdir}/oci-utils.conf.d/10-oci-kvm.conf

%changelog
* Fri Apr 20 2018 Qing Lin <qing.lin@oracle.com>   --4
- added oci-image-cleanup and its manual.

* Tue Apr 17 2018 Laszlo (Laca) Peter <laszlo.peter@oracle.com>
- added oci-utils-kvm package

* Fri Oct  6 2017 Laszlo (Laca) Peter <laszlo.peter@oracle.com>
- initial spec file for oci-utils
