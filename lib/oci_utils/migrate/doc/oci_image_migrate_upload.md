# oci-utils.oci-image-migrate-upload

## Introduction

oci-image-migrate-upload uploads an on-premise image to an object storage
of the Oracle Cloud Infrastructure.

## Usage
```
   $ oci-image-migrate-upload --help
   usage: oci-image-migrate-upload-main.py -i INPUT_IMAGE 
                                           -b BUCKET_NAME
                                           [-o OUTPUT_NAME]
                                           [--verbose] 
                                           [--yes]
                                           [--help]

   Utility to upload on-premise legacy images to object storage of the Oracle
   Cloud Infrastructure.

   Arguments:
  -i INPUT_IMAGE, --image-name INPUT_IMAGE
                        The on-premise image name uploaded image.
  -b BUCKET_NAME, --bucket-name BUCKET_NAME
                        The name of the object storage.
  -o OUTPUT_NAME, --output-name OUTPUT_NAME
                        The name the image will be stored in the object
                        storage.
  --verbose, -v         Show verbose information.
   -y, --yes           The answer on Yes/No questions is supposed to be yes.
  --help                Display this help
```

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
