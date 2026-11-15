include "root" {
  path = find_in_parent_folders("root.hcl")
}
include "state" {
  path = find_in_parent_folders("state.hcl")
}
terraform {
  source = "${get_repo_root()}/infra/terraform/modules/argocd-bootstrap"
  before_hook "cluster_identity" {
    commands = ["init", "plan", "apply"]
    execute  = ["bash", "${get_repo_root()}/infra/argocd/bootstrap/bootstrap.sh"]
  }
}
inputs = {
  context          = get_env("KUBE_CONTEXT")
  expected_server  = get_env("KUBE_SERVER")
  kubeconfig       = get_env("KUBECONFIG", "${get_env("HOME")}/.kube/config")
  values_file      = "${get_repo_root()}/infra/environments/prod/argocd.yaml"
  bootstrap_script = "${get_repo_root()}/infra/argocd/bootstrap/bootstrap.sh"
}
