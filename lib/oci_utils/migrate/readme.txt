#
# Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

#
# definition of supported image formats:
# dictionary of dictionaries,
#  main key is the magic number,
#    the format dictinary contains at least the name,
#                                           the module name (without the .py extension)
#                                           the class to be used
                                            the class dependent prerequisites

supported_formats = {'514649fb': {'name': 'qcow2',
                                  'mod': 'qcow2',
                                  'clazz': 'Qcow2Head',
                                  'prereq': {'MAX_IMG_SIZE' : 300.0,}},
                     '4b444d56': {'name': 'vmdk',
                                  'mod': 'vmdk',
                                  'clazz': 'VmdkHead',
                                  'prereq': {'MAX_IMG_SIZE' : 300.0,
                                            'vmdk_supported_types' :['monolithicSparse', 'streamOptimized']}}}

#
# the data collection:
 device_data  img_name   <image file name>

              img_type   [VMDK | qcow2]

              img_header <contents is type dependent>

              img_size  physical
                        logical

              mbr    bin
                     hex
                     valid (bool)
                     partition_table [ {boot, type} ...]

              parted Model
                     Disk
                     Partition Table
                     Partion List with detail

              partitions /dev/nbd<n>p<m>  start
                                          size
                                          id
                                          bootable
                                          ID_FS_LABEL
                                          ID_FS_LABEL_ENC
                                          ID_FS_TYPE
                                          ID_FS_USAGE
                                          ID_FS_UUID
                                          ID_FS_UUID_ENC
                                          ID_FS_VERSION
                                          ID_PART_ENTRY_DISK
                                          ID_PART_ENTRY_NUMBER
                                          ID_PART_ENTRY_OFFSET
                                          ID_PART_ENTRY_SCHEME
                                          ID_PART_ENTRY_SIZE
                                          ID_PART_ENTRY_TYPE
                                          mountpoint
                                          usage [na| standard| boot| root]

                         /dev/nbd<n>p<m>  ....

                         /dev/mapper/<..> ...
                          ....
              volume_groups volume_group [ (logical volume, lv mapper), (logical volume, lv mapper),...]
                            ...

              osinformation NAME
                            VERSION
                            ....
                            ....

              bootmnt  (boot partition, <current mountpoint of the boot partition>)

              rootmnt  (root partition, <current mountpoint of the root partition>)

              boot_type [BIOS|UEFI|NA]

              fstab  (list of relevant fstab line as lists)

              grubdata [ { cnt { menuentry : [ menuentry list] { search : [search list ] ... }       ]

              pseudomountlist [ list of mountpoints of pseudofs ]

              remountlist [ list of mounts root and swap excluded ]

              ostype <ref to os dependent code>

              major_release <MAJOR os release>

              kernelversion <version of kernel booted by default>

              kernellist [ list of kernels defined in grub config file ]
