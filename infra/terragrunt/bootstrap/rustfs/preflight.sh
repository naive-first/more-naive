#!/bin/sh
# Run before Terraform opens local state or accesses the Docker provider.
set -eu
umask 077
[ "${MORE_NAIVE_ENV:-}" = prod ] || { echo 'bootstrap requires explicit prod' >&2; exit 2; }
repo=$1
action=$2
if [ "$action" = destroy ] && [ "${RUSTFS_ALLOW_DESTROY:-}" != true ]; then
  echo 'bootstrap destroy requires RUSTFS_ALLOW_DESTROY=true; retain host data' >&2
  exit 2
fi
case "$RUSTFS_ENDPOINT" in
  http://127.0.0.1:[0-9]*) ;;
  *) echo 'bootstrap requires http://127.0.0.1:PORT' >&2; exit 2 ;;
esac
port=${RUSTFS_ENDPOINT#http://127.0.0.1:}
case "$port" in *[!0-9]*|'') exit 2 ;; esac
[ "$port" -ge 1024 ] && [ "$port" -lt 65535 ]
for target in "$RUSTFS_DATA_DIR" "$RUSTFS_STATE_PATH"; do
  case "$target" in /*) ;; *) echo 'persistent paths must be absolute' >&2; exit 2 ;; esac
  resolved=$(realpath -m "$target")
  case "$resolved/" in "$repo/"*|*/.terragrunt-cache/*) echo 'persistent paths must be outside checkout/cache' >&2; exit 2 ;; esac
done
[ -d "$RUSTFS_DATA_DIR" ] && [ "$(stat -Lc %u "$RUSTFS_DATA_DIR")" = 10001 ] || {
  echo 'data directory must exist and be owned by UID 10001' >&2; exit 2;
}
parent=$(dirname "$RUSTFS_STATE_PATH")
mkdir -p "$parent"
[ "$(stat -Lc %a "$parent")" = 700 ] && [ "$(stat -Lc %u "$parent")" = "$(id -u)" ] || {
  echo 'state directory must be owned by the current user with mode 0700' >&2; exit 2;
}
