terraform {
  required_version = "= 1.17.2"
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "3.3.0"
    }
  }
}

provider "helm" {
  kubernetes = {
    config_paths   = [for config in split(":", var.kubeconfig) : pathexpand(config)]
    config_context = var.context
  }
}

resource "helm_release" "argocd" {
  name             = "argocd"
  repository       = "oci://ghcr.io/argoproj/argo-helm"
  chart            = "argo-cd"
  version          = "10.18.0"
  namespace        = "argocd"
  create_namespace = true
  wait             = true
  timeout          = 600
  replace          = false
  values           = [file(var.values_file)]
}

resource "terraform_data" "registration" {
  # Repository credentials stay outside state. Each apply re-injects them and
  # verifies the root after Helm has installed the Application CRD.
  triggers_replace = [timestamp()]
  depends_on       = [helm_release.argocd]
  provisioner "local-exec" {
    command = "bash \"$ARGO_BOOTSTRAP_SCRIPT\" --apply"
    environment = {
      ARGO_BOOTSTRAP_SCRIPT = var.bootstrap_script
      KUBE_CONTEXT          = var.context
      KUBE_SERVER           = var.expected_server
      KUBECONFIG            = var.kubeconfig
    }
  }
}
