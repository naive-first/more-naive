#!/usr/bin/env bash
set -euo pipefail
[[ ${K3S_NODE_NAME-} =~ ^[a-z0-9][a-z0-9.-]{0,62}$ && ${K3S_ROLE-} =~ ^(server|agent)$ ]] || {
  echo 'expected k3s node and server/agent role required' >&2; exit 2;
}
[[ ${K3S_TOKEN-} =~ [^[:space:]] && $K3S_TOKEN != *$'\n'* && $K3S_TOKEN != *$'\r'* ]] || {
  echo 'K3S_TOKEN must be nonempty and single-line' >&2; exit 2;
}
if [[ $K3S_ROLE == agent ]]; then
  server='^https://([A-Za-z0-9.-]+|\[[0-9a-fA-F:]+\]):6443$'
  [[ ${K3S_SERVER_URL-} =~ $server ]] || { echo 'agent requires private server HTTPS URL on port 6443' >&2; exit 2; }
fi
export SSH_EXPECTED_HOST=$K3S_NODE_NAME
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)
source "$root/scripts/check-ssh.sh"
tailscale status --json | jq -e '.BackendState == "Running"' >/dev/null
tailscale ping --c=1 --timeout=10s --until-direct=false "$SSH_HOST" >/dev/null
"${SSH_COMMAND[@]}" 'sudo -n true'
echo 'prod node identity, sudo and operator tailnet reachability verified; no installation performed'
