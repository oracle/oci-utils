// Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
// Licensed under the Universal Permissive License v 1.0 as shown
// at http:/oss.oracle.com/licenses/upl.

resource "null_resource" "oci_sdk_config" {
  depends_on = [module.base_instance]
  provisioner "file" {
    source = var.oci_private_key
    destination = "/tmp/oci_private_key.pem"
    connection {
      type = "ssh"
      user = var.remote_user
      agent = false
      host = module.base_instance.instance_XXXX_ip
      timeout = "15m"
      private_key = file(var.ssh_private_key)
    }
  }
  provisioner "remote-exec" {
    connection {
      type = "ssh"
      user = var.remote_user
      agent = false
      host = module.base_instance.instance_XXXX_ip
      timeout = "15m"
      private_key = file(var.ssh_private_key)
    }
    inline = [
       "/bin/sudo --preserve-env mkdir -p /root/.oci",
       "/bin/sudo --preserve-env cp /tmp/oci_private_key.pem /root/.oci/$(basename ${var.oci_private_key})",
       "/bin/sudo --preserve-env echo [DEFAULT] > /tmp/config",
       "/bin/sudo --preserve-env echo user=${var.user_ocid} >> /tmp/config",
       "/bin/sudo --preserve-env echo fingerprint=${var.fingerprint} >> /tmp/config",
       "/bin/sudo --preserve-env echo key_file=/root/.oci/$(basename ${var.oci_private_key}) >> /tmp/config",
       "/bin/sudo --preserve-env echo tenancy=${var.tenancy_ocid} >> /tmp/config",
       "/bin/sudo --preserve-env echo region=${var.region} >> /tmp/config",
       "/bin/sudo cp /tmp/config /root/.oci/config",
       "/bin/sudo chmod -R 600 /root/.oci/"
    ]
  }
}
