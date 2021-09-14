# Using build_image

## Introduction

build_image assists in building KVM images based on Linux images.

## Prerequisites

The user running the build needs to have direct authenticaton configured. (Instance principal authentication is on the enthancement list.) The build_image uses only private ips. (Public ip is on the enhancement list.)

## Installation

The code resides in github. Install by:
```shell
$ git clone <git link to be completed> ~
```
This creates a directory tree:
```shell
 build_image
    ├── bin
    │   ├── configure_image.py
    │   └── install_packer.py
    ├── Makefile_xxx
    ├── scripts
    │   ├── custom_firstboot.sh
    │   └── custom_post_install_task.sh
    └── templates
         ├── al-kvm-image-template.json
         └── ol-kvm-image-template.json

```

* **Makefile**: make commands.
* **ol-kvm-image-template.json**: packer template file.
* **al-kvm-image-template.json**: packer template file.
* **custom_post_install_task.sh**: bash script run during image creation.  
* **custom_firstboot.sh**: bash script run during image creation. 
* **install_packer.py**: installs the latest version of **packer** in **/usr/local/bin**
* **configure_image.py**: collects all the data required for building the image.

## Usage

Go to the **build_image** directory.
```shell
$ make
help info:
 make help
 make show_version
 make install
 make install_packer
 make configure PROFILE=<profile> CONFIG=<config> DATADIR=<data directory> VARFILENAME=<packer variable file name> TYPE=[OL|AL]
          only TYPE=[OL|AL] is mandatory
 make configure TYPE=[OL|AL]
 make show_vars
 make build_image VARFILENAME=<packer variable file name> TYPE=[OL|AL] 
 make all TYPE=[OL|AL]
```

The **Makefile** contains all what is needed to build an Oracle Linux based KVM image. Although all commands can be run separately, a single or a two-step use is easy:
```shell
$ make configure
$ make build_image 
```
The built image is place in the **custom images** repository. The image name contains the date of creation.

