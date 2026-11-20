#!/usr/bin/env bash
set -euo pipefail
[[ $# == 0 || ( $# == 1 && $1 == --apply ) ]] || { echo 'use --apply after provider installation' >&2; exit 2; }
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)
repo_token=${ARGO_REPO_TOKEN-}; repo_username=${ARGO_REPO_USERNAME-}
unset ARGO_REPO_TOKEN ARGO_REPO_USERNAME RUSTFS_ADMIN_ACCESS_KEY RUSTFS_ADMIN_SECRET_KEY RUSTFS_STATE_ACCESS_KEY RUSTFS_STATE_SECRET_KEY
bash "$root/scripts/check-cluster.sh"
helm template argocd oci://ghcr.io/argoproj/argo-helm/argo-cd --version 10.18.0 --namespace argocd --values "$root/infra/environments/prod/argocd.yaml" >/dev/null
if [[ $# == 0 ]]; then echo 'prod context/API and chart verified; no cluster writes'; exit 0; fi
kube=(kubectl --context "$KUBE_CONTEXT" --request-timeout=30s)
for name in istio-system more-naive-prod; do
  jq -n --arg name "$name" '{apiVersion:"v1",kind:"Namespace",metadata:({name:$name} + if $name == "more-naive-prod" then {labels:{"istio-injection":"enabled"}} else {} end)}' | "${kube[@]}" apply -f -
done
if [[ -n $repo_token ]]; then
  if ! ARGO_REPO_TOKEN="$repo_token" ARGO_REPO_USERNAME="$repo_username" jq -n -f "$root/infra/argocd/bootstrap/repository-secret.jq" |
       "${kube[@]}" apply --server-side --field-manager=more-naive-bootstrap -f - >/dev/null 2>/dev/null; then
    echo 'repository credential injection failed; values suppressed' >&2; exit 1
  fi
fi
for resource in deployment/argocd-server deployment/argocd-repo-server statefulset/argocd-application-controller; do
  "${kube[@]}" -n argocd rollout status "$resource" --timeout=300s
done
project="$root/infra/argocd/bootstrap/prod/project.yaml"
if [[ -f $project ]]; then "${kube[@]}" apply -f "$project"; fi
"${kube[@]}" apply -f "$root/infra/argocd/projects/prod"
while read -r name namespace resource condition; do
  declaration="$root/infra/argocd/applications/prod/$name.yaml"
  [[ -f $declaration ]] || continue
  "${kube[@]}" apply -f "$declaration"
  "${kube[@]}" -n argocd wait "application/$name" '--for=jsonpath={.status.sync.status}=Synced' --timeout=600s
  "${kube[@]}" -n argocd wait "application/$name" '--for=jsonpath={.status.health.status}=Healthy' --timeout=600s
  if [[ $condition == rollout ]]; then
    "${kube[@]}" -n "$namespace" rollout status "$resource" --timeout=300s
  else
    "${kube[@]}" -n "$namespace" wait "$resource" "--for=condition=$condition" --timeout=300s
  fi
done <<'STAGES'
istio-base istio-system crd/gateways.networking.istio.io Established
istiod istio-system deployment/istiod Available
istio-gateway istio-system deployment/istio-ingressgateway Available
postgres more-naive-prod statefulset/postgres rollout
backend more-naive-prod deployment/backend Available
STAGES
"${kube[@]}" apply -f "$root/infra/argocd/bootstrap/prod/root.yaml"
"${kube[@]}" -n argocd wait application/more-naive-prod '--for=jsonpath={.status.sync.status}=Synced' --timeout=300s
echo 'Argo CD Ready and prod root Synced'
