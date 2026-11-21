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

variable "admin_password_hash" {
  description = "선택한 admin 비밀번호의 bcrypt 해시. 빈 값이면 Helm에 비밀번호를 지정하지 않습니다."
  type        = string
  default     = ""
  sensitive   = true
  nullable    = false

  validation {
    condition = var.admin_password_hash == "" || can(regex(
      "^\\$2[aby]\\$(0[4-9]|[12][0-9]|3[01])\\$[./A-Za-z0-9]{53}$",
      var.admin_password_hash
    ))
    error_message = "admin_password_hash는 빈 값 또는 유효한 형식의 bcrypt 해시여야 합니다. 평문 비밀번호는 사용할 수 없습니다."
  }
}
