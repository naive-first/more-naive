locals {
  state_unit = get_env("RUSTFS_STATE_UNIT")
}

remote_state {
  backend = "s3"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    bucket                      = get_env("RUSTFS_BUCKET")
    key                         = "more-naive/prod/${local.state_unit}/terraform.tfstate"
    workspace_key_prefix        = "more-naive/prod/workspaces"
    region                      = get_env("RUSTFS_REGION")
    endpoints                   = { s3 = get_env("RUSTFS_ENDPOINT") }
    profile                     = "more-naive-state"
    shared_credentials_file     = get_env("RUSTFS_CREDENTIALS_FILE")
    use_path_style              = true
    use_lockfile                = true
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_metadata_api_check     = true
    skip_requesting_account_id  = true
    disable_bucket_update       = true
    skip_bucket_versioning      = true
    skip_bucket_ssencryption    = true
    skip_bucket_enforced_tls    = true
  }
}
