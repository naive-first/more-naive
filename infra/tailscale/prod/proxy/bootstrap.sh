#!/usr/bin/env bash
set -euo pipefail
[[ $# == 0 || ( $# == 1 && $1 == --apply ) ]] || { echo 'use --apply after preflight' >&2; exit 2; }
fail() { echo "$1" >&2; exit 2; }
[[ ${MORE_NAIVE_ENV-} == prod && ${PROXY_EXPECTED_HOST-} == "$(hostname)" && $(id -u) == 0 ]] || fail 'explicit prod, matching OS hostname and root required'
host=${PROXY_HTTPS_HOSTNAME-}; port=${RELAY_PORT-}
[[ $host =~ ^[a-z0-9][a-z0-9.-]*\.ts\.net$ && $port =~ ^[0-9]{1,5}$ && $port -ge 1024 && $port -le 65535 ]] || fail 'tailnet HTTPS host and private relay port required'
for tool in jq curl systemctl install ss timeout cmp; do command -v "$tool" >/dev/null || fail "required tool missing: $tool"; done
tailscale=/usr/local/bin/tailscale; kube=/usr/local/bin/k3s
[[ -x $tailscale && -x $kube ]] || fail 'Tailscale and k3s installation must complete first'
status=$("$tailscale" status --json)
jq -e --arg host "$host" '.BackendState=="Running" and (.Self.DNSName|rtrimstr("."))==$host' <<< "$status" >/dev/null || fail 'authenticated node DNS differs from selected HTTPS host'
proxy="http://127.0.0.1:$port"
before=$("$tailscale" serve status --json)
jq -e --arg host "$host:443" '.AllowFunnel[$host]!=true' <<< "$before" >/dev/null || fail 'Funnel must be disabled for the selected HTTPS host'
if jq -e --arg host "$host:443" '.TCP["443"]!=null or .Web[$host]!=null' <<< "$before" >/dev/null; then
  jq -e --arg host "$host:443" --arg proxy "$proxy" '.TCP["443"].HTTPS==true and .Web[$host].Handlers=={"/":{"Proxy":$proxy}} and .AllowFunnel[$host]!=true' <<< "$before" >/dev/null || fail 'HTTPS 443 already belongs to another Serve configuration'
fi
unit=more-naive-gateway-relay.service
source_unit="$(dirname "${BASH_SOURCE[0]}")/$unit"
[[ -f $source_unit ]] || fail 'rendered relay service required'
if systemctl cat "$unit" >/dev/null 2>&1; then
  cmp -s "$source_unit" "/etc/systemd/system/$unit" || fail 'existing relay service differs; review before replacing'
fi
if [[ -n $(ss -H -ltn "sport = :$port") ]]; then systemctl is-active --quiet "$unit" || fail 'loopback relay port is occupied by another service'; fi
"$kube" kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml -n istio-system rollout status deployment/istio-ingressgateway --timeout=120s
gateway_ip=$("$kube" kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml -n istio-system get service istio-ingressgateway -o 'jsonpath={.spec.clusterIP}')
[[ $gateway_ip =~ ^10\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail 'private gateway ClusterIP required'
curl --fail --silent --show-error --noproxy '*' --max-time 10 --header "Host: $host" --output /dev/null "http://$gateway_ip/api/tests"
if [[ $# == 0 ]]; then echo 'node identity, gateway and Serve ownership verified; no changes'; exit 0; fi
install -m 644 "$source_unit" "/etc/systemd/system/$unit"
systemctl daemon-reload
systemctl enable --now "$unit"
ready=false
for ((attempt=0; attempt<20; attempt++)); do
  if curl --fail --silent --show-error --noproxy '*' --max-time 2 --header "Host: $host" --output /dev/null "$proxy/api/tests" 2>/dev/null; then ready=true; break; fi
  sleep 1
done
[[ $ready == true ]] || fail 'gateway loopback relay is not ready'
umask 077
if output=$(timeout 45s "$tailscale" serve --bg --yes --https=443 "$proxy" 2>&1); then code=0; else code=$?; fi
if [[ $code != 0 || $output == *https://login.tailscale.com/* ]]; then
  install -d -m 700 /var/lib/more-naive-proxy
  printf '%s\n' "$output" > /var/lib/more-naive-proxy/serve-approval.txt
  fail "Serve configuration needs inspection (exit $code); private output: /var/lib/more-naive-proxy/serve-approval.txt"
fi
after=$("$tailscale" serve status --json)
jq -e --arg host "$host:443" --arg proxy "$proxy" '.TCP["443"].HTTPS==true and .Web[$host].Handlers["/"].Proxy==$proxy and .AllowFunnel[$host]!=true' <<< "$after" >/dev/null || fail 'Serve target or private-only policy differs'
other_config='{TCP:((.TCP//{})|del(.["443"])),Web:((.Web//{})|del(.[$host])),AllowFunnel:((.AllowFunnel//{})|del(.[$host]))}'
[[ $(jq -cS --arg host "$host:443" "$other_config" <<< "$before") == "$(jq -cS --arg host "$host:443" "$other_config" <<< "$after")" ]] || fail 'unrelated Serve configuration changed'
printf '%s\n' "$output"
echo 'private tailnet HTTPS -> loopback relay -> Istio gateway configured'
