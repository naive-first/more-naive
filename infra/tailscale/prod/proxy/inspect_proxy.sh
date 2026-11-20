#!/usr/bin/env bash
set -euo pipefail
[[ $# == 0 ]] || { echo 'set PROXY_* inputs in the selected environment file' >&2; exit 2; }
upstream=${PROXY_UPSTREAM_URL-}; gateway=${PROXY_GATEWAY_HOST-}
[[ -z $upstream && -z $gateway || -n $upstream && -n $gateway ]] || { echo 'upstream URL and gateway Host required together' >&2; exit 2; }
if [[ -n $upstream ]]; then
  [[ $upstream =~ ^https?://(\[[a-fA-F0-9:]+\]|[a-zA-Z0-9][a-zA-Z0-9.-]*)(:[0-9]+)?(/[a-zA-Z0-9/_.~%-]*)?$ && $gateway =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*(:[0-9]+)?$ ]] || {
    echo 'explicit HTTP(S) upstream without credentials/query/fragment and valid gateway Host required' >&2; exit 2;
  }
fi
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd -P)
SSH_HOST=${PROXY_HOST-}; SSH_USER=${PROXY_USER-}; SSH_KEY_FILE=${PROXY_KEY_FILE-}; SSH_EXPECTED_HOST=${PROXY_EXPECTED_HOST-}
source "$root/scripts/check-ssh.sh"
printf -v remote 'bash -s -- %q %q %q %q' "$upstream" "$gateway" "$SSH_EXPECTED_HOST" "$SSH_USER"
"${SSH_COMMAND[@]}" "$remote" <<'REMOTE'
set -euo pipefail
upstream=$1; gateway=$2
[[ $(hostname) == "$3" && $(id -un) == "$4" ]] || { echo 'remote hostname/user mismatch' >&2; exit 2; }
command -v tailscale >/dev/null || { echo 'Tailscale is not installed on this SSH destination; inspect the actual tailnet proxy host' >&2; exit 2; }
status=$(tailscale status --json 2>/dev/null) || { echo 'Tailscale status lookup failed' >&2; exit 1; }
serve=$(tailscale serve status --json 2>/dev/null) || { echo 'Tailscale Serve lookup failed' >&2; exit 1; }
sudo_ok=false; if sudo -n true >/dev/null 2>&1; then sudo_ok=true; fi
upstream_status='NOT_RUN: actual private upstream not supplied'
if [[ -n $upstream ]]; then
  authority=${upstream#*://}; authority=${authority%%/*}; scheme=${upstream%%:*}
  port=80; [[ $scheme != https ]] || port=443
  if [[ $authority == \[* ]]; then
    host=${authority#\[}; host=${host%%\]*}; rest=${authority#*\]}
    [[ -z $rest ]] || port=${rest#:}
  else
    host=${authority%%:*}; [[ $authority != *:* ]] || port=${authority##*:}
  fi
  [[ ${#port} -le 5 && $port =~ ^[0-9]+$ && $((10#$port)) -ge 1 && $((10#$port)) -le 65535 ]] || { echo 'invalid upstream port' >&2; exit 2; }
  if [[ $host == *:* || $host =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then addresses=$(printf '%s\n' "$host" | tr 'A-F' 'a-f'); else
    records=$(dig +time=5 +tries=1 +noall +answer A "$host" && dig +time=5 +tries=1 +noall +answer AAAA "$host")
    addresses=$(awk '$4=="A" || $4=="AAAA" {print tolower($5)}' <<< "$records")
  fi
  [[ -n $addresses ]] || { echo 'upstream has no addresses' >&2; exit 2; }
  while IFS= read -r ip; do
    if [[ $ip == *:* ]]; then
      [[ $ip == ::1 || $ip =~ ^f[cd][0-9a-f]{2}: || $ip =~ ^fe[89ab][0-9a-f]: ]] || { echo 'upstream must resolve exclusively to private addresses' >&2; exit 2; }
    else
      awk -F. 'NF==4 && $1>=0 && $1<=255 && $2>=0 && $2<=255 && $3>=0 && $3<=255 && $4>=0 && $4<=255 && ($1==10 || $1==127 || ($1==172 && $2>=16 && $2<=31) || ($1==192 && $2==168) || ($1==169 && $2==254) || ($1==100 && $2>=64 && $2<=127)) {exit 0} {exit 1}' <<< "$ip" || { echo 'upstream must resolve exclusively to private addresses' >&2; exit 2; }
    fi
  done <<< "$addresses"
  first=${addresses%%$'\n'*}; [[ $first != *:* ]] || first="[$first]"
  resolve=()
  if [[ $host != *:* && ! $host =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then resolve=(--resolve "$host:$port:$first"); fi
  upstream_status=$(curl --silent --show-error --noproxy '*' --max-time 10 "${resolve[@]}" --header "Host: $gateway" --output /dev/null --write-out '%{http_code}' "$upstream")
fi
printf '%s\n%s' "$status" "$serve" | jq -s --arg hostname "$(hostname)" --arg user "$(id -un)" --argjson sudo "$sudo_ok" --arg upstream "$upstream_status" '{hostname:$hostname,user:$user,tailscale_state:.[0].BackendState,dns_name:.[0].Self.DNSName,tailnet_ips:(.[0].Self.TailscaleIPs // []),serve_tcp_ports:((.[1].TCP // {})|keys),serve_web_hosts:((.[1].Web // {})|keys),sudo_noninteractive:$sudo,upstream_status:$upstream}'
REMOTE
