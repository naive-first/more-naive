#!/usr/bin/env bash
set -euo pipefail
apply=false; reviewed=false
for arg in "$@"; do
  case $arg in --apply) apply=true;; --policy-reviewed) reviewed=true;; *) echo 'use --apply --policy-reviewed after preflight' >&2; exit 2;; esac
done
fail() { echo "$1" >&2; exit 2; }
[[ ${MORE_NAIVE_ENV-} == prod && ${TAILSCALE_EXPECTED_HOST-} == "$(hostname)" ]] || fail 'explicit prod and matching console hostname required'
[[ ${TAILSCALE_NODE_NAME-} =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]] || fail 'invalid node name'
[[ ${SSH_USER-} =~ ^[a-z_][a-z0-9_-]*$ ]] && id "$SSH_USER" >/dev/null 2>&1 || fail 'existing OS user required'
[[ -z ${TAILSCALE_TAGS-} || $TAILSCALE_TAGS =~ ^tag:[a-zA-Z0-9-]+(,tag:[a-zA-Z0-9-]+)*$ ]] || fail 'invalid tags'
join_key=${TAILSCALE_AUTH_KEY-}; unset TAILSCALE_AUTH_KEY
if ! command -v tailscale >/dev/null; then
  if ! $apply; then echo 'NOT_RUN: new node needs pinned Tailscale 1.104.7; preflight only'; exit 0; fi
  [[ $(id -u) == 0 && $(uname -s) == Linux && $(uname -m) == x86_64 ]] || fail 'first installation supports root on Linux amd64 only'
  [[ $reviewed == true && -n $join_key ]] || fail 'reviewed policy and external join key required before installation'
  [[ ! -e /var/lib/tailscale/tailscaled.state && ! -e /etc/systemd/system/tailscaled.service ]] || fail 'existing daemon state/service requires review'
  [[ ! -e /etc/systemd/system/more-naive-tailscaled.service ]] || fail 'existing managed service requires review'
  for tool in curl sha256sum tar install systemctl jq; do command -v "$tool" >/dev/null || fail "required command missing: $tool"; done
  temporary=$(mktemp -d); trap 'rm -rf "$temporary"' EXIT
  curl --fail --silent --show-error --location --max-time 60 https://pkgs.tailscale.com/stable/tailscale_1.104.7_amd64.tgz -o "$temporary/archive.tgz"
  printf '%s  %s\n' e56693ff74a64f2591b7e819c280635a100aae1ddfb0ef058fcd052b7cd8d16c "$temporary/archive.tgz" | sha256sum --check --status || fail 'official static archive checksum mismatch'
  tar -xzf "$temporary/archive.tgz" -C "$temporary" tailscale_1.104.7_amd64/tailscale tailscale_1.104.7_amd64/tailscaled
  install -m 755 "$temporary/tailscale_1.104.7_amd64/tailscale" /usr/local/bin/tailscale
  install -m 755 "$temporary/tailscale_1.104.7_amd64/tailscaled" /usr/local/sbin/tailscaled
  install -m 644 "$(dirname "${BASH_SOURCE[0]}")/more-naive-tailscaled.service" /etc/systemd/system/more-naive-tailscaled.service
  systemctl daemon-reload
  systemctl enable --now more-naive-tailscaled.service
  rm -rf "$temporary"; trap - EXIT
fi
status=$(tailscale status --json)
if [[ $(jq -er '.BackendState' <<< "$status") == Running ]]; then
  [[ $(jq -er '.Self.HostName' <<< "$status") == "$TAILSCALE_NODE_NAME" ]] || fail 'existing node name differs; enrollment unchanged'
  echo 'Existing node Running; enrollment and SSH settings unchanged'; exit 0
fi
[[ -z $(jq -r '.Self.ID // empty' <<< "$status") ]] || fail 'existing enrollment is not Running; diagnose before rejoining'
if ! $apply; then echo 'NOT_RUN: registration requires explicit --apply and reviewed policy'; exit 0; fi
[[ $reviewed == true && -n $join_key ]] || fail 'reviewed policy and external join key required'
version=$(tailscale version); [[ ${version%%$'\n'*} == 1.104.7 ]] || fail 'new node binary differs from pinned version'
umask 077
temporary=$(mktemp -d); trap 'rm -rf "$temporary"' EXIT
printf '%s' "$join_key" > "$temporary/join-key"; unset join_key
tailscale up --ssh "--hostname=$TAILSCALE_NODE_NAME" "--advertise-tags=${TAILSCALE_TAGS-}" "--auth-key=file:$temporary/join-key"
echo 'Registration completed; operator SSH allow/deny and restart checks remain required'
