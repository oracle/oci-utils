Name: oci-utils
Version: 0.14.0
Release: 3%{?dist}
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
#
Requires: xfsprogs
Requires: cloud-utils-growpart
# for lsblk
Requires: util-linux
# for iscsiadm
Requires: iscsi-initiator-utils
#
%if 0%{?rhel} == 9
Requires: python39-oci-sdk
Requires: python3-netaddr
Requires: python3-daemon
Requires: python3-sdnotify
%endif
#
%if 0%{?rhel} == 8
Requires: network-scripts
Requires: python3-netaddr
Requires: python36-oci-sdk
Requires: python3-daemon
Requires: python3-sdnotify
%endif
#
%if 0%{?rhel} == 7
Requires: python36-netaddr
Requires: python36-oci-sdk
Requires: python3-daemon
Requires: python3-sdnotify
%endif
#
%description
A package with useful scripts for querying/validating the state of Oracle Cloud Infrastructure instances running Oracle Linux and facilitating some common configuration tasks.

%package kvm
Summary: Utilitizes for managing virtualization in Oracle Cloud Infrastructure
Group: Development/Tools
Requires: %{name} = %{version}-%{release}
#
%if 0%{?rhel} == 9
Requires: python3-libvirt
%endif
#
%if 0%{?rhel} == 8
Requires: python3-libvirt
%endif
#
%if 0%{?rhel} == 7
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
#
%if 0%{?rhel} == 9
Requires: python3
Requires: python39-oci-cli
Requires: python3-pyyaml
%endif
#
%if 0%{?rhel} == 8
Requires: python3
Requires: python36-oci-cli
Requires: python3-pyyaml
%endif
#
%if 0%{?rhel} == 7
Requires: python36
Requires: python36-pyyaml
Requires: python36-oci-cli
%endif
#
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
%{__cp} -r README.md %{buildroot}/opt/oci-utils

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
%{python3_sitelib}/oci_utils/impl/__init__*
%{python3_sitelib}/oci_utils/impl/migrate
%{python3_sitelib}/oci_utils/migrate
%{_datadir}/man/man1/oci-image-migrate*1.gz
%config %{_sysconfdir}/oci-utils/oci-migrate-conf.yaml


%files oumtest
/opt/oci-utils/lib
/opt/oci-utils/tools
/opt/oci-utils/tests/data
/opt/oci-utils/README.md
/opt/oci-utils/requirements.txt
/opt/oci-utils/setup*
/opt/oci-utils/tests/test_mig*
/opt/oci-utils/tests/__init__*

%changelog
* Thu Sep 22 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.14.0-3
- LINUX-11440/LINUX-12246 iscsi does not fall back to scanning if authentication succeeds but get instance data fails
- added oci-attached-volumes, collects data on volumes, via OCI if priviliges in place, via scan otherwise.
- LINUX-12907 sudo oci-network-config --show missing spaces between values

* Mon Sep 5 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.14.0-2
- LINUX-12761/OLUEK-6199 ocid leaves lots of connections in CLOSE_WAIT state

* Thu Aug 11 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.14.0-1
- LINUX-12027: oci-image-migrate on ol7 unable to mount ol9 xfs filesystem

* Mon Jul 25 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.14.0-0
- support for ipv6:
- LINUX-9259 add ipv6 support in oci-metadata
- OLDIS-6914 IPv6 support for oci-utils

* Thu Jun 9 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.9-1
- renamed dashed python files to underscore python files
- extended instance principal test code with listing attached volunes, all volumes, attached volumes, available notification topics, vcns, subnets, vnics.

* Tue May 24 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.8-2
- modified fatal error on retrieving notify topic list to a warning

* Thu Apr 14 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.8-1
- fixed oci-public-ip all flag: removed

* Wed Mar 30 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.7-3
- spec file fixed for ol9 builds of oci-kvm and oci-migrate
- tests for instance distribution and version

* Wed Mar 09 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.7-2
- LINUX-11994 oci-utils for OL9
- adjust oci-kvm guest test
- show-all option for oci-iscsi-config
- LINUX-12111 oci-public-ip (oci-utils) does not show the reason why no public ip's are returned.
- LINUX-12119 oci-public-ip does not have the correct ordering in "primary on top"
- update oci-kvm

