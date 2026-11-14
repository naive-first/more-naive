variable "host" { type = string }
variable "ssh_port" {
  type    = number
  default = 22
}
variable "user" {
  type = string
  validation {
    condition     = can(regex("^[a-z_][a-z0-9_-]*$", var.user))
    error_message = "An explicit SSH OS user is required."
  }
}
variable "host_key" {
  type = string
  validation {
    condition     = can(regex("^(ssh-|ecdsa-|sk-)", var.host_key))
    error_message = "A trusted SSH host public key is required."
  }
}
variable "private_key_file" {
  type      = string
  ephemeral = true
}
variable "node" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{0,62}$", var.node))
    error_message = "An expected node hostname is required."
  }
}
variable "role" {
  type = string
  validation {
    condition     = contains(["server", "agent"], var.role)
    error_message = "role must be server or agent."
  }
}
variable "server_url" {
  type    = string
  default = ""
  validation {
    condition     = var.role == "server" || can(regex("^https://[A-Za-z0-9.:\\[\\]-]+:6443$", var.server_url))
    error_message = "agent requires https://<private-server>:6443."
  }
}
variable "token" {
  type      = string
  sensitive = true
  ephemeral = true
  validation {
    condition     = length(trimspace(var.token)) > 0 && !can(regex("[\\r\\n\\x00]", var.token))
    error_message = "A nonempty single-line join token is required."
  }
}
