# Assistance for creating a basic instance in OCI.

## Prerequisites

- terraform software installed
- oci-sdk installed and configured for direct authentication (for now)


## Flow
- copy this tree/tar ball and expand to a working location
- chdir to **instance** directory
- install by executing `make install`, this will the template structure to a directory `~/create_instance` and the executable `create_instance` to `~/bin` 
- run `~/bin/create_instance` which completes the variable data, creates a directory `~/oci_instance/<instance name>` which contains the data for creating the instance, and creates create and destroy scripts.
