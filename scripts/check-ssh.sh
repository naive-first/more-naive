#!/usr/bin/env bash
# Sourced by the two SSH tools so checks and connection options stay together.
set -euo pipefail
[[ ${MORE_NAIVE_ENV-} == prod ]] || { echo 'SSH requires explicit prod' >&2; exit 2; }
[[ ${SSH_USER-} =~ ^[a-z_][a-z0-9_-]*$ && ${SSH_EXPECTED_HOST-} =~ ^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$ ]] || {
  echo 'explicit OS user and expected hostname required' >&2; exit 2;
}
SSH_KEY_FILE=${SSH_KEY_FILE-}
case $SSH_KEY_FILE in '~/'*) SSH_KEY_FILE="$HOME/${SSH_KEY_FILE#'~/'}" ;; esac
[[ ${SSH_HOST-} =~ ^[A-Za-z0-9][A-Za-z0-9.:-]*$ && -f ${SSH_KEY_FILE-} ]] || {
  echo 'SSH target and existing private key path required' >&2; exit 2;
}
case $(uname -s) in
  Darwin) mode=$(stat -f %Lp "$SSH_KEY_FILE") ;;
  Linux) mode=$(stat -c %a "$SSH_KEY_FILE") ;;
  *) echo 'unsupported SSH client OS' >&2; exit 2 ;;
esac
[[ $mode == 600 || $mode == 400 ]] || { echo 'SSH key must be owner-only' >&2; exit 2; }
if [[ $SSH_HOST =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ || $SSH_HOST == *:* ]]; then
  addresses=$(printf '%s\n' "$SSH_HOST" | tr 'A-F' 'a-f')
else
  records=$(dig +time=5 +tries=1 +noall +answer A "$SSH_HOST" && dig +time=5 +tries=1 +noall +answer AAAA "$SSH_HOST")
  addresses=$(printf '%s\n' "$records" | awk '$4=="A" || $4=="AAAA" {print tolower($5)}')
fi
[[ -n $addresses ]] || { echo 'SSH hostname has no addresses' >&2; exit 2; }
while IFS= read -r address; do
  if [[ $address == *:* ]]; then
    [[ $address == fd7a:115c:a1e0:* ]] || { echo 'SSH target must be exclusively tailnet addresses' >&2; exit 2; }
  else
    printf '%s\n' "$address" | awk -F. 'NF==4 && $1==100 && $2>=64 && $2<=127 && $3>=0 && $3<=255 && $4>=0 && $4<=255 {exit 0} {exit 1}' || {
      echo 'SSH target must be exclusively tailnet addresses' >&2; exit 2;
    }
  fi
done <<< "$addresses"
SSH_COMMAND=(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 -i "$SSH_KEY_FILE" "$SSH_USER@$SSH_HOST")
identity=$("${SSH_COMMAND[@]}" 'id -un; hostname')
[[ $identity == "$SSH_USER"$'\n'"$SSH_EXPECTED_HOST" ]] || { echo 'remote user/hostname mismatch' >&2; exit 2; }
