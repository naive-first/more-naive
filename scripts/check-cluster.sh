#!/usr/bin/env bash
set -euo pipefail
[[ ${MORE_NAIVE_ENV-} == prod && -n ${KUBE_CONTEXT-} && ${KUBE_SERVER-} == https://* ]] || {
  echo 'explicit prod context and HTTPS API server required' >&2; exit 2;
}
actual=$(kubectl --context "$KUBE_CONTEXT" --request-timeout=30s config view --minify -o 'jsonpath={.clusters[0].cluster.server}')
[[ $actual == "$KUBE_SERVER" ]] || { echo 'context API endpoint mismatch' >&2; exit 2; }
