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
    usage: oci-image-migrate [-i INPUTIMAGE] [-b BUCKETNAME] [-o OUTPUTIMAGE]
                             [--quiet] [--verbose] [--help]

    Utility to support preparation of on-premise legacy images for importing in
    the Oracle Cloud Infrastructure.

    optional arguments:
      -i INPUTIMAGE, --iimage INPUTIMAGE
                            The on-premise image for migration to OCI.
      -b BUCKETNAME, --bucket BUCKETNAME
                            The destination bucket in OCI to store the converted
                            image.
      -o OUTPUTIMAGE, --oimage OUTPUTIMAGE
                            The output image name.
      --quiet, -q           Suppress information messages
      --verbose, -v         Show verbose information.
      --help                Display this help`

The environment variable LOGLEVEL changes the logging level of the python 
code, if set to a valid value. The default log level is ERROR, the debug
flag changes it to INFO, the quiet flag to CRITICAL.
 
## The image type

The image type specific code has

1. a dictionary **format-data** containing 1 key, the **magic number** and a 
value which contains the dictionary of mandatory and optional data. Mandatory 
are the **name**, the **module** name, the **class** name. The **prereq** key 
is also optional and its value is structure of image type prerequisites.

    format_data = {'01234567': {'name': 'sometype',
                                'module': 'sometype',
                                'clazz': 'SomeTypeHead',
                                'prereq': {'MAX_IMG_SIZE_GB': 300.0}}}
                           
1. a class definition **SomeTypeHead**,  which is a child of the 
**DeviceData** class, contains a structure defining the header of the image 
file, which has methods:
   1. **show_header** to display the header data;
   1. **image_size** to return a dictionary containig the physical and 
   logical size for the image file in GigaBytes;
   1. **image_supported** to test if the image is suppored;
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
datastructure **img_info** for analysing the image:

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
           Partition Table

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

    botmnt  (boot partition, <current mountpoint of the boot partition>)

    rootmnt  (root partition, <current mountpoint of the root partition>)

    boot_type [BIOS|UEFI|NA]

    fstab  (list of relevant fstab line as lists)

    grubdata [ { cnt { menuentry : [ menuentry list] { search : [search list ] ... }       ]

    network { networkdevice { network data...}} {  { }} ....

    pseudomountlist [ list of mountpoints of pseudofs ]

    remountlist [ list of mountpoints used while chroot]

    ostype <ref to os dependent code>

    oci_config {the contents of the oci cli configuration file}

## Installation

### Prerequisites

   1. The git package is installed.

   1. The developer channel is defined and enabled in the yum.repo.

   1. The python setuptools package is at the latest release.

   1. The oci cli package is installed and configured.

### The install

1. Pull the software from github:

       # git clone https://github.com/guidotijskens/oci-utils.git

1. Checkout the migrate branch:

       # git checkout migrate

1. Build the rpm:

       # cd oci-utils
       # ./setup.py -c create-rpm

1. Install the rpm:

       # yum localinstall oci-utils/rpmbuild/RPMS/noarch/oci-utils-migrate
