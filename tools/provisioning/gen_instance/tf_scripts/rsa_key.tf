// Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
// Licensed under the Universal Permissive License v 1.0 as shown
// at http:/oss.oracle.com/licenses/upl.

resource "null_resource" "oci_private_key" {
  depends_on = [module.base_instance]
  provisioner "file" {
    source = var.ssh_private_key
    destination = "/tmp/id_rsa"
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
       "/bin/sudo --preserve-env mkdir -p /root/.ssh",
       "/bin/sudo --preserve-env cp /tmp/id_rsa /root/.ssh/id_rsa",
       "/bin/sudo chmod -R 600 /root/.ssh/",
       "/bin/sudo chmod 700 /root/.ssh",
       "/bin/sudo --preserve-env mkdir -p /home/${var.remote_user}/.ssh",
       "/bin/sudo --preserve-env cp /tmp/id_rsa /home/${var.remote_user}/.ssh/id_rsa",
       "/bin/sudo --preserve-env chown -R ${var.remote_user}:${var.remote_user} /home/${var.remote_user}/.ssh",
       "/bin/sudo chmod -R 600 /home/${var.remote_user}/.ssh/",
       "/bin/sudo chmod 700 /home/${var.remote_user}/.ssh"
    ]
  }
}
