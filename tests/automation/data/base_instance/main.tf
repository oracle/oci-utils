// Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
// Licensed under the Universal Permissive License v 1.0 as shown
// at http:/oss.oracle.com/licenses/upl.

variable "os_user" {
  description = "os user."
  type = string
}

variable "os_user_home" {
  description = "operator home directory"
  type = string
}

variable "server_ip" {
  description = "this server ipv4 address"
  type = string
}

variable "tenancy_ocid" {
  description = "tencancy identification."
  type = string
}

variable "user_ocid" {
  description = "user identification."
  type = string
}

variable "oci_private_key" {
  description = "path to use private key for OCI."
  type = string
}

variable "fingerprint" {
  description = "OCI key fingerprint."
  type = string
}

variable "region" {
  description = "oci region name."
  type = string
}

variable "availability_domain" {
  description = "availability domain name."
  type = string
}

variable "compartment_ocid" {
  description = "compartment identification."
  type = string
}

variable "shape" {
  description = "shape selection."
  type = string
}

//FLEXvariable "instance_flex_memory_in_gbs" {
//FLEX description = "instance memorry size in GB."
//FLEX  type = number
//FLEX}

//FLEXvariable "instance_flex_ocpus" {
//FLEX  description = "amount of instance ocpus."
//FLEX  type = number
//FLEX}

variable "source_ocid" {
  description = "source identification."
  type = string
}

variable "source_type" {
  description = "source type identification."
  type = string
}

variable "instance_display_name" {
  description = "instance display name."
  type = string
}

variable "assign_public_ip" {
  description = "assign a public ip."
  type = bool
}

variable "vnic_display_name" {
  description = "vnic display name."
  type = string
}

variable "subnet_ocid" {
  description = "subnet identification."
  type = string
}

variable "ssh_public_key" {
  description = "user authorized keys path."
  type = string
}

variable "remote_user" {
  description = "user to connect to remote with sudo privileges."
  type = string
}

variable "ssh_private_key" {
  description = "local user private key path."
  type = string
}

variable "auth" {
  description = "authentication method."
  type = string
}

variable "log_file_path" {
  description = "path to logfile"
  type = string
}

variable "script_path" {
  description = "path to bash script direcory"
  type = string
}

provider "oci" {
  tenancy_ocid = var.tenancy_ocid
  user_ocid = var.user_ocid
  private_key_path = var.oci_private_key
  fingerprint = var.fingerprint
  region = var.region
  // auth = var.auth
}

resource "oci_core_instance" "test_instance" {
  count               = "1"
  availability_domain = var.availability_domain
  compartment_id      = var.compartment_ocid
  display_name        = var.instance_display_name
  shape               = var.shape
//FLEX  shape_config {
//FLEX    memory_in_gbs = var.instance_flex_memory_in_gbs
//FLEX    ocpus         = var.instance_flex_ocpus
//FLEX  }
  create_vnic_details {
    subnet_id        = var.subnet_ocid
    display_name     = var.vnic_display_name
    assign_public_ip = var.assign_public_ip
  }

  source_details {
    source_type = var.source_type
    source_id   = var.source_ocid
  }

  preserve_boot_volume = false

  metadata = {
    ssh_authorized_keys = file(var.ssh_public_key)
  }

  timeouts {
    create = "60m"
  }

}

// install repo.
resource "null_resource" "install_repo" {
  depends_on = [oci_core_instance.test_instance]
  provisioner "file" {
    source      = "/var/www/html/channel_rpms/${var.os_user}/"
    destination = "/tmp/"
    connection {
      type = "ssh"
      agent = false
      user = var.remote_user
      host = oci_core_instance.test_instance.*.PUBIP_ip[0]
      timeout = "15m"
      private_key = file(var.ssh_private_key)
    }
  }

  provisioner "remote-exec" {
    connection {
      type = "ssh"
      agent = false
      user = var.remote_user
      host = oci_core_instance.test_instance.*.PUBIP_ip[0]
      timeout = "15m"
      private_key = file(var.ssh_private_key)
    }
    script = "${var.script_path}/install_oci_utils_automation.sh"
  }

  provisioner "remote-exec" {
    connection {
      type = "ssh"
      agent = false
      user = var.remote_user
      host = oci_core_instance.test_instance.*.PUBIP_ip[0]
      timeout = "15m"
      private_key = file(var.ssh_private_key)
    }
    inline = [
      "/bin/sudo --preserve-env mkdir -p /logs",
      "/bin/sudo --preserve-env chmod 777 /logs"
      ]
  }
}

