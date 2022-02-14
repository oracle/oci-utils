// Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
// Licensed under the Universal Permissive License v 1.0 as shown
// at http:/oss.oracle.com/licenses/upl.

output "instance_private_ip" {
    value = module.base_instance.instance_private_ip
}

//XXXXoutput "instance_public_ip" {
//XXXX    value = module.base_instance.instance_public_ip
//XXXX}

output "boot_volume_ocid" {
    value = module.base_instance.boot_volume_ocid
}

output "instance_ocid" {
    value = module.base_instance.instance_ocid
}