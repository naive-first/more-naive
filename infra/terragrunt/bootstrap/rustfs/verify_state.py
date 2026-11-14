#!/usr/bin/env python3
"""Exercise a disposable RustFS backend with real Terraform and restricted IAM."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from verify_bootstrap import IMAGE, command, wait_health


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def main():
    with tempfile.TemporaryDirectory(prefix="more-naive-state-") as scratch:
        scratch = Path(scratch)
        data = scratch / "data"
        data.mkdir()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        name = "more-naive-state-" + secrets.token_hex(5)
        endpoint = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update({"RUSTFS_ENDPOINT": endpoint, "RUSTFS_BUCKET": "state-proof", "RUSTFS_REGION": "us-east-1",
                    "RUSTFS_ADMIN_ACCESS_KEY": secrets.token_hex(10), "RUSTFS_ADMIN_SECRET_KEY": secrets.token_hex(24),
                    "RUSTFS_STATE_ACCESS_KEY": secrets.token_hex(10), "RUSTFS_STATE_SECRET_KEY": secrets.token_hex(24),
                    "XDG_STATE_HOME": str(scratch / "profiles"), "TG_NO_COLOR": "true", "TG_NON_INTERACTIVE": "true",
                    "TF_CLI_ARGS": "-no-color", "AWS_EC2_METADATA_DISABLED": "true"})
        env_file = scratch / "docker.env"
        env_file.write_text("RUSTFS_ACCESS_KEY=" + env["RUSTFS_ADMIN_ACCESS_KEY"] + "\nRUSTFS_SECRET_KEY=" + env["RUSTFS_ADMIN_SECRET_KEY"] + "\nRUSTFS_OBS_LOGGER_LEVEL=error\n")
        env_file.chmod(0o600)
        command(["docker", "run", "--rm", "--user", "0", "--entrypoint", "sh", "-v", f"{data}:/data", IMAGE,
                 "-c", "chown 10001:10001 /data && chmod 700 /data"])
        command(["docker", "run", "-d", "--name", name, "--env-file", str(env_file), "-v", f"{data}:/data", "-p", f"127.0.0.1:{port}:9000", IMAGE, "/data"])
        try:
            wait_health(endpoint)
            unit = scratch / "unit-a"
            unit.mkdir()
            (unit / "terragrunt.hcl").write_text('include "state" { path = "' + str(ROOT / "infra/terragrunt/state.hcl") + '" }\n')
            (unit / "main.tf").write_text('terraform { required_version = "= 1.17.2" }\nresource "terraform_data" "proof" { input = "state-persisted" }\n')

            def state(action, **kwargs):
                args = [sys.executable, str(HERE / "state.py"), "--env", "prod", "--unit", "verify", action]
                return subprocess.run([*args, *kwargs.get("extra", [])], env=kwargs.get("env", env), cwd=kwargs.get("cwd", unit),
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            result = state("bootstrap")
            print(result.stdout)
            assert result.returncode == 0
            result = state("bootstrap")
            print(result.stdout)
            assert result.returncode == 0
            print("PASS 1: Terragrunt bucket bootstrap and idempotent rerun")
            admin = boto3.client("s3", endpoint_url=endpoint, region_name="us-east-1", aws_access_key_id=env["RUSTFS_ADMIN_ACCESS_KEY"],
                                 aws_secret_access_key=env["RUSTFS_ADMIN_SECRET_KEY"], config=Config(s3={"addressing_style": "path"}))
            try:
                admin.put_object(Bucket="state-proof", Key="sse-probe", Body=b"probe", ServerSideEncryption="AES256")
                print("SSE-S3 supported by this runtime")
            except ClientError as error:
                print("SSE-S3 unavailable without configured key management:", error.response["Error"]["Code"])
            policy_file = scratch / "policy.json"
            policy_file.write_text(command([sys.executable, str(HERE / "state-policy.py"), "state-proof"]))
            command(["docker", "cp", str(policy_file), name + ":/tmp/state-policy.json"])
            # rc 인증과 IAM 생성 응답에는 비밀값이 포함될 수 있어 출력하지 않는다.
            for args in [["alias", "set", "local", "http://127.0.0.1:9000", env["RUSTFS_ADMIN_ACCESS_KEY"], env["RUSTFS_ADMIN_SECRET_KEY"]],
                         ["admin", "user", "add", "local", env["RUSTFS_STATE_ACCESS_KEY"], env["RUSTFS_STATE_SECRET_KEY"]],
                         ["admin", "policy", "create", "local", "terraform-state", "/tmp/state-policy.json"],
                         ["admin", "policy", "attach", "local", "terraform-state", "--user", env["RUSTFS_STATE_ACCESS_KEY"]]]:
                rc = subprocess.run(["docker", "exec", name, "rc", *args], capture_output=True)
                assert rc.returncode == 0, "RustFS IAM setup failed (credentials withheld)"
            for action, extra in [("init", ["-input=false"]), ("apply", ["-input=false", "-auto-approve"])]:
                result = state(action, extra=extra)
                print(result.stdout)
                assert result.returncode == 0
            print("PASS 2: restricted credentials write state with native lock")
            client = boto3.client("s3", endpoint_url=endpoint, region_name="us-east-1", aws_access_key_id=env["RUSTFS_STATE_ACCESS_KEY"],
                                  aws_secret_access_key=env["RUSTFS_STATE_SECRET_KEY"], config=Config(s3={"addressing_style": "path"}))
            assert client.get_object(Bucket="state-proof", Key="more-naive/prod/verify/terraform.tfstate")["ContentLength"] > 0
            print("PASS 3: remote state object exists and is readable")
            for bucket, key in [("state-proof", "unrelated/terraform.tfstate"), ("other-proof", "more-naive/prod/verify/terraform.tfstate")]:
                try:
                    client.put_object(Bucket=bucket, Key=key, Body=b"forbidden")
                    raise AssertionError("out-of-scope write unexpectedly allowed")
                except ClientError as error:
                    assert error.response["ResponseMetadata"]["HTTPStatusCode"] == 403
            print("PASS 4: other prefix and bucket writes denied")
            second = scratch / "unit-b"
            second.mkdir()
            for file in ["terragrunt.hcl", "main.tf"]:
                (second / file).write_text((unit / file).read_text())
            result = state("init", cwd=second, extra=["-input=false"])
            print(result.stdout)
            assert result.returncode == 0
            result = state("plan", cwd=second, extra=["-input=false"])
            print(result.stdout)
            assert result.returncode == 0 and "No changes." in result.stdout
            print("PASS 5: a fresh working directory reloads remote state")
            for bad_env in [{**env, "RUSTFS_STATE_SECRET_KEY": "invalid-state-secret"}, {**env, "RUSTFS_ENDPOINT": ""}]:
                result = state("plan", env=bad_env, extra=["-input=false"])
                assert result.returncode != 0
            print("PASS 6: invalid credentials and missing endpoint fail closed")
        finally:
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            command(["docker", "run", "--rm", "--user", "0", "--entrypoint", "sh", "-v", f"{data}:/data", IMAGE,
                     "-c", "rm -rf /data/* /data/.[!.]* /data/..?*; chmod 777 /data"])
    print("6 backend checks passed; no prod resource changed")


if __name__ == "__main__":
    main()
