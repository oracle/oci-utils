# Assistance for creating a basic instance in OCI.

## Prerequisites

- terraform software installed
- oci-sdk installed and configured for direct authentication (for now)

## Command line
```buildoutcfg
$ create_instance --help
usage: create_instance.py [-h] [-n DISPLAY_NAME] [-p PROFILE] [-c CONFIGFILE]
                          [-d DATADIR] [-f VARFILENAME]

Configure oci utils auto test.

Arguments:
  -h, --help            show this help message and exit
  -n DISPLAY_NAME, --name DISPLAY_NAME
                        The display name of the instance to create. There is
                        no default, if not provided, the script asks for it.
  -p PROFILE, --profile PROFILE
                        The profile in the cli/sdk config file, default is
                        DEFAULT.
  -c CONFIGFILE, --config CONFIGFILE
                        The cli/sdk config file, default is ~/.oci/config.
  -d DATADIR, --data-directory DATADIR
                        Root directory with data for auto test run, default is
                        ~/<display_name>/data.
  -f VARFILENAME, --var-file VARFILENAME
                        filename to store the variables; the extension
                        .tfvars.json is added automatically.

```
## Flow
- copy this tree/tar ball and expand to a working location
- chdir to **gen_instance** directory
- `make` will show some help information
- install by executing `make install`, this will the copy template structure to a directory `~/create_instance` and the python code  `create_instance.py` and the bash wrapper `create_instance` to `~/bin` 
- run `~/bin/create_instance` which completes the variable data, creates a directory `~/oci_instance/<instance name>` which contains the data for creating the instance, and creates create and destroy scripts.
- the code assumes the presence of **${HOME}/.ssh/id_rsa** and **${HOME}/.ssh/id_rsa.pub**.