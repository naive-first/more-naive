terraform {
  required_version = "= 1.17.2"
}
locals {
  relay_address = "172.30.104.10"
  relay_port    = 18080
}
resource "terraform_data" "proxy" {
  input = { host = var.host, node = var.node, gateway_host = var.gateway_host, relay_address = local.relay_address, relay_port = local.relay_port }
  triggers_replace = [
    var.host, var.node, var.user, var.gateway_host, local.relay_address, local.relay_port,
    filesha256("${var.proxy_directory}/bootstrap.sh"),
    filesha256("${var.proxy_directory}/more-naive-gateway-relay.service.tftpl"),
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
    inline = ["umask 077; test ! -e .more-naive-proxy-${self.id} && mkdir -m 700 .more-naive-proxy-${self.id}"]
  }
  provisioner "file" {
    source      = "${var.proxy_directory}/bootstrap.sh"
    destination = ".more-naive-proxy-${self.id}/bootstrap.sh"
  }
  provisioner "file" {
    content     = templatefile("${var.proxy_directory}/more-naive-gateway-relay.service.tftpl", { address = local.relay_address, port = local.relay_port })
    destination = ".more-naive-proxy-${self.id}/more-naive-gateway-relay.service"
  }
  provisioner "remote-exec" {
    inline = [<<-SH
      directory="$HOME/.more-naive-proxy-${self.id}"
      trap 'rm -f "$directory/bootstrap.sh" "$directory/more-naive-gateway-relay.service"; rmdir "$directory"' EXIT
      sudo -n env MORE_NAIVE_ENV=prod PROXY_EXPECTED_HOST=${jsonencode(var.node)} GATEWAY_HOST=${jsonencode(var.gateway_host)} RELAY_ADDRESS=${local.relay_address} RELAY_PORT=${local.relay_port} bash "$directory/bootstrap.sh" --apply
    SH
    ]
  }
}
