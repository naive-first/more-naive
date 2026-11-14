terraform {
  required_version = "= 1.17.2"
}

locals {
  version = "v1.35.10+k3s1"
  config = join("\n", concat([
    "node-name: ${jsonencode(var.node)}",
    "write-kubeconfig-mode: \"0600\"",
    "token-file: /etc/rancher/k3s/more-naive-token",
  ], var.role == "server" ? ["disable:", "  - traefik", "  - servicelb"] : ["server: ${jsonencode(var.server_url)}"], [""]))
}

resource "terraform_data" "installation" {
  input = { host = var.host, node = var.node, role = var.role, version = local.version }
  # Ephemeral tokens cannot be compared through state. Recheck the existing
  # installation on each apply; replacement has no node uninstall action.
  triggers_replace = [timestamp()]

  connection {
    type        = "ssh"
    host        = var.host
    port        = var.ssh_port
    user        = var.user
    host_key    = var.host_key
    private_key = file(pathexpand(var.private_key_file))
    agent       = false
    timeout     = "30s"
  }

  provisioner "remote-exec" {
    inline = ["umask 077; test ! -e .more-naive-k3s-${self.id} && mkdir -m 700 .more-naive-k3s-${self.id}"]
  }
  provisioner "file" {
    content     = var.token
    destination = ".more-naive-k3s-${self.id}/token"
  }
  provisioner "file" {
    content = templatefile("${path.module}/install.sh.tftpl", {
      node = var.node, role = var.role, version = local.version, config_base64 = base64encode(local.config)
    })
    destination = ".more-naive-k3s-${self.id}/install.sh"
  }
  provisioner "remote-exec" {
    inline = ["sudo -n sh \"$HOME/.more-naive-k3s-${self.id}/install.sh\" \"$HOME/.more-naive-k3s-${self.id}\""]
  }
}
