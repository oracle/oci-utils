Name: oci-utils
Version: 0.11.0
Release: 0%{?dist}
Url: http://cloud.oracle.com/iaas
Summary: Oracle Cloud Infrastructure utilities
License: UPL
Group: Development/Tools
Source: %{name}-%{version}.tar.gz

BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot

%{?systemd_requires}

BuildArch: noarch

BuildRequires: systemd

BuildRequires: python3-devel
BuildRequires: python3-setuptools
BuildRequires: python-flake8
Requires: python3
Requires: python3-daemon
Requires: python3-sdnotify

%description
A package with useful scripts for querying/validating the state of Oracle Cloud Infrastructure instances running Oracle Linux and facilitating some common configuration tasks.

%package migrate
Summary: Migrate vm from on-premise to the OCI
Group: Development/Tools
Requires: util-linux
Requires: parted
Requires: python36-pyyaml
Requires: qemu-img >= 15:3.1
%description migrate
Utilities for migrating on-premise guests to Oracle Cloud Infrastructure.

%pre
# some old version of oci-utils, used to leave this behind.
%{__rm} -f /var/tmp/oci-utils.log*

%prep
%setup -q -n %{name}-%{version}

%build
%{__python3} setup.py build

%install
%{__python3} setup.py install -O1 --prefix=%{_prefix} --root=%{buildroot}
%{__mkdir_p} %{buildroot}%{_localstatedir}/lib/oci-utils

%clean
rm -rf %{buildroot}

%files

%exclude %{_bindir}/oci-image-migrate
%exclude %{_bindir}/oci-image-migrate-import
%exclude %{_datadir}/man/man1/oci-image-migrate.1.gz
%exclude %{_datadir}/man/man1/oci-image-migrate-import.1.gz
%defattr(-,root,root)
%{python3_sitelib}/oci_utils*
%{_bindir}/oci-*
%exclude %{_bindir}/oci-image-migrate
%exclude %{_bindir}/oci-image-migrate-import
%{_datadir}/man
%dir %{_localstatedir}/lib/oci-utils
%doc LICENSE.txt PKG-INFO

%files migrate
%{_bindir}/oci-image-migrate
%{_bindir}/oci-image-migrate-import
%{python3_sitelib}/oci_utils/__init__*
%{python3_sitelib}/oci_utils/exceptions*
%{python3_sitelib}/oci_utils/impl/__init__*
%{python3_sitelib}/oci_utils/impl/oci-image-migrate*
%{python3_sitelib}/oci_utils/migrate*
%{_datadir}/man/man1/oci-image-migrate*1.gz
%config %{_sysconfdir}/oci-utils/oci-migrate-conf.yaml

%changelog
* Fri Feb 7 2020 Guido Tijskens <guido.tijskens@oracle.com> -- 0.11.0-0
- Full python3 code

* Tue Jan 7 2020 Guido Tijskens <guido.tijskens@oracle.com> -- 0.10.2-3
- Added oci-image-migrate-import utility

* Thu Dec 12 2019 Guido Tijskens <guido.tijskens@oracle.com> -- 0.10.2-2
- Added oci-image-migrate utility.

* Wed Dec 4 2019 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.10.2
- Update to use Python 3 on OL8

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
