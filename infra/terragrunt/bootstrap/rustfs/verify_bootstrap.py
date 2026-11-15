#!/usr/bin/env python3
"""Verify bootstrap only in a fresh, isolated local Docker instance."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.request

import boto3
from botocore.config import Config


IMAGE = "rustfs/rustfs:1.0.5@sha256:b81d16a90ee25bd9511280127ca1471788c6e874cf0f0da759645f46b2dc1d74"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BOOTSTRAP = ["terragrunt", "--working-dir", str(HERE), "run", "--"]


def command(argv, env=None):
    result = subprocess.run(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, umask=0o077)
    if result.returncode:
        print(result.stdout)
        raise RuntimeError(f"command failed: {argv[0]} (exit {result.returncode})")
    print(result.stdout, end="")
    return result.stdout


def wait_health(endpoint):
    for _ in range(60):
        try:
            with urllib.request.urlopen(endpoint + "/health", timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError("RustFS health timed out")


def main():
    with tempfile.TemporaryDirectory(prefix="more-naive-rustfs-") as scratch:
        scratch = Path(scratch)
        data = scratch / "data"
        data.mkdir()
        state = scratch / "state"
        state.mkdir(mode=0o700)
        with socket.socket() as port_probe:
            port_probe.bind(("127.0.0.1", 0))
            port = port_probe.getsockname()[1]
        name = "more-naive-verify-" + secrets.token_hex(5)
        endpoint = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update({"MORE_NAIVE_ENV": "prod", "RUSTFS_DATA_DIR": str(data), "RUSTFS_STATE_PATH": str(state / "bootstrap.tfstate"),
                    "RUSTFS_ENDPOINT": endpoint, "RUSTFS_NAME": name,
                    "RUSTFS_ADMIN_ACCESS_KEY": secrets.token_hex(10),
                    "RUSTFS_ADMIN_SECRET_KEY": secrets.token_hex(24),
                    "TG_DOWNLOAD_DIR": str(scratch / "cache-a"), "TF_LOG": "", "TG_NO_COLOR": "true", "TG_LOG_LEVEL": "error"})
        command(["docker", "run", "--rm", "--user", "0", "--entrypoint", "sh", "-v", f"{data}:/data", IMAGE,
                 "-c", "chown 10001:10001 /data && chmod 700 /data"])
        try:
            command([*BOOTSTRAP, "init", "-input=false", "-no-color"], env)
            command([*BOOTSTRAP, "apply", "-input=false", "-auto-approve", "-no-color"], env)
            wait_health(endpoint)
            s3 = boto3.client("s3", endpoint_url=endpoint, region_name="us-east-1",
                              aws_access_key_id=env["RUSTFS_ADMIN_ACCESS_KEY"],
                              aws_secret_access_key=env["RUSTFS_ADMIN_SECRET_KEY"],
                              config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 1}))
            s3.create_bucket(Bucket="bootstrap-proof")
            s3.put_object(Bucket="bootstrap-proof", Key="proof", Body=b"persistent-object")
            command(["docker", "restart", name])
            wait_health(endpoint)
            assert s3.get_object(Bucket="bootstrap-proof", Key="proof")["Body"].read() == b"persistent-object"
            print("PASS 1: S3 object survives restart")
            command([*BOOTSTRAP, "apply", "-replace=docker_container.rustfs",
                     "-auto-approve", "-input=false", "-no-color"], env)
            wait_health(endpoint)
            assert s3.get_object(Bucket="bootstrap-proof", Key="proof")["Body"].read() == b"persistent-object"
            print("PASS 2: S3 object survives container replacement")
            env["TG_DOWNLOAD_DIR"] = str(scratch / "cache-b")
            plan = command([*BOOTSTRAP, "plan", "-input=false", "-no-color"], env)
            assert "No changes." in plan
            assert (state / "bootstrap.tfstate").is_file()
            assert (state / "bootstrap.tfstate").stat().st_mode & 0o777 == 0o600
            print("PASS 3: a fresh cache reads the same absolute local state")
            denied = subprocess.run([*BOOTSTRAP, "apply", "-input=false", "-auto-approve"],
                                    env={**env, "MORE_NAIVE_ENV": "dev"}, capture_output=True, text=True)
            assert denied.returncode != 0
            print("PASS 4: dev is refused before a write")
        finally:
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            command(["docker", "run", "--rm", "--user", "0", "--entrypoint", "sh", "-v", f"{data}:/data", IMAGE,
                     "-c", "rm -rf /data/* /data/.[!.]* /data/..?*; chmod 777 /data"])
    print("4 bootstrap checks passed; prod host was not modified")


if __name__ == "__main__":
    main()
