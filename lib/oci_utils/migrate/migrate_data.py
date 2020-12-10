# oci-utils
#
# Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module containing data.
"""
from datetime import datetime

#
# some numbers.
gigabyte = 2**30
rmmod_max_count = 4
qemu_max_count = 2
#
# the root for loopback mounts of partitions and logical volumes.
loopback_root = '/mnt'
#
# the root of the migrate related packages.
module_home = 'oci_utils.migrate.os_types'
#
# some flags.
verbose_flag = False
yes_flag = False
#
# time of execution.
current_time = datetime.now().strftime('%Y%m%d%H%M')
#
# last resort nameserver.
nameserver = '8.8.8.8'
#
# location of the configuration file
oci_migrate_conf_file = '/etc/oci-utils/oci-migrate-conf.yaml'
#
# will be set to False is the image is not fit to migrate to OCI for whatever
# reason.
migrate_preparation = True
#
# the reason why the image is not fit for migration to OCI.
migrate_non_upload_reason = ''
#
# it the migrate platform has logical volumes in use, a conflict is possible and
# the local volume groups can be renamed; the default is no.
local_volume_group_rename = False
local_volume_groups = list()
#
# the migrate util configuration is saved here for use while in chroot jail.
oci_image_migrate_config = dict()
#
# the os version information is saved here for use while in chroot jail.
os_version_id = 'X'
oracle_cloud_agent_location = None
#
# resolv.conf path
resolv_conf_path = ''
#
# full path for the (verbose) results.
result_filepath = ''
result_filename = ''
