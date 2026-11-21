#!/usr/bin/env bash
set -euo pipefail
write=false; restart_backend=false; restart_db=false
for arg in "$@"; do
  case $arg in --allow-write) write=true;; --restart-backend) restart_backend=true;; --restart-db) restart_db=true;; *) echo 'unknown smoke option' >&2; exit 2;; esac
done
fail() { echo "$1" >&2; exit 2; }
[[ ${MORE_NAIVE_ENV-} == prod && ${NAMESPACE-} == more-naive-prod ]] || fail 'explicit prod and more-naive-prod namespace required'
[[ ${PROXY_HTTPS_HOSTNAME-} =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*\.ts\.net$ ]] || fail 'tailnet HTTPS hostname required'
[[ $write == true || ( $restart_backend == false && $restart_db == false ) ]] || fail 'restart requires --allow-write'
unset DB_PASSWORD ARGO_REPO_TOKEN TAILSCALE_AUTH_KEY RUSTFS_ADMIN_ACCESS_KEY RUSTFS_ADMIN_SECRET_KEY RUSTFS_STATE_ACCESS_KEY RUSTFS_STATE_SECRET_KEY
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
bash "$root/scripts/check-cluster.sh"
umask 077
temporary=$(mktemp -d); owned=()
request() {
  local method=$1 suffix=${2-} value=${3-}
  local args=(curl --silent --show-error --noproxy '*' --max-time 20 --request "$method" --header 'Content-Type: application/json' --output "$temporary/body" --write-out '%{http_code}')
  if [[ $method == POST || $method == PUT ]]; then
    status=$(jq -n --arg value "$value" '{value:$value}' | "${args[@]}" --data-binary @- "https://$PROXY_HTTPS_HOSTNAME/api/tests$suffix")
  else
    status=$("${args[@]}" "https://$PROXY_HTTPS_HOSTNAME/api/tests$suffix")
  fi
  printf '%s /api/tests%s: %s\n' "$method" "$suffix" "$status"
}
cleanup() {
  local result=$? id; trap - EXIT
  for id in "${owned[@]}"; do
    [[ -n $id ]] || continue
    if ! request DELETE "/$id" || [[ $status != 204 && $status != 404 ]]; then
      echo "cleanup failed; owned row ID needs inspection: $id" >&2; result=2
    fi
  done
  rm -rf "$temporary"; exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
request GET
[[ $status == 200 ]] && jq -e 'type=="array"' "$temporary/body" >/dev/null || fail 'test list is not ready'
if ! $write; then echo 'read-only verification passed; no rows or Pods changed'; exit 0; fi
seed=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
for label in target control; do
  value="smoke-$seed-$label"; request POST '' "$value"
  [[ $status == 201 ]] && jq -e --arg value "$value" '.value==$value' "$temporary/body" >/dev/null || fail 'create outcome uncertain; inspect before retrying'
  id=$(jq -er '.id | select(type=="number" and .>=1 and .<=9007199254740991 and floor==.) | tostring' "$temporary/body") || fail 'create ID invalid; inspect request outcome before retrying'
  [[ ! " ${owned[*]} " == *" $id "* ]] || fail 'duplicate created ID'
  owned+=("$id")
  if [[ $label == target ]]; then target=$id; else control=$id; fi
done
changed="smoke-$seed-updated"
request PUT "/$target" "$changed"
[[ $status == 200 ]] && jq -e --argjson id "$target" --arg value "$changed" '.=={id:$id,value:$value}' "$temporary/body" >/dev/null || fail 'update contract mismatch'
kube=(kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" --request-timeout=30s)
for resource in deployment/backend statefulset/postgres; do
  if [[ $resource == deployment/backend && $restart_backend == true || $resource == statefulset/postgres && $restart_db == true ]]; then
    "${kube[@]}" rollout restart "$resource"
    "${kube[@]}" rollout status "$resource" --timeout=300s
  fi
done
request GET "/$target"
[[ $status == 200 ]] && jq -e --argjson id "$target" --arg value "$changed" '.=={id:$id,value:$value}' "$temporary/body" >/dev/null || fail 'readback/persistence contract mismatch'
request GET "/$control"
[[ $status == 200 ]] && jq -e --argjson id "$control" --arg value "smoke-$seed-control" '.=={id:$id,value:$value}' "$temporary/body" >/dev/null || fail 'control row changed'
request DELETE "/$target"
[[ $status == 204 && ! -s $temporary/body ]] || fail 'delete contract mismatch'
owned[0]=''
for method in GET DELETE; do request "$method" "/$target"; [[ $status == 404 ]] || fail 'deleted row must return 404'; done
echo 'owned-row CRUD/persistence verification passed'
