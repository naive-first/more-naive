#!/usr/bin/env python3
"""Run the independently stored RustFS bootstrap after the root env loader."""
import argparse
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", required=True, choices=["prod"])
    parser.add_argument("--allow-destroy", action="store_true")
    parser.add_argument("command", choices=["init", "validate", "plan", "apply", "destroy"])
    args, extra = parser.parse_known_args()
    if args.command == "destroy" and not args.allow_destroy:
        parser.error("destroy requires --allow-destroy; persistent data is retained")
    root = Path(__file__).resolve().parents[4]
    for key in ["RUSTFS_STATE_PATH", "RUSTFS_DATA_DIR"]:
        value = os.environ.get(key, "")
        target = Path(value)
        if not target.is_absolute() or target.is_relative_to(root) or ".terragrunt-cache" in target.parts:
            parser.error(f"{key} must be an absolute path outside this checkout and cache")
    data = Path(os.environ["RUSTFS_DATA_DIR"])
    if not data.is_dir() or data.stat().st_uid != 10001:
        parser.error("RUSTFS_DATA_DIR must exist and be owned by UID 10001 on the local Docker host")
    endpoint = urlsplit(os.environ.get("RUSTFS_ENDPOINT", ""))
    if endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or endpoint.path not in ["", "/"]:
        parser.error("bootstrap requires a loopback http://127.0.0.1:PORT endpoint; use a private TLS tunnel for remote clients")
    os.environ["RUSTFS_API_PORT"] = str(endpoint.port or 9000)
    if not all(os.environ.get(key) for key in ["TF_VAR_admin_access_key", "TF_VAR_admin_secret_key"]):
        parser.error("administrator credentials are required through scripts/env.py rustfs-bootstrap")
    state = Path(os.environ["RUSTFS_STATE_PATH"])
    state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if state.parent.stat().st_mode & 0o077:
        parser.error("bootstrap state parent permissions must be 0700")
    os.umask(0o077)
    os.environ["TG_TF_PATH"] = "terraform"
    os.environ["TF_IN_AUTOMATION"] = "true"
    return subprocess.call(["terragrunt", "run", "--", args.command, *extra], cwd=Path(__file__).parent)


if __name__ == "__main__":
    raise SystemExit(main())
