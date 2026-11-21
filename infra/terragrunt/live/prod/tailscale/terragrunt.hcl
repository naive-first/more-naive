include "root" {
  path = find_in_parent_folders("root.hcl")
}
include "state" {
  path = find_in_parent_folders("state.hcl")
}
terraform {
  source = "${get_repo_root()}/infra/terraform/modules/tailscale"
  before_hook "node_identity" {
    commands = ["init", "plan", "apply"]
    execute  = ["bash", "${get_repo_root()}/scripts/check-ssh.sh"]
  }
}
inputs = {
  host             = get_env("SSH_HOST")
  user             = get_env("SSH_USER")
  host_key         = get_env("SSH_HOST_KEY")
  private_key_file = get_env("SSH_KEY_FILE")
  node             = get_env("TAILSCALE_EXPECTED_HOST")
  node_directory   = "${get_repo_root()}/infra/tailscale/prod/node"
}
