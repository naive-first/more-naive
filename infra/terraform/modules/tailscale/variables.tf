variable "host" { type = string }
variable "user" {
  type = string
  validation {
    condition     = can(regex("^[a-z_][a-z0-9_-]*$", var.user))
    error_message = "An existing SSH OS user is required."
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
    error_message = "The actual OS hostname is required."
  }
}
variable "node_directory" { type = string }
