#!/usr/bin/env bash
set -euo pipefail
[[ $# == 0 || ( $# == 1 && $1 == --apply ) ]] || { echo 'use --apply after preflight' >&2; exit 2; }
fail() { echo "$1" >&2; exit 2; }
[[ ${MORE_NAIVE_ENV-} == prod && ${PROXY_EXPECTED_HOST-} == "$(hostname)" && $(id -u) == 0 ]] || fail 'explicit prod, matching OS hostname and root required'
host=${GATEWAY_HOST-}; address=${RELAY_ADDRESS-}; port=${RELAY_PORT-}
[[ $host =~ ^[a-z0-9][a-z0-9.-]*\.ts\.net$ && $address == 172.30.104.10 && $port == 18080 ]] || fail 'prod gateway Host and private relay endpoint required'
[[ -n $(ip -o -4 addr show to "$address/32") ]] || fail 'private relay address is not assigned to this VM'

unit=more-naive-gateway-relay.service
unit_path="/etc/systemd/system/$unit"
source_unit="$(dirname "${BASH_SOURCE[0]}")/$unit"
[[ -f $source_unit ]] || fail 'rendered relay service required'
fragment=$(systemctl show "$unit" --property=FragmentPath --value)
if [[ -n $fragment || -e $unit_path ]]; then
  [[ $fragment == "$unit_path" ]] || fail 'existing relay service has a different owner'
  cmp -s "$source_unit" "$unit_path" ||
    cmp -s "$unit_path" <(sed -e 's/gateway private relay/gateway loopback relay/' \
      -e 's/--address=[^ ]*/--address=127.0.0.1/' -e '/^PartOf=k3s\.service$/d' "$source_unit") ||
    fail 'existing relay service differs from managed versions'
fi
drop_in=$(systemctl show "$unit" --property=DropInPaths --value)
if [[ -n $drop_in ]]; then
  [[ $drop_in == "$unit_path.d/10-private-listener.conf" ]] &&
    cmp -s "$drop_in" <(printf '[Service]\nExecStart=\n'; sed -n '/^ExecStart=/p' "$source_unit") ||
    fail 'relay drop-in differs from the known private listener'
fi

proxy="$address:$port"
listener=$(ss -H -ltn "sport = :$port" | awk '{print $4}')
if [[ -n $listener ]]; then
  [[ $listener == "$proxy" || $listener == "127.0.0.1:$port" ]] &&
    systemctl is-active --quiet "$unit" || fail 'relay port is occupied by another listener'
fi
kube=(/usr/local/bin/k3s kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml -n istio-system)
"${kube[@]}" rollout status deployment/istio-ingressgateway --timeout=120s
gateway_ip=$("${kube[@]}" get service istio-ingressgateway -o 'jsonpath={.spec.clusterIP}')
[[ $gateway_ip =~ ^10\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail 'private gateway ClusterIP required'
[[ $(curl --fail --silent --show-error --noproxy '*' --max-time 10 --header "Host: $host" \
  --output /dev/null --write-out '%{http_code}' "http://$gateway_ip:80/api/tests") == 200 ]] || fail 'Istio gateway route is not ready'
if [[ $# == 0 ]]; then echo 'node, private listener configuration and gateway verified'; exit 0; fi

if ! cmp -s "$source_unit" "$unit_path"; then
  install -m 644 "$source_unit" "$unit_path"
fi
systemctl daemon-reload
systemctl enable --now "$unit"
if [[ $listener == "127.0.0.1:$port" ]]; then
  systemctl restart "$unit"
fi
for ((attempt=0; attempt<20; attempt++)); do
  if [[ $(ss -H -ltn "sport = :$port" | awk '{print $4}') == "$proxy" ]] &&
    [[ $(curl --fail --silent --noproxy '*' --max-time 2 --header "Host: $host" \
      --output /dev/null --write-out '%{http_code}' "http://$proxy/api/tests") == 200 ]]; then
    echo "private relay $proxy -> Istio Service:80 verified"
    exit 0
  fi
  sleep 1
done
fail 'private gateway relay is not ready'
