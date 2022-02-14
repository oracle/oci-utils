# Using build_image

## Introduction

build_image assists in building KVM images based on Linux images.

## Prerequisites

1. The user running the build needs to have direct authenticaton configured. (Instance principal authentication is on the enhancement list.) 
2. The build_image uses only private ips. (Public ip is on the enhancement list.)

## Installation

The code resides in github. 
1. Create a user to be used for the build of the KVM images. This user should have direct authentication via an oci-sdk configuration file set up. Also the user needs to have administration privileges, i.e. being a member of the wheel group. The passwordless sudo is very useful.
2. Connect as this user and create a work-directory. 
3. 2 options are available for installation:
    1. Clone the complete git repo and eventually check out a branch:
    ```shell
    $ git clone <git link to be completed> 
    ```
    2. Pull and expand the tar file **imagebuild.tar**
4. This creates a directory tree in this subdirectory or further down in the git clone **tools** directory:
    ```shell
     build_image
        ├── bin
        │   ├── configure_image.py
        │   └── install_packer.py
        │   └── upload_image.py
        │   └── create_imagebuild
        ├── Makefile
        ├── README.md
        ├── scripts
        │   ├── custom_firstboot.sh
        │   ├── custom_install.sh
        │   └── custom_post_install_task.sh
        └── templates
             ├── al-kvm-image-template.json
             └── ol-kvm-image-template.json
    
    ```
5. The script **create_imagebuild** can do the most of the above:
   1. Copy the tar file **imagebuild.tar** to a working directory.
   2. Copy the **sdk config** and **PEM RSA private key** files to the working directory.
   3. Run **create_imagebuild** as root
   ```shell
   # ./imagebuild/build_image/bin/create_imagebuild 
   23-Sep-2021 13:42:00 --- ERR --- username, userid, config, key file and/or tar file missing

   Usage:

   ./imagebuild/build_image/bin/create_imagebuild <userid> <sdk config> <key file> <tar file>

   <userid>     : the userid for the user.
   <sdk config> : the sdk config file.
   <key file>   : the sdk key file.
   <tar file>   : the tar file with the tool.

   Creates a user with name imagebuild and userid <userid>
   with groupid 1000 and in group wheel with home
   directory /home/imagebuild; configures the oci-sdk for direct authentication.
   ```
   Execution:
   ```shell
   # ./create_imagebuild 2000 /tmp/config /tmp/oci_api_key.pem /tmp/imagebuild.tar
   23-Sep-2021 14:12:30 --- MSG --- Username is imagebuild
   23-Sep-2021 14:12:30 --- MSG --- UserID is 2000
   23-Sep-2021 14:12:30 --- MSG --- SDK config file is /tmp/config
   23-Sep-2021 14:12:30 --- MSG --- Key file /tmp/oci_api_key.pem
   23-Sep-2021 14:12:30 --- MSG --- TAR file /tmp/imagebuild.tar
   23-Sep-2021 14:12:30 --- MSG --- user home directory is /home/imagebuild
   23-Sep-2021 14:12:30 --- MSG --- .oci is /home/imagebuild/.oci
   23-Sep-2021 14:12:30 --- MSG --- config file is /home/imagebuild/.oci/config
   23-Sep-2021 14:12:30 --- MSG --- sdk key file is /home/imagebuild/.oci/oci_api_key.pem
   23-Sep-2021 14:12:31 --- MSG --- imagebuild created successfully.
   Changing password for user imagebuild.
   New password: 
   Retype new password: 
   passwd: all authentication tokens updated successfully.
   23-Sep-2021 14:12:42 --- MSG --- Password for imagebuild set successfully.
   23-Sep-2021 14:12:42 --- MSG --- Created bin successfully.
   23-Sep-2021 14:12:42 --- MSG --- Created tests successfully.
   23-Sep-2021 14:12:42 --- MSG --- Created work scripts templates successfully.
   23-Sep-2021 14:12:42 --- MSG --- /home/imagebuild/.oci created successfully.
   23-Sep-2021 14:12:42 --- MSG --- /home/imagebuild/.oci permission set to 700 successfully.
   23-Sep-2021 14:12:42 --- MSG --- Copied /tmp/config to /home/imagebuild/.oci/config successfully.
   23-Sep-2021 14:12:42 --- MSG --- /home/imagebuild/.oci/config permissions set to 600 successfully.
   23-Sep-2021 14:12:42 --- MSG --- 
   23-Sep-2021 14:12:42 --- MSG --- 
   ./bin/
   ./bin/configure_image.py
   ./bin/install_packer.py
   ./bin/upload_image.py
   ./bin/create_imagebuild
   ./Makefile
   ./README.md
   ./scripts/
   ./scripts/custom_firstboot.sh
   ./scripts/custom_post_install_task.sh
   ./scripts/custom_install.sh
   ./templates/
   ./templates/al-kvm-image-template.json
   ./templates/ol-kvm-image-template.json
   23-Sep-2021 14:12:42 --- MSG --- /tmp/imagebuild.tar successfully expanded
   ```
7. To install this package, run from the working directory as the user which is going to do the image build (**imagebuild** if the script is used) :
    ```
    $ make install
    ```
8. The files copied and/or created:
   * **Makefile**: make commands.
   * **README.md**: this readme file.
   * **ol-kvm-image-template.json**: packer template file.
   * **al-kvm-image-template.json**: packer template file.
   * **custom_post_install_task.sh**: bash script run during image creation.
   * **custom_install.sh** bash script installing additional packages
   * **custom_firstboot.sh**: bash script run during image creation. 
   * **install_packer.py**: installs the latest version of **packer** in **/usr/local/bin**
   * **configure_image.py**: collects all the data required for building the image.
   * **upload_image.py**: uploads an image to an object storage.
   * **create_imagebuild**: creates the imagebuild user.

## Usage

Go to the **$HOME** directory.
```shell
$ make
help info:
 make help
 make show_version
 make install
 make install_packer
 make configure PROFILE=<profile> CONFIG=<config> DATADIR=<data directory> VARFILENAME=<packer variable file name> TYPE=[OL|AL] RELEASE=[7|8]
          The paramaters TYPE=[$(OLTYPE)|$(ALTYPE)] and RELEASE=[7|8] are mandatory
 make configure TYPE=[OL|AL]
 make show_vars
 make build_image VARFILENAME=<packer variable file name> TYPE=[OL|AL] 
 make all TYPE=[OL|AL]
```

The **Makefile** contains all what is necessary to build an Oracle Linux based KVM image. For example, to create an OL7 KVM image run:
```shell
$ make configure TYPE=OL RELEASE=7
$ make buildimage TYPE=OL RELEASE=7
```
or in one go:
```shell
$ make all TYPE=OL RELEASE=7
```
* **make configure** installs the latest version of **packer** and generates the json parameter file for the packer scripts.
* **make buildimage** creates the actual image; running this separately is useful if one or a few parameter(s) in the json paramter file are changed manually.
* When specifying the **VARFILENAME** for the **buildimage** option, the extension **.tfvar.json** is added implicitly.
* The built image is placed in the **custom images** repository. The image name contains the date of creation.

