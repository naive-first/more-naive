include "root" {
  path = find_in_parent_folders("root.hcl")
}
include "state" {
  path = find_in_parent_folders("state.hcl")
}
terraform {
  source = "${get_repo_root()}/infra/terraform/modules/k3s"
  before_hook "node_identity" {
    commands = ["init", "plan", "apply"]
    execute = ["python3", "${get_repo_root()}/infra/k3s/scripts/preflight.py", "--environment", "prod",
      "--host", get_env("SSH_HOST"), "--user", get_env("SSH_USER"), "--node", get_env("K3S_NODE_NAME"),
    "--key-file", get_env("SSH_KEY_FILE"), "--role", get_env("K3S_ROLE")]
  }
}
inputs = {
  host             = get_env("SSH_HOST")
  user             = get_env("SSH_USER")
  host_key         = get_env("SSH_HOST_KEY")
  private_key_file = get_env("SSH_KEY_FILE")
  node             = get_env("K3S_NODE_NAME")
  role             = get_env("K3S_ROLE")
  server_url       = get_env("K3S_SERVER_URL", "")
}
