# oci-utils.oci-image-migrate

## Introduction

oci-image-migrate prepares the image of an on-premise vm for being migrate to
 the Oracle Cloud Infrastructure. The code detects the image type, the 
 operating system as well as various configurations with respect to network, 
 partitions, file systems, mount setup
... 
 The code is flexible and open for addition 
 of new operating systems, new image type, new configurations.

## Usage


    # oci-image-migrate --help
    usage: oci-image-migrate [-i INPUTIMAGE] [--verbose] [--yes] [--help]

    Utility to support preparation of on-premise legacy images for importing in
    the Oracle Cloud Infrastructure.

    optional arguments:
      -i INPUTIMAGE, --input-mage INPUTIMAGE
                            The on-premise image for migration to OCI.
      -v, --verbose         Show verbose information.
      -y, --yes             The answer on Yes/No questions is supposed to be yes.
      --help                Display this help.

The environment variable _OCI_UTILS_DEBUG changes the logging level of
the python code.
 
## The image type

The image type specific code has

1. a dictionary **format_data** containing 1 key, the **magic number**
   and a value which contains the dictionary of mandatory and optional
   data. Mandatory are the **name**, the **module** name, the **class**
   name. The **prereq** key is also optional and its value is structure
   of image type prerequisites.

    format_data = {'01234567': {'name': 'sometype',
                                'module': 'sometype',
                                'clazz': 'TemplateTypeHead',
                                'prereq': {'MAX_IMG_SIZE_GB': 300.0}}}
                           
1. a class definition **TemplateTypeHead**,  which is a child of the 
**DeviceData** class, contains a structure defining the header of the image 
file, which has methods:
   1. **show_header** to display the header data;
   1. **image_size** to return a dictionary containig the physical and 
   logical size for the image file in GigaBytes;
   1. **image_supported** to test if the image is supported;
   1. **type_specific_prereq_test** to verify the image type specific 
   prerequisites;
   1. **image_data** which collects the data for this image type;

## The operating system dependent code

The code which is dependent of the operating system type, i.e. Oracle Linux 
type or Ubuntu Linux type distributions currently.

1. the tag **\_os_type_tag_csl_tag_type_os_** which is a list of operating 
system ID's as they are presented in the **os-release** file;
1. the method **install_cloud_init** which installs  the cloud_init and its 
dependent packages;
1. the method **update_network_config** to modify the network configuration 
as required by the migration documentation;


## The data structure

The **DeviceData** class creates, completes and uses a dictionary 
datastructure **image_info** for analysing the image:

    img_name   <image file name>

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
           Disk Flags
           Partition Table
           Partion List with detail

    partitions /dev/nbd<n>p<m>  start
                                size
                                id
                                bootable
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
                  ID
                  ....

    bootmnt  (boot partition, <current mountpoint of the boot partition>)

    rootmnt  (root partition, <current mountpoint of the root partition>)

    boot_type [BIOS|UEFI|NA]

    fstab  (list of relevant fstab line as lists)

    grubdata [ { cnt { menuentry : [ menuentry list] { search : [search list ] ... }       ]

    network { networkdevice { network data...}} {  { }} ....

    pseudomountlist [ list of mountpoints of pseudofs ]

    remountlist [ list of mountpoints used while chroot]

    ostype <ref to os dependent code>
    
    major_release MAJOR os release
    
    kernelversion <version of kernel booted by default>
    
    kernellist [ list of kernels defined in grub config file ]


## Installation

### Prerequisites

   1. The git package is installed.

   1. The developer channel is defined and enabled in the yum.repo.
   
   1. The kvm utils channel is defined and enabled in the yum.repo.

   1. The python setuptools package is at the latest release.


### The install

1. Pull the software from github:

       # git clone https://github.com/guidotijskens/oci-utils.git

1. Checkout the migrate branch:

       # git checkout migrate

1. Build the rpm:

       # cd oci-utils
       # python3 ./setup.py -c create-rpm

1. Install the rpm:

       # yum localinstall oci-utils/rpmbuild/RPMS/noarch/oci-utils-migrate

### Known issues

1. The cloud-init service, although enabled does not start at first boot in 
OCI. The issue is noticed on ubuntu18 server. This is probably related to 
the situation described in https://bugs.launchpad.net/bugs/1669675.
The workaround: 
   1. connect to the instance using vnc or serial console.
   1. delete the contents of /var/lib/cloud.
   1. eventually delete /var/log/cloud* files.
   1. explicitly start the cloud-init service
   1. reboot the instance

1. Entries in /etc/fstab as /dev/disk/by-id are not supported yet.
The workaround:
   1. update the /etc/fstab file so it refers to partitions via label, uuid,
   logical volume.
   
1 The instance created from a migrated image does not boot,  is  unable to find boot 
disk because initramfs does not include the correct kernel module to recognise the 
bootable partition. The issue is being worked on.  The workaround:                                                                       
                                                                                                                               
   1. rebuild initramfs before migration so it includes all modules and rebuilding  
   again after first boot with the necessary ones.        

### Debugging help

To verify the status of the migration preparation, it is possible to stop the process 
on predefined places without the attachment of a debugger. The wait is triggered by
defining environment variables. Currently the next are implemented:
1. _OCI_CHROOT
1. _OCI_PART
1. _OCI_LVM
1. _OCI_EXEC
1. _OCI_MOUNT
1. _OCI_NETWORK

Setting _OCI_PAUSE waits everywhere.

### Testing

Various image types are to be tested:
1. BIOS boot - UEFI boot
1. standard partitions
1. logical volumes
1. separate boot partition
1. fstab entries: UUID, /dev/mapper, /dev/disk/by-uuid, ...
1. network configurations:
   1. ifcfg
   1. network manager
   1. netplan
   1. systemd
   
