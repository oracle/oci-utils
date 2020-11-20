===================================================
oci-utils-automation - For Oracle Internal Use Only
===================================================
The oci-utils-automation rpms define the repofiles for
accessing rpms to test and creates the repository
directories if they do not exist yet.

usage:
- pull the software tree
- change directory to the sotware root
- run 'make publisch'
- run 'make clean'

copy rpms to the repositories:
 make copyrpm RPM=<path to rpm> DISTRO=<valid distro, OL7|OL8>
