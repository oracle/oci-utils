Name: oci-utils
Version: 0.12.0
Release: 1%{?dist}
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
Requires: python3
Requires: python3-daemon
Requires: python3-sdnotify
Requires: xfsprogs
Requires: cloud-utils-growpart
# for lsblk
Requires: util-linux
# for iscsiadm
Requires: iscsi-initiator-utils
# for notify for now
Requires: python36-oci-cli
Requires: python36-oci-sdk
#
%if 0%{?rhel} == 7
Requires: python36-netaddr
%else
Requires: network-scripts
Requires: python3-netaddr
%endif

%description
A package with useful scripts for querying/validating the state of Oracle Cloud Infrastructure instances running Oracle Linux and facilitating some common configuration tasks.

%package kvm
Summary: Utilitizes for managing virtualization in Oracle Cloud Infrastructure
Group: Development/Tools
Requires: %{name} = %{version}-%{release}

%if 0%{?rhel} >= 8
Requires: python3-libvirt
%else
Requires: python36-libvirt
%endif

%description kvm
Utilities for creating and managing KVM guests that use Oracle Cloud Infrastructure resources, such as block storage and networking, directly.

%package outest
Summary: OCI utils tests
Group: Development/Tools
Requires: %{name} = %{version}-%{release}
%description outest
Utilities unit tests

%package migrate
Summary: Migrate vm from on-premise to the OCI
Group: Development/Tools
Requires: util-linux
Requires: parted
Requires: bind-utils
Requires: qemu-img >= 15:2.12
# for upload and import
Requires: python36-oci-cli
%if 0%{?rhel} == 7
Requires: python36-pyyaml
Requires: python36-requests
%else
Requires: python3-pyyaml
Requires: python3-requests
Requires: python36
%endif
%description migrate
Utilities for migrating on-premise guests to Oracle Cloud Infrastructure.

%package oumtest
Summary: OCI utils migrate tests
Group: Development/Tools
Requires: %{name}-migrate = %{version}-%{release}
%description oumtest
Utilities migrate unit tests

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
# use for outest and oumtest package
%{__mkdir_p} $RPM_BUILD_ROOT/opt/oci-utils
%{__mkdir_p} $RPM_BUILD_ROOT/opt/oci-utils/lib
%{__cp} -r tests %{buildroot}/opt/oci-utils
%{__cp} -r setup.cfg %{buildroot}/opt/oci-utils
%{__cp} -r setup.py %{buildroot}/opt/oci-utils
%{__cp} -r requirements.txt %{buildroot}/opt/oci-utils
%{__cp} -r README %{buildroot}/opt/oci-utils

%clean
rm -rf %{buildroot}

