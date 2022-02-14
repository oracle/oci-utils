Summary:       oci-utils automation build and test utils
Name:          oci-utils-automation
Version:       0.2.2
Url:           http://cloud.oracle.com/iaas
Release:       0%{?dist}
License:       UPL
Group:         Development/Tools
Source0:       oci-utils-automation-%{version}.tar.gz
BuildArch:     noarch

BuildRoot:     /tmp/oci-utils-automation

%define is_el7  %(test "%{?dist}" = ".el7"  && echo 1 || echo 0)
%define is_el8  %(test "%{?dist}" = ".el8"  && echo 1 || echo 0)

%define os_id /etc/redhat-release
# Default to ol7 
%if %is_el7
%define os_version 7|7Server
%define os_tag 7
%endif

%if %is_el8
%define os_version 8|8Server
%define os_tag 8
%endif

Requires:      rpm
Requires:      %{os_id}

%description
This package contains utils for automation of oci-utils build and testing

%prep
%setup -q

%build

%install
[ "${RPM_BUILD_ROOT}" != "/" ] && rm -rf "${RPM_BUILD_ROOT}"
mkdir -p "${RPM_BUILD_ROOT}/etc/yum.repos.d"
mkdir -p "${RPM_BUILD_ROOT}/usr/share/rhn"
# cp oci-utils-automation.repo-%{os_tag} ${RPM_BUILD_ROOT}/etc/yum.repos.d/oci-utils-automation.repo
cp %{getenv:HOME}/git_repo/tests/automation/configuration/oci-utils-automation.repo-%{os_tag} ${RPM_BUILD_ROOT}/etc/yum.repos.d/oci-utils-automation.repo
cp RPM-GPG-KEY-oracle-%{os_tag}   ${RPM_BUILD_ROOT}/usr/share/rhn/RPM-GPG-KEY-oracle

%clean
[ "${RPM_BUILD_ROOT}" != "/" ] && rm -rf "${RPM_BUILD_ROOT}"

%files
%defattr(644, root, root)
/etc/yum.repos.d/oci-utils-automation.repo
/usr/share/rhn/RPM-GPG-KEY-oracle

%pre
# Exit if this is a GIT machine
if [ -f /usr/local/git/etc/mkks-iso-version ] ||  [ -f /etc/OSCC-Release ] ; then
   echo "
 This is a GIT machine. This package is not for production machines.

 Aborting...
     "
   exit 1
fi

# Check OS release
egrep "%{os_version}" /etc/redhat-release > /dev/null 2>&1
if [ $? -ne 0 ] ; then
  echo "
   Installed OS is not supported by this version of oci-utils-automation.
   "
  exit 1
fi

%post
# Backup and install config files
tstamp=`date -u +%Y-%m-%d-%H:%M`
[ -f /etc/sysconfig/rhn/sources     ] && mv /etc/sysconfig/rhn/sources /etc/sysconfig/rhn/sources.uln-$tstamp
[ -f /etc/yum.repos.d/oci-utils-automation.repo ] && cp /etc/yum.repos.d/oci-utils-automation.repo /etc/yum.repos.d/oci-utils-automation.repo.uln-$tstamp
# cp /usr/share/rhn/RPM-GPG-KEY-oracle /usr/share/rhn/RPM-GPG-KEY-oracle
cp /usr/share/rhn/RPM-GPG-KEY-oracle /etc/pki/rpm-gpg/RPM-GPG-KEY-oracle
rpm --import /usr/share/rhn/RPM-GPG-KEY-oracle 

%changelog
* Tue Nov 9 2021 Guido Tijskens <guido.tijskens@oracle.com> ( 0.2.2-0)
- fixed os release check

* Wed Sep 15 2021 Guido Tijskens <guido.tijskens@oracle.com> ( 0.2.1-0)
- update structure

* Wed Nov 18 2020 Guido Tijskens <guido.tijskens@oracle.com> ( 0.1.1-1 )
- user specific channels

* Tue Nov 10 2020 Guido Tijskens <guido.tijskens@oracle.com> ( 0.1.1-0 )
- initial version
