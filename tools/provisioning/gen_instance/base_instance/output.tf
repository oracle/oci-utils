// Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
// Licensed under the Universal Permissive License v 1.0 as shown
// at http:/oss.oracle.com/licenses/upl.

output "instance_private_ip" {
    description = "Private IP of created instance."
    value = oci_core_instance.test_instance.*.private_ip[0]
}

//XXXXoutput "instance_public_ip" {
//XXXX    description = "Public IPs of created instance."
//XXXX    value       = oci_core_instance.test_instance.*.public_ip[0]
//XXXX}

output "boot_volume_ocid" {
    description = "OCID of the boot volume of the created instance."
    value = oci_core_instance.test_instance.*.boot_volume_id[0]
}

output "instance_ocid" {
    description = "OCID of the created instance."
    value = oci_core_instance.test_instance.*.id[0]
}

