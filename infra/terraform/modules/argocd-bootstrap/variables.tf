variable "context" { type = string }
variable "expected_server" {
  type = string
  validation {
    condition     = startswith(var.expected_server, "https://")
    error_message = "An explicit HTTPS API server is required."
  }
}
variable "kubeconfig" { type = string }
variable "values_file" { type = string }
variable "bootstrap_script" { type = string }
