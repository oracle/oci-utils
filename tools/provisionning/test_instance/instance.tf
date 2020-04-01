// Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
// Licensed under the Universal Permissive License v 1.0 as shown
// at http://oss.oracle.com/licenses/upl.
terraform {
  required_providers {
    oci = ">= 3.56.0"
  }
}
variable "tests_tools_dir" {}
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


variable "dns_search_domains" {}
variable "dns_server_ip" {}
variable "http_proxy_url" {}
variable "https_proxy_url" {}


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

data "template_file" "resolver_config" {
  template = file(join("/", [abspath(path.root), "userdata", "oci_resolver_config"]))
  vars = {
    dns_search_domains = var.dns_search_domains
    dns_server_ip      = var.dns_server_ip
  }
}
data "template_file" "tests_environement" {
  template = file(join("/", [abspath(path.root), "userdata", "oci-tests-env"]))
  vars = {
    http_proxy_url  = var.http_proxy_url
    https_proxy_url = var.https_proxy_url
  }
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
    source      = join("/", [var.oci_utils_rpms_dir, "/"])
    destination = "/tmp"

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
    content     = data.template_file.resolver_config.rendered
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
    content     = data.template_file.tests_environement.rendered
    destination = "/tmp/oci-tests-env.sh"

    connection {
      type        = "ssh"
      agent       = false
      user        = var.ssh_user
      host        = oci_core_instance.test_instance[0].private_ip
      timeout     = "15m"
      private_key = file(var.ssh_private_key_path)
    }
  }

  // do this right now as other command may need it
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
      "/bin/sudo /bin/cp --force /tmp/oci-tests-env.sh /etc/profile.d",
      "/bin/sudo /bin/cp --force /etc/resolv.conf /etc/resolv.conf.back",
      "/bin/sudo /bin/cp --force /tmp/resolv.conf /etc/resolv.conf",
    ]
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
      "/bin/sudo --login /usr/bin/yum install --quiet --assumeyes gcc",
      "/bin/sudo --login /usr/bin/yum install --quiet --assumeyes python3-devel",
      "/bin/sudo --login /usr/bin/yum install --quiet --assumeyes python3-pip",
      "/bin/sudo --login /usr/bin/yum install --quiet --assumeyes python-oci-sdk",
      "/bin/sudo --login /usr/bin/yum install --quiet --assumeyes libvirt",
      "/bin/sudo --login /usr/bin/yum install --quiet --assumeyes libvirt-python",
      "/bin/sudo --login /usr/bin/pip3 install --quiet --upgrade pip",
      "/bin/sudo --login /usr/bin/pip3 install setuptools --upgrade",
      "/bin/sudo --login /usr/bin/yum localinstall --assumeyes /tmp/oci-utils-*.rpm",
      "/bin/sudo --login /usr/bin/systemctl enable --now ocid",
      "/bin/sudo --login /usr/bin/systemctl enable --now libvirtd",
      "/bin/sudo --login /usr/bin/pip3 install wheel",
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
    // do not use --login as it make the shell to change dir
    inline = [
      "cd /opt/oci-utils/ && /bin/sudo --preserve-env /bin/python3 /opt/oci-utils/setup.py oci_tests --tests-base=/opt/oci-utils/tests/data"
    ]
  }


}
