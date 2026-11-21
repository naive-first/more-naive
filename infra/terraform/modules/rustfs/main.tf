terraform {
  required_version = "= 1.17.2"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "4.7.0"
    }
  }
}

provider "docker" {}

variable "name" {
  type    = string
  default = "more-naive-rustfs"
}

variable "data_dir" {
  type = string
  validation {
    condition     = startswith(var.data_dir, "/") && !strcontains(var.data_dir, ".terragrunt-cache")
    error_message = "data_dir must be an absolute persistent path outside the Terragrunt cache."
  }
}

variable "api_port" {
  type    = number
  default = 9000
  validation {
    condition     = var.api_port >= 1024 && var.api_port < 65535
    error_message = "api_port must leave room for the adjacent Console port."
  }
}

variable "admin_access_key" {
  type      = string
  sensitive = true
  validation {
    condition     = length(var.admin_access_key) >= 8 && var.admin_access_key != "rustfsadmin"
    error_message = "A non-default administrator access key of at least 8 characters is required."
  }
}

variable "admin_secret_key" {
  type      = string
  sensitive = true
  validation {
    condition     = length(var.admin_secret_key) >= 16 && var.admin_secret_key != "rustfsadmin"
    error_message = "A non-default administrator secret of at least 16 characters is required."
  }
}

resource "docker_image" "rustfs" {
  name         = "rustfs/rustfs:1.0.5@sha256:b81d16a90ee25bd9511280127ca1471788c6e874cf0f0da759645f46b2dc1d74"
  keep_locally = true
}

resource "docker_container" "rustfs" {
  name    = var.name
  image   = docker_image.rustfs.image_id
  command = ["/data"]
  restart = "unless-stopped"
  env = [
    "RUSTFS_ACCESS_KEY=${var.admin_access_key}",
    "RUSTFS_SECRET_KEY=${var.admin_secret_key}",
    "RUSTFS_CONSOLE_ENABLE=true",
    "RUSTFS_OBS_LOGGER_LEVEL=error",
  ]
  volumes {
    host_path      = var.data_dir
    container_path = "/data"
  }
  ports {
    internal = 9000
    external = var.api_port
    ip       = "127.0.0.1"
  }
  ports {
    internal = 9001
    external = var.api_port + 1
    ip       = "127.0.0.1"
  }
  healthcheck {
    test         = ["CMD", "curl", "--fail", "--silent", "http://127.0.0.1:9000/health"]
    interval     = "5s"
    timeout      = "3s"
    retries      = 12
    start_period = "10s"
  }
  wait         = true
  wait_timeout = 120
}

output "endpoint" {
  value = "http://127.0.0.1:${var.api_port}"
}
