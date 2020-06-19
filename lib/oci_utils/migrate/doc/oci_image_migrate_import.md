# oci-utils.oci-image-migrate-import

## Introduction

oci-image-migrate-import imports an image from the object storage to the
custom images repository in teh Oracle Cloud Infrastructure.

## Usage

    # oci-image-migrate-import --help
    usage: oci-image-migrate-import.py -i IMAGENAME -b BUCKETNAME
                                       -c COMPARTMENTNAME 
                                       [-d DISPLAYNAME]
                                       [-l {PARAVIRTUALIZED,EMULATED,NATIVE}]
                                       [--verbose] [--yes] [--help]

    Utility to import a (verified and modified) on-premise legacy images which
    was uploaded to object storage in the custom images folderof the Oracle
    Cloud Infrastructure.

    Arguments:
    -i IMAGENAME, --image-name IMAGENAME
                        The name of the object representing the uploaded
                        image.
    -b BUCKETNAME, --bucket-name BUCKETNAME
                        The name of the object storage.
    -c COMPARTMENTNAME, --compartment-name COMPARTMENTNAME
                        The name of the destination compartment.
    -d DISPLAYNAME, --display-name DISPLAYNAME
                        Image name as it will show up in the custom images;
                        the default is the image name.
    -l {PARAVIRTUALIZED,EMULATED,NATIVE}, --launch-mode {PARAVIRTUALIZED
                        ,EMULATED,NATIVE}
                        The mode the instance created from the custom image
                        will be started; the default is PARAVIRTUALIZED.
    -v, --verbose       Show verbose information.
    -y, --yes           The answer on Yes/No questions is supposed to be yes.
    --help              Display this help

The environment variable _OCI_UTILS_DEBUG changes the logging level of
the python code.
 
## Installation

### Prerequisites

   1. The git package is installed.

   1. The oci cli package is installed and configured.

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
