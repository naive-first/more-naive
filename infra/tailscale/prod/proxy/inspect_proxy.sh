#!/usr/bin/env bash
set -euo pipefail
[[ $# == 0 && ${PROXY_HTTPS_HOSTNAME-} =~ ^[a-z0-9][a-z0-9.-]*\.ts\.net$ ]] || {
  echo 'set PROXY_HTTPS_HOSTNAME in the selected environment file' >&2; exit 2;
}
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd -P)
SSH_EXPECTED_HOST=${PROXY_EXPECTED_HOST-}
source "$root/scripts/check-ssh.sh"
printf -v remote 'bash -s -- %q' "$PROXY_HTTPS_HOSTNAME"
"${SSH_COMMAND[@]}" "$remote" <<'REMOTE'
set -euo pipefail
host=$1
listener=172.30.104.10:18080
systemctl is-active more-naive-gateway-relay.service
[[ $(ss -H -ltn 'sport = :18080' | awk '{print $4}') == "$listener" ]] || {
  echo 'expected only the private relay listener' >&2; exit 1;
}
for path in /api/tests /argocd/; do
  code=$(curl --fail --silent --show-error --noproxy '*' --max-time 10 --header "Host: $host" \
    --output /dev/null --write-out '%{http_code}' "http://$listener$path")
  printf '%s %s %s\n' "$listener" "$path" "$code"
  [[ $code == 200 ]] || exit 1
done
REMOTE
for path in /api/tests /argocd/; do
  code=$(curl --fail --silent --show-error --noproxy '*' --max-time 10 \
    --output /dev/null --write-out '%{http_code}' "https://$PROXY_HTTPS_HOSTNAME$path")
  printf '%s %s %s\n' "$PROXY_HTTPS_HOSTNAME" "$path" "$code"
  [[ $code == 200 ]] || exit 1
done
