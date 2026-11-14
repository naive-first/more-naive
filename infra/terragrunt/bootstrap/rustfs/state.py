#!/usr/bin/env python3
"""Run a prod unit using an isolated RustFS backend credential profile."""
import argparse
import configparser
import os
from pathlib import Path
import subprocess
import hashlib
import tempfile
from urllib.parse import urlsplit


def run(unit, action, extra, administrator=False):
    endpoint = urlsplit(os.environ.get("RUSTFS_ENDPOINT", ""))
    if endpoint.scheme not in ["http", "https"] or not endpoint.hostname or endpoint.username or endpoint.password:
        raise ValueError("RUSTFS_ENDPOINT must be an explicit http(s) URL without credentials")
    if endpoint.scheme == "http" and endpoint.hostname not in ["localhost", "127.0.0.1", "::1"]:
        raise ValueError("HTTP backend is allowed only on loopback; use a private TLS endpoint/tunnel")
    if not os.environ.get("RUSTFS_BUCKET") or not os.environ.get("RUSTFS_REGION"):
        raise ValueError("RUSTFS_BUCKET and RUSTFS_REGION are required")
    prefix = "RUSTFS_ADMIN" if administrator else "RUSTFS_STATE"
    access = os.environ.get(prefix + "_ACCESS_KEY")
    secret = os.environ.get(prefix + "_SECRET_KEY")
    if not access or not secret:
        raise ValueError(f"{prefix} credentials are required; no fallback is allowed")
    # backend metadata의 인증 파일 경로가 매 실행마다 바뀌면 재초기화가 필요해진다.
    directory = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "more-naive/rustfs"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.stat().st_mode & 0o077:
        raise ValueError("RustFS credential directory must have mode 0700")
    identity = hashlib.sha256((os.environ["RUSTFS_ENDPOINT"] + os.environ["RUSTFS_BUCKET"]).encode()).hexdigest()[:16]
    credentials = directory / (identity + ".credentials")
    config = configparser.ConfigParser(interpolation=None)
    config["more-naive-state"] = {"aws_access_key_id": access, "aws_secret_access_key": secret}
    # Terragrunt 1.2.2는 이 경로를 shared config로 읽고 Terraform은 credentials로 읽는다.
    config["profile more-naive-state"] = dict(config["more-naive-state"])
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as output:
        config.write(output)
        temporary = output.name
    os.replace(temporary, credentials)
    env = {key: value for key, value in os.environ.items() if not key.startswith("AWS_")}
    env.update({"RUSTFS_CREDENTIALS_FILE": str(credentials), "RUSTFS_STATE_UNIT": unit,
                "TG_TF_PATH": "terraform", "TF_IN_AUTOMATION": "true", "AWS_EC2_METADATA_DISABLED": "true"})
    argv = ["terragrunt", "backend", "bootstrap"] if administrator else ["terragrunt", "run", "--", action]
    return subprocess.call([*argv, *extra], env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", required=True, choices=["prod"])
    parser.add_argument("--unit", required=True, choices=["network", "compute", "verify"])
    parser.add_argument("action", choices=["bootstrap", "init", "validate", "plan", "apply", "output"])
    args, extra = parser.parse_known_args()
    try:
        return run(args.unit, args.action, extra, args.action == "bootstrap")
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
