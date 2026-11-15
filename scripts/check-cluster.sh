#!/usr/bin/env bash
set -euo pipefail
[[ ${MORE_NAIVE_ENV-} == prod && -n ${KUBE_CONTEXT-} && ${KUBE_SERVER-} == https://* ]] || {
  echo 'explicit prod context and HTTPS API server required' >&2; exit 2;
}
if ! actual=$(kubectl --context "$KUBE_CONTEXT" --request-timeout=30s config view --minify -o 'jsonpath={.clusters[0].cluster.server}' 2>/dev/null); then
  echo 'context API lookup failed; values suppressed' >&2; exit 2
fi
[[ $actual == "$KUBE_SERVER" ]] || { echo 'context API endpoint mismatch' >&2; exit 2; }
