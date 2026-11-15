#!/usr/bin/env bash
set -euo pipefail
[[ ${MORE_NAIVE_ENV-} == prod ]] || { echo 'state requires explicit prod' >&2; exit 2; }
endpoint=${RUSTFS_ENDPOINT-}
https='^https://([A-Za-z0-9.-]+|\[[0-9a-fA-F:]+\])(:[0-9]+)?(/[^?#[:space:]]*)?$'
loopback='^http://(127\.0\.0\.1|localhost|\[::1\])(:[0-9]+)?(/[^?#[:space:]]*)?$'
[[ $endpoint =~ $https || $endpoint =~ $loopback ]] || {
  echo 'backend requires HTTPS or loopback HTTP without userinfo/query/fragment' >&2; exit 2;
}
[[ -n ${RUSTFS_BUCKET-} && -n ${RUSTFS_REGION-} ]] || { echo 'backend bucket/region required' >&2; exit 2; }
credential=${RUSTFS_CREDENTIALS_FILE:?existing private credential profile required}
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
[[ $credential == /* && $credential != "$repo/"* && -f $credential ]] || {
  echo 'credential profile must exist at an absolute path outside checkout' >&2; exit 2;
}
case $(uname -s) in
  Darwin) mode=$(stat -f %Lp "$credential"); owner=$(stat -f %u "$credential") ;;
  Linux) mode=$(stat -c %a "$credential"); owner=$(stat -c %u "$credential") ;;
  *) echo 'unsupported credential host OS' >&2; exit 2 ;;
esac
[[ $mode == 600 && $owner == "$(id -u)" ]] || {
  echo 'credential profile must be owned by this user with mode 0600' >&2; exit 2;
}
