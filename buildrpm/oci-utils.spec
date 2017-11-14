Name: oci-utils
Version: 0.3
Release: 1%{?dist}
Url: http://cloud.oracle.com/iaas
Summary: Oracle Cloud Infrastructure utilities
License: GPLv2
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
     
%prep
%setup -q -n %{name}-%{version}

%build
%{__python} setup.py build

%install
%{__python} setup.py install -O1 --prefix=%{_prefix} --root=%{buildroot}

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root)
%{python_sitelib}/oci_utils*
%{_bindir}/oci-*
%{_libexecdir}/ocid
%{_sysconfdir}/systemd/system/ocid.service
%doc COPYING PKG-INFO

%changelog
* Fri Oct  6 2017 Laszlo (Laca) Peter <laszlo.peter@oracle.com>
- initial spec file for oci-utils
