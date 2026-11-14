terraform_binary              = "terraform"
terraform_version_constraint  = "= 1.17.2"
terragrunt_version_constraint = "= 1.2.2"

terraform {
  source = "${get_repo_root()}/infra/terraform/modules/rustfs"
}

remote_state {
  backend = "local"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    path = get_env("RUSTFS_STATE_PATH")
  }
}

inputs = {
  data_dir = get_env("RUSTFS_DATA_DIR")
  name     = get_env("RUSTFS_NAME", "more-naive-rustfs")
  api_port = tonumber(get_env("RUSTFS_API_PORT", "9000"))
}