* Wed Feb 16 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.7-1
- LINUX-12109 Local iSCSI info not available" after running oci-iscsi-config sync
- LINUX-12114 oci-utils help info contains ref to python main module iso the command

* Thu Feb 10 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.6-12
- LINUX-12063 attach detach attach detach "is already detached" error

* Tue Feb 8 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.6-11
- fixed timing issue with ocid refresh

* Fri Feb 4 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.6-10
- LINUX-12038 oci-utils-0.12.6-9.el7 oci-iscsi-config has errors Error running fdisk

* Mon Jan 31 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.6-9
- LINUX--11928 oci-utils growfs should support more than xfs file systems; ext4 filesystem added.
- oci-growfs ported to python code.

* Fri Jan 14 2022 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.6-8
- LINUX-11876: centralise cache files
- refactor oci-iscsi-config-main attach and sync
- updated oci-iscsi-config manpage for the sync option
- added oci-instanceid, oci-compartmentid, oci-volume-data as non-documented utilities
- LINUX-11228: oci-iscsi-config sync does not function as it is documented

* Fri Dec 24 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.6-7
- kvm autotest update
- provisioning update
- kvm provisioning update

* Wed Dec 1 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.6-6
- LINUX-9217: add testcases for oci-notify
- LINUX-11400: verify the notification topic at configuration time.
- LINUX-11773: oci-notify uses a deprecated parameter message_type in publishing a message.

* Fri Nov 26 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.6-5
- LINUX-10151: oci-network-config show --details does not list secondary ip address; implemented in show-vnics
- LINUX-10139: table print headers need to match the column widths
- autotest update
- provisioning update

* Tue Oct 19 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.6-4
- Correction in oci-iscsi-config man page
- LINUX-9802 oci-iscsi-config --show does not show mount point nor file system data
- Fixed oci-iscsi-config table formatting
- Fixed oci-public-ip table formatting
- Added oci-instanceid and oci-compartmentid scripts

* Thu Oct 7 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.6-3
- OL8 kvm image build automation

* Wed Sep 29 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.6-2
- Removed message_type from publish message call.

* Tue Sep 28 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.6-1
- Back out ocid service enabled at install.

* Wed Sep 08 2021 guido tijskens <guido.tijskens@oracle.com> - 0.12.6-0
- release 0.12.6-0

* Tue Sep 07 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.5-10
- LINUX-11499: oci-metadata --value-only returning null

* Fri Aug 27 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.5.9
- LINUX-11457: public API oci_api missing get_object_storage_client

* Tue Aug 24 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.5-8
- LINUX-11441: add --yes flag to delete-network in oci-kvm
- LINUX-11442: oci-kvm create network fails with 'numerical result out of range when name > 14 characters
- LINUX-11443: oci-kvm create-pool on nfs fails with python3 string error

* Thu Aug 12 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.5-7
- LINUX-7304: KVM image script alignment

* Wed Aug 11 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.5-6
- LINUX-1742: oci-public-ip reports errors when python-oci-sdk is installed but not set up
- LINUX-9425: oci-iscsi-config attach -I fails on iqn's
- LINUX-9444: port oci-notify to python3; remove requirement for oci-cli
- LINUX-11295: ocid service fails to restart in E4 flex shapes on OL8 image
- LINUX-11322: oci-iscsi-config create and attach do not have a 'require chap credentials' option
- LINUX-11379: The oci-iscsi-config -a missing "command executed successfully' message

* Mon Aug 2 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.5-5
- LINUX-9229 remove Error in message "Error: Local iscsi info not available
- LINUX-9857 oci-network-config configure do not persist configuration
- LINUX-11293 oci-iscsi-config chap secrets function
- LINUX-11345 oci-iscsi-config show without sudo shows error

* Fri Jul 16 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.5-4
- enable ocid service install time
- fixed secondary address persistence and configuration issue

* Fri Jul 2 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.5-3
- LINUX-9680 move KVM image scripts to github
- LINUX-11255 output of oci-public-ip -g has a # at then end
- LINUX-11261 ocid does not enable vnics at reboot/ocid configures unconfigured vnics
- image build scripts

