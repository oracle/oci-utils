# Assistance for creating a kvm host instance and kvm guests in OCI.

## Prerequisites

- terraform software installed
- oci-sdk installed and configured for direct authentication (for now)


## Initialisation
- copy this tree or the tar ball (and expand) to a working directory.
- chdir to **kvm** directory

## Install host code
- As user with root privileges, run **create_kvmhost_user** which creates the user kvmhost and copies the necessary files in place.

    ```shell
    $ tar xvf /tmp/create_instance.0.10_May_02_2022.bz
    Makefile
    README.md
    host_instance/bin/create_kvm_host
    host_instance/bin/create_kvm_host.py
    guest_instance/bin/create_guest_vm
    guest_instance/bin/create_guest_vm.py
    host_instance/base_instance/data.tf
    host_instance/base_instance/main.tf
    host_instance/base_instance/output.tf
    host_instance/tf_scripts/api_key.tf
    host_instance/tf_scripts/data.tf
    host_instance/tf_scripts/main.tf
    host_instance/tf_scripts/version.tf
    host_instance/tf_scripts/output.tf
    host_instance/scripts/initial_config.sh
    guest_instance/templates/kickstart_bridge_template_ol7
    guest_instance/templates/kickstart_bridge_template_ol8
    guest_instance/templates/kickstart_direct_template_ol7
    guest_instance/templates/kickstart_direct_template_ol8
    create_kvmhost_user
    
    $ sudo ./create_kvmhost_user 3000 /tmp/config /tmp/oci_private_key.pem /tmp/create_instance.0.10_May_02_2022.bz
    03-May-2022 16:46:54 --- MSG --- Username is kvmhost
    03-May-2022 16:46:54 --- MSG --- UserID is 3000
    03-May-2022 16:46:54 --- MSG --- SDK config file is /tmp/config
    03-May-2022 16:46:54 --- MSG --- Key file /tmp/oci_private_key.pem
    03-May-2022 16:46:54 --- MSG --- TAR file /tmp/create_instance.0.10_May_02_2022.bz
    03-May-2022 16:46:54 --- MSG --- user home directory is /home/kvmhost
    03-May-2022 16:46:54 --- MSG --- .oci is /home/kvmhost/.oci
    03-May-2022 16:46:54 --- MSG --- config file is /home/kvmhost/.oci/config
    03-May-2022 16:46:54 --- MSG --- sdk key file is /home/kvmhost/.oci/oci_api_key.pem
    03-May-2022 16:46:55 --- MSG --- kvmhost created successfully.
    Changing password for user kvmhost.
    New password: 
    Retype new password: 
    passwd: all authentication tokens updated successfully.
    03-May-2022 16:47:06 --- MSG --- Password for kvmhost set successfully.
    03-May-2022 16:47:06 --- MSG --- Created bin successfully.
    03-May-2022 16:47:06 --- MSG --- Created base_instance successfully.
    03-May-2022 16:47:06 --- MSG --- Created work successfully.
    03-May-2022 16:47:06 --- MSG --- Created scripts successfully.
    03-May-2022 16:47:06 --- MSG --- Created tf_scripts successfully.
    03-May-2022 16:47:06 --- MSG --- /home/kvmhost/.oci created successfully.
    03-May-2022 16:47:06 --- MSG --- /home/kvmhost/.oci permission set to 700 successfully.
    03-May-2022 16:47:06 --- MSG --- Copied /tmp/config to /home/kvmhost/.oci/config successfully.
    03-May-2022 16:47:06 --- MSG --- /home/kvmhost/.oci/config permissions set to 600 successfully.
    03-May-2022 16:47:06 --- MSG --- Copied /tmp/oci_private_key.pem to /home/kvmhost/.oci/oci_api_key.pem successfully.
    03-May-2022 16:47:06 --- MSG --- 
    Makefile
    README.md
    host_instance/bin/create_kvm_host
    host_instance/bin/create_kvm_host.py
    guest_instance/bin/create_guest_vm
    guest_instance/bin/create_guest_vm.py
    host_instance/base_instance/data.tf
    host_instance/base_instance/main.tf
    host_instance/base_instance/output.tf
    host_instance/tf_scripts/api_key.tf
    host_instance/tf_scripts/data.tf
    host_instance/tf_scripts/main.tf
    host_instance/tf_scripts/version.tf
    host_instance/tf_scripts/output.tf
    host_instance/scripts/initial_config.sh
    guest_instance/templates/kickstart_bridge_template_ol7
    guest_instance/templates/kickstart_bridge_template_ol8
    guest_instance/templates/kickstart_direct_template_ol7
    guest_instance/templates/kickstart_direct_template_ol8
    create_kvmhost_user
    03-May-2022 16:47:06 --- MSG --- /tmp/create_instance.0.10_May_02_2022.bz successfully expanded
    03-May-2022 16:47:06 --- MSG --- Copied create_kvm_host.py in place successfully
    03-May-2022 16:47:06 --- MSG --- Copied create_kvm_host in place successfully
    03-May-2022 16:47:06 --- MSG --- Copied initial_config.sh in place successfully
    03-May-2022 16:47:06 --- MSG --- Copied data.tf in place successfully
    03-May-2022 16:47:06 --- MSG --- Copied main.tf in place successfully
    03-May-2022 16:47:06 --- MSG --- Copied output.tf in place successfully
    03-May-2022 16:47:06 --- MSG --- Copied api_key.tf in place successfully
    03-May-2022 16:47:06 --- MSG --- Copied data.tf in place successfully
    03-May-2022 16:47:07 --- MSG --- Copied main.tf in place successfully
    03-May-2022 16:47:07 --- MSG --- Copied output.tf in place successfully
    03-May-2022 16:47:07 --- MSG --- Copied version.tf in place successfully
    03-May-2022 16:47:07 --- MSG --- Copied Makefile in place successfully
    03-May-2022 16:47:07 --- MSG --- Copied README.md in place successfully
    03-May-2022 16:47:07 --- MSG --- Completed successfully
    ```
  
- install by executing `make install`, this will the template structure to a directory `~/create_instance` and the executable `create_instance` to `~/bin` 
- run `~/bin/create_instance` which completes the variable data, creates a directory `~/oci_instance/<instance name>` which contains the data for creating the instance, and creates create and destroy scripts.

## Install guest code