%files
%exclude %dir %{python3_sitelib}/oci_utils/kvm
%exclude %{python3_sitelib}/oci_utils/kvm/*
%exclude %{_bindir}/oci-kvm
%exclude %{_datadir}/man/man1/oci-kvm.1.gz
%exclude %{_bindir}/oci-image-migrate*
%exclude %{_datadir}/man/man1/oci-image-migrate*1.gz
%defattr(-,root,root)
%{python3_sitelib}/oci_utils*
%{_bindir}/oci-*
%exclude %{_bindir}/oci-kvm
%{_libexecdir}/
%{_sysconfdir}/systemd/system/ocid.service
%{_prefix}/lib/systemd/system-preset/91-oci-utils.preset
%dir %attr(0755,root,root) %{_sysconfdir}/oci-utils.conf.d
%config %{_sysconfdir}/oci-utils.conf.d/00-oci-utils.conf
%dir %attr(0755,root,root) %{_sysconfdir}/oci-utils
%config %{_sysconfdir}/oci-utils/oci-image-cleanup.conf
%exclude %{_bindir}/oci-image-migrate*
%exclude %{python3_sitelib}/oci_utils/impl/migrate
%exclude %{python3_sitelib}/oci_utils/migrate
%{_datadir}/man
%exclude %{_datadir}/man/man1/oci-kvm.1.gz
%dir %{_localstatedir}/lib/oci-utils
%doc LICENSE.txt PKG-INFO

%files kvm
%{_bindir}/oci-kvm
%{_libexecdir}/oci-kvm-config.sh
%{_libexecdir}/oci-kvm-network-script
%{python3_sitelib}/oci_utils/kvm*
%{_datadir}/man/man1/oci-kvm.1.gz
%{_sysconfdir}/systemd/system/oci-kvm-config.service
%{_prefix}/lib/systemd/system-preset/91-oci-kvm.preset
%config %{_sysconfdir}/oci-utils.conf.d/10-oci-kvm.conf

%files outest
%exclude /opt/oci-utils/tests/test_mig*
/opt/oci-utils

%post kvm
%systemd_post oci-kvm-config.service

%preun kvm
%systemd_preun oci-kvm-config.service

%files migrate
%{_bindir}/oci-image-migrate*
%{python3_sitelib}/oci_utils/__init__*
%{python3_sitelib}/oci_utils/exceptions*
%{python3_sitelib}/oci_utils/impl/__init__*
%{python3_sitelib}/oci_utils/impl/migrate
%{python3_sitelib}/oci_utils/migrate
%{_datadir}/man/man1/oci-image-migrate*1.gz
%config %{_sysconfdir}/oci-utils/oci-migrate-conf.yaml


%files oumtest
/opt/oci-utils/lib
/opt/oci-utils/tools
/opt/oci-utils/tests/data
/opt/oci-utils/README
/opt/oci-utils/requirements.txt
/opt/oci-utils/setup*
/opt/oci-utils/tests/test_mig*
/opt/oci-utils/tests/__init__*

%changelog
* Tue Dec 1 2020 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.0-1
 - update migrate

* Tue Nov 10 2020 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.12.0
 - LINUX-9546 - oci-image-cleanup --dry-run do not print the plan directly
 - oci-iscsi-config usage refactor
 - LINUX-9202 - oci-network-config error in oci_utils.exceptions.OCISDKError: Failed to fetch instance
 - LINUX-8946 - no warning when user select primary vnic

* Fri Oct 9 2020 Guido Tijskens <guido.tijskens@oracle.com> --0.11.6-1
- oci-image-migrate code cleanup

* Thu Sep 24 2020 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.11.6
- LINUX-7035 - oci-utils: move base functionality from al-config to oci-utils
- LINUX-8976 - multi-vnic on bare metal shapes suffer from connection issues
- LINUX-8952 - oci-growfs does not prompt for y/n and hangs.
- LINUX-8946 - no warning when user select primary vnic


* Wed Sep 16 2020 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.11.5
- LINUX-6752 - add dependency on OCI python sdk

* Tue Sep 15 2020 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.11.4
- LINUX-7035 - introduce oci-notify tool to send notification to OCI notification service

* Wed Sep 9 2020 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.11.3.6
- LINUX-8607 - ssh keys not cleanup for some users
- LINUX-8426 - On BM shape when link is down, VF are missing

* Tue Aug 25 2020 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.11.3.3
- LINUX-7986 - fix crash while printing network interfaces on BM shapes with oci-network-config command
- LINUX-7918 - fix regression on -n option of oci-kvm command
- LINUX-7918 - fix free vnic search for oci-kvm command on BM shapes
- LINUX-8011 - interpreter crashes displaying iSCSI information

* Mon Aug 17 2020 Guido Tijskens <guido.tijskens@oracle.com> --0.11.3.1
- ACL-180

* Tue Aug 4 2020 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.11.3
- LINUX-7672 - fix for python3 byte handling issue.

* Thu Jul 16 2020 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.11.2
- support for LVM root filesystem in oci-growfs

* Wed Jul 2 2020 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.11.1
- multi vnic support for KVM guests
- removal of libexec/secondary_vnic_all_configure.sh, replaced by python implementation
- oci-kvm, added sanity around parameters passes as part of extra-args option

* Wed Apr 1 2020 Guido Tijskens <guido.tijskens@oracle.com> -- 0.11.0
- add oci-image-migrate code
- remove of python2 support on all platform
- move to by-uuid device name for libvirt storage pool build

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
