terraform {
  required_version = "= 1.17.2"
}

resource "terraform_data" "installation" {
  input = { host = var.host, node = var.node }
  triggers_replace = [
    var.host, var.node, var.user,
    filesha256("${var.node_directory}/register.sh"),
    filesha256("${var.node_directory}/more-naive-tailscaled.service"),
  ]

  connection {
    type        = "ssh"
    host        = var.host
    user        = var.user
    host_key    = var.host_key
    private_key = file(pathexpand(var.private_key_file))
    agent       = false
    timeout     = "30s"
  }

  provisioner "remote-exec" {
    inline = ["umask 077; test ! -e .more-naive-tailscale-${self.id} && mkdir -m 700 .more-naive-tailscale-${self.id}"]
  }
  provisioner "file" {
    source      = "${var.node_directory}/register.sh"
    destination = ".more-naive-tailscale-${self.id}/register.sh"
  }
  provisioner "file" {
    source      = "${var.node_directory}/more-naive-tailscaled.service"
    destination = ".more-naive-tailscale-${self.id}/more-naive-tailscaled.service"
  }
  provisioner "remote-exec" {
    inline = [<<-SH
      directory="$HOME/.more-naive-tailscale-${self.id}"
      trap 'rm -f "$directory/register.sh" "$directory/more-naive-tailscaled.service"; rmdir "$directory"' EXIT
      sudo -n env MORE_NAIVE_ENV=prod TAILSCALE_EXPECTED_HOST=${jsonencode(var.node)} SSH_USER=${jsonencode(var.user)} bash "$directory/register.sh" --apply --install-only
    SH
    ]
  }
}
