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
    execute  = ["bash", "${get_repo_root()}/infra/k3s/scripts/preflight.sh"]
  }
  extra_arguments "join_token" {
    commands = get_terraform_commands_that_need_vars()
    env_vars = { TF_VAR_token = get_env("K3S_TOKEN") }
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
  tls_san          = get_env("K3S_ROLE") == "server" ? yamldecode(file("${get_repo_root()}/infra/environments/prod/istio-route.yaml")).host : ""
}
