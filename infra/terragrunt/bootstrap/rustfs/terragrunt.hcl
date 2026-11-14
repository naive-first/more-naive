terraform_binary              = "terraform"
terraform_version_constraint  = "= 1.17.2"
terragrunt_version_constraint = "= 1.2.2"

terraform {
  source = "${get_repo_root()}/infra/terraform/modules/rustfs"
  before_hook "persistent_paths" {
    commands = ["init", "plan", "apply", "destroy", "output", "validate"]
    execute  = ["sh", "${get_terragrunt_dir()}/preflight.sh", get_repo_root(), get_terraform_command()]
  }
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
  api_port = tonumber(trimprefix(get_env("RUSTFS_ENDPOINT"), "http://127.0.0.1:"))
}
