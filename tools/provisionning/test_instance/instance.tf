// Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
// Licensed under the Universal Permissive License v 1.0 as shown
//
 at http://oss.oracle.com/licenses/upl.
terraform {
  required_providers {
    oci = ">= 3.56.0"
  }
}

variable "tenancy_ocid" {}
variable "user_ocid" {}
variable "fingerprint" {}
variable "private_key_path" {}
variable "region" {}
variable "compartment_id" {}
variable "availability_domain_id" {}
variable "subnet_id" {}
variable "instance_shape" {}
variable "instance_image_ocid" {}

variable "ssh_private_key_path" {}
variable "ssh_authorized_key_path" {}
variable "ssh_user" {}

variable "oci_utils_rpms_dir" {}


provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

variable "db_size" {
  default = "50" # size in GBs
}

data "oci_identity_availability_domains" "ad" {
  compartment_id = var.compartment_id
}




resource "oci_core_instance" "test_instance" {
  count               = "1"
  availability_domain = var.availability_domain_id
  compartment_id      = var.compartment_id
  display_name        = "OCIUtilsTestInstance"
  shape               = var.instance_shape

  create_vnic_details {
    subnet_id        = var.subnet_id
    display_name     = "Primaryvnic"
    assign_public_ip = false
  }

  source_details {
    source_type = "image"
    source_id   = var.instance_image_ocid
  }

  preserve_boot_volume = false
  metadata = {
    ssh_authorized_keys = file(var.ssh_authorized_key_path)
  }


  timeouts {
    create = "60m"
  }

}

output "instance_private_ip" {
  value = oci_core_instance.test_instance.*.private_ip
}


resource "null_resource" "deploy_test" {
  depends_on = [oci_core_instance.test_instance]

  provisioner "file" {
    source      = var.oci_utils_rpms_dir
    destination = "/tmp/"

    connection {
      type        = "ssh"
      agent       = false
      user        = var.ssh_user
      host        = oci_core_instance.test_instance[0].private_ip
      timeout     = "15m"
      private_key = file(var.ssh_private_key_path)
    }

  }

  provisioner "file" {
    source      = join("/", [abspath(path.root), "userdata", "oci_resolver_config"])
    destination = "/tmp/resolv.conf"

    connection {
      type        = "ssh"
      agent       = false
      user        = var.ssh_user
      host        = oci_core_instance.test_instance[0].private_ip
      timeout     = "15m"
      private_key = file(var.ssh_private_key_path)
    }

  }
  provisioner "file" {
    source      = join("/", [abspath(path.root), "userdata", "proxied_cmd"])
    destination = "/tmp/proxied_cmd"

    connection {
      type        = "ssh"
      agent       = false
      user        = var.ssh_user
      host        = oci_core_instance.test_instance[0].private_ip
      timeout     = "15m"
      private_key = file(var.ssh_private_key_path)
    }

  }

  provisioner "file" {
    source      = join("/", [abspath(path.root), "userdata", "proxied_oci_utils_cmd"])
    destination = "/tmp/proxied_oci_utils_cmd"

    connection {
      type        = "ssh"
      agent       = false
      user        = var.ssh_user
      host        = oci_core_instance.test_instance[0].private_ip
      timeout     = "15m"
      private_key = file(var.ssh_private_key_path)
    }

  }

  provisioner "remote-exec" {
    connection {
      type        = "ssh"
      agent       = false
      user        = var.ssh_user
      host        = oci_core_instance.test_instance[0].private_ip
      timeout     = "15m"
      private_key = file(var.ssh_private_key_path)
    }

    inline = [
      "/bin/sudo  /bin/cp -f /tmp/resolv.conf /etc/resolv.conf",
      "/bin/sh /tmp/proxied_cmd /usr/bin/yum  install --quiet --assumeyes gcc",
      "/bin/sh /tmp/proxied_cmd /usr/bin/yum  install --quiet --assumeyes python-devel",
      "/bin/sh /tmp/proxied_cmd /usr/bin/yum  install --quiet --assumeyes python-pip",
      "/bin/sh /tmp/proxied_cmd /usr/bin/yum  install --quiet --assumeyes python-oci-sdk",
      "/bin/sh /tmp/proxied_cmd /usr/bin/yum  install --quiet --assumeyes libvirt",
      "/bin/sh /tmp/proxied_cmd /usr/bin/yum  install --quiet --assumeyes libvirt-python",
      "/bin/sh /tmp/proxied_cmd /usr/bin/pip  install --quiet --upgrade pip",
      "/bin/sh /tmp/proxied_cmd /usr/bin/pip  install setuptools  --upgrade",
      "/bin/sh /tmp/proxied_cmd /usr/bin/yum  localinstall --assumeyes /tmp/oci-utils-*.rpm",
      "/bin/sh /tmp/proxied_cmd /usr/bin/systemctl enable --now ocid",
      "/bin/sh /tmp/proxied_cmd /usr/bin/systemctl enable --now libvirtd",
      "/bin/sh /tmp/proxied_cmd /usr/bin/pip  install wheel",
    ]
  }

}
resource "null_resource" "run_test" {
  depends_on = [null_resource.deploy_test]

  provisioner "remote-exec" {
    connection {
      type        = "ssh"
      agent       = false
      user        = var.ssh_user
      host        = oci_core_instance.test_instance[0].private_ip
      timeout     = "15m"
      private_key = file(var.ssh_private_key_path)
    }

    inline = [
      "/bin/sh /tmp/proxied_oci_utils_cmd /bin/python /opt/oci-utils/setup.py test"
    ]
  }


}
