#!/usr/bin/env bash
set -euo pipefail
[[ $# == 1 && $1 == --apply ]] || { echo 'explicit --apply required' >&2; exit 2; }
[[ ${NAMESPACE-} == more-naive-prod ]] || { echo 'more-naive-prod namespace required' >&2; exit 2; }
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
password=${DB_PASSWORD-}
redis_password=${REDIS_PASSWORD-}
unset DB_PASSWORD REDIS_PASSWORD ARGO_REPO_TOKEN RUSTFS_ADMIN_ACCESS_KEY RUSTFS_ADMIN_SECRET_KEY RUSTFS_STATE_ACCESS_KEY RUSTFS_STATE_SECRET_KEY
if ! payload=$(DB_PASSWORD="$password" REDIS_PASSWORD="$redis_password" jq -n -f "$root/scripts/prod-config.jq" 2>/dev/null); then
  echo 'required database inputs missing; values suppressed' >&2; exit 2
fi
unset password redis_password DB_DATABASE DB_USERNAME DB_URL
bash "$root/scripts/check-cluster.sh"
kube=(kubectl --context "$KUBE_CONTEXT" --namespace "$NAMESPACE" --request-timeout=30s)
if ! "${kube[@]}" get namespace "$NAMESPACE" -o json | jq -e --arg name "$NAMESPACE" '.metadata.name == $name' >/dev/null; then
  echo 'namespace identity could not be verified' >&2; exit 2
fi
if ! printf '%s' "$payload" | "${kube[@]}" apply --server-side --field-manager=more-naive-config -f - >/dev/null 2>/dev/null; then
  echo 'kubectl apply failed; inspect access and field ownership without rendering secrets' >&2; exit 2
fi
for kind in ConfigMap Secret; do
  if [[ $kind == ConfigMap ]]; then resource=configmap; name=more-naive-config; else resource=secret; name=more-naive-db; fi
  if ! actual=$("${kube[@]}" get "$resource" "$name" -o json 2>/dev/null); then
    echo 'readback failed; values suppressed' >&2; exit 2
  fi
  if ! printf '%s\n%s' "$payload" "$actual" | jq -se --arg kind "$kind" '([.[0].items[] | select(.kind == $kind)][0].data) == .[1].data' >/dev/null 2>/dev/null; then
    echo 'readback differs; values suppressed' >&2; exit 2
  fi
done
echo 'verified: prod more-naive-config and more-naive-db; values suppressed'
