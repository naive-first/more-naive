#!/usr/bin/env bash
set -euo pipefail
nodes=(); write=false
while (($#)); do
  case $1 in
    --node) [[ $# -ge 2 ]] || exit 2; nodes+=("$2"); shift 2 ;;
    --write-smoke) write=true; shift ;;
    *) echo 'use --node NAME [--node NAME] [--write-smoke]' >&2; exit 2 ;;
  esac
done
[[ ${KUBE_CONTEXT-} == more-naive-prod && ${#nodes[@]} -gt 0 ]] || { echo 'explicit prod node inventory required' >&2; exit 2; }
expected=$(printf '%s\n' "${nodes[@]}" | jq -Rsc 'split("\n")[:-1] | sort')
[[ $(jq 'unique | length' <<< "$expected") == "${#nodes[@]}" ]] || { echo 'duplicate nodes' >&2; exit 2; }
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)
bash "$root/scripts/check-cluster.sh"
kube=(kubectl --context "$KUBE_CONTEXT" --request-timeout=30s)
actual=$("${kube[@]}" get nodes -o json | jq -c '[.items[].metadata.name] | sort')
[[ $actual == "$expected" ]] || { echo 'node inventory differs; no probe created' >&2; exit 2; }
for node in "${nodes[@]}"; do "${kube[@]}" wait "node/$node" --for=condition=Ready --timeout=120s; done
echo 'PASS: context, API server, exact node inventory and Ready'
$write || { echo 'DNS/Pod communication NOT_RUN; use --write-smoke'; exit 0; }
namespace=more-naive-network-$(od -An -N5 -tx1 /dev/urandom | tr -d ' \n')
"${kube[@]}" create namespace "$namespace" >/dev/null
cleanup() {
  result=$?; trap - EXIT
  if ! "${kube[@]}" delete namespace "$namespace" --wait=true --timeout=120s; then result=1; fi
  exit "$result"
}
trap cleanup EXIT
pods=(); addresses=(); index=0
for node in "${nodes[@]}"; do
  name=probe-$index
  overrides=$(jq -nc --arg node "$node" '{spec:{nodeName:$node,automountServiceAccountToken:false,securityContext:{runAsUser:1000,runAsGroup:1000}}}')
  "${kube[@]}" -n "$namespace" run "$name" --image=busybox:1.37.0 --restart=Never --overrides="$overrides" --command -- sh -ec 'mkdir /tmp/www; echo ok >/tmp/www/index.html; httpd -f -p 8080 -h /tmp/www'
  "${kube[@]}" -n "$namespace" wait "pod/$name" --for=condition=Ready --timeout=120s
  address=$("${kube[@]}" -n "$namespace" get pod "$name" -o json | jq -er '.status.podIP')
  pods+=("$name"); addresses+=("$address"); index=$((index+1))
done
for name in "${pods[@]}"; do
  "${kube[@]}" -n "$namespace" exec "$name" -- nslookup kubernetes.default.svc.cluster.local
  for address in "${addresses[@]}"; do
    [[ $address != *:* ]] || address="[$address]"
    reply=$("${kube[@]}" -n "$namespace" exec "$name" -- wget -qO- -T 10 "http://$address:8080")
    [[ $reply == ok ]] || { echo 'unexpected peer HTTP result' >&2; exit 1; }
  done
done
echo "PASS: DNS on ${#pods[@]} nodes and $((${#pods[@]} * ${#pods[@]})) Pod HTTP paths"