* Mon Jun 28 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.5-2
- OLUEK-5005 oci-metadata (oci-utils) value-only flag broken

* Wed Jun 23 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.5-1
- modified oci-iscsi-config output in compat mode
- corrected oci-iscsi-config behaviour on invalid compat syntax
- some small changes
- changed log and error messages

* Thu Jun 17 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.4-4
- LINUX-11136 compatibility: oci-network-config --(de)configure does not show results
- LINUX-11163 compatibility: oci-network-config differences in output
- LINUX-11164 compatibility: oci-iscsi-config differences in output
- LINUX-11166 oci-iscsi-config show --compartment does not show correct data
- LINUX-11165 oci-iscsi-config unhandled exceptions
- OLUEK-4954 oci-iscsi-config --show does not return values

* Fri Jun 4 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.4-3
- LINUX-11094 oci-network-config --add-private-ip error
- LINUX-11102 oci-network-config --add-secondary-addr should be able to assign a free IP automatically
- LINUX-11113 oci-network-config show messages when detaching vnic
- LINUX-11114 oci-iscsi-config change messages when no volumes found

* Tue Jun 1 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.4-2
- LINUX-11099 compatibility issue: oci-iscsi-config --destroy-volume has new prompt to confirm deletion (-y option)
- LINUX-11093 oci-network-config man pages contains incorrect command line format
- LINUX-11085 remove requirement for python3-requests package

* Wed May 12 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.4
- LINUX-10886 oci-network-config/oci-iscsi-config failures: __init__.py, line 58 in _oci_utils_exception_hook
- LINUX-10964 oci-network-inspector test fails
- LINUX-10214 convert README.md to md format

* Fri Apr 9 2021 Guido Tijskens <guido.tijskens@oracle.com> -- 0.12.2
- LINUX-8692  oci-image-cleanup: line 588: /dev/shm/oci-utils/image-cleanup.plan: Permission denied
- LINUX-10007 oci-metadata autotest fails on several locations
- LINUX-10048 oci-network-inspector autotest fails
- LINUX-10050 oci-iscsi-config autotest fails
- LINUX 10105 oci-iscsi-config attach -i <iqn...> fails
- LINUX-10121 oci-iscsi detach "multiple iqns" fails with 'NoneType' object is not subscriptable
- LINUX-10142 oci-network-config show-vnics --details inhibits output mode
- LINUX-10149 oci-network-config attach-vnic -I 100.110.5.99 fails
- LINUX-10316 oci-network-config attach-vnic --name <name> --subnet <subnetid> fails
- LINUX-10323 <>.get_compartment_id returns tenancy ocid iso compartment ocid
- LINUX-10345 OCIVNIC cannot handle empty/absent attachement data
- LINUX-10360 ocid service configures unconfigured vnics
- LINUX-10363 oci-network-config --create-vnic --private-ip <ipv4> fails
- LINUX-10373 oci-network-config -X <vnic..> fails (as does -I)
- LINUX-10382 oci-image-cleanup: add tests for source exist before running rsync
- LINUX-10426 oci-iscsi-config fails to attach/destroy volumes on r1 tenancy
- LINUX-10428 oci-metadata --get /vnics/privateip fail
- LINUX-10535 oci-iscsi-config -s shows all the unattached volumes that exist in the compartment, man page needs an update to.
- LINUX-10667 oci-iscsi-config sync --apply fails: str obj has not attr keys
- LINUX-10686 oci-network-config compatibility issue: --add-private-ip -e <ip> <ocid>

* Thu Dec 10 2020 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.12.1
- LINUX-9315: reduce use of sleep calls
- LINUX-9806: OCISession.get_vnic not optimised
- LINUX-9566: oci-network-config should display NIC index
- LINUX-9781: Should add parsable output
- LINUX-9740: oci_api module takes long time to load
- LINUX-9334: remove use of sleep in oci-network-config-main
- LINUX-9770: oci-network-config usage refactor
- LINUX-9815 : oci-public-ip do not implement --human-readable option
- LINUX-9812 : oci-public-ip should leverage new output mechanism


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

* Thu Jul 2 2020 Emmanuel Jannetti <emmanuel.jannetti@oracle.com> --0.11.1
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
