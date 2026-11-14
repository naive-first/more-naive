#!/usr/bin/env python3
"""Verify real state lock contention, outage failure, and persisted remote state."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
from urllib.parse import urlsplit

from botocore.exceptions import ClientError

from verify_bootstrap import EXECUTABLE, IMAGE, command, wait_health
from verify_state import ROOT, main


def check_lock(unit, second, env, name, client, state):
    bucket = env["RUSTFS_BUCKET"]
    key = "more-naive/prod/verify/terraform.tfstate.tflock"
    client.put_object(Bucket=bucket, Key=key, Body=b"conditional-write-probe", IfNoneMatch="*")
    try:
        client.put_object(Bucket=bucket, Key=key, Body=b"duplicate", IfNoneMatch="*")
        raise AssertionError("conditional write overwrote an existing key")
    except ClientError as error:
        assert error.response["ResponseMetadata"]["HTTPStatusCode"] == 412
    finally:
        client.delete_object(Bucket=bucket, Key=key)
    print("PASS 7: conditional creation refuses an existing lock key with 412")
    marker = unit.parent / "lock-held"
    code = f"from pathlib import Path;import time;Path({str(marker)!r}).touch();time.sleep(12)"
    wait_command = shlex.join([sys.executable, "-c", code])
    extra = '\nresource "terraform_data" "hold" {\n  provisioner "local-exec" {\n    command = ' + json.dumps(wait_command) + '\n  }\n}\n'
    for directory in [unit, second]:
        with (directory / "main.tf").open("a") as output:
            output.write(extra)
    args = [str(EXECUTABLE), "--repo-root", str(ROOT), "--env", "prod", "--target", "state", "--unit", "verify", "apply", "-input=false", "-auto-approve"]
    first = subprocess.Popen(args, env=env, cwd=unit, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(100):
            if marker.exists():
                break
            if first.poll() is not None:
                print(first.communicate()[0])
                raise AssertionError("first apply ended before holding the lock")
            time.sleep(0.1)
        assert marker.exists(), "first apply never reached the locked provisioner"
        collision = state("plan", cwd=second, extra=["-input=false", "-lock-timeout=1s"])
        print(collision.stdout)
        assert collision.returncode != 0 and "Error acquiring the state lock" in collision.stdout
        print("PASS 8: concurrent Terraform plan fails while first apply holds the lock")
        print(first.communicate(timeout=40)[0])
        assert first.returncode == 0
    finally:
        if first.poll() is None:
            first.terminate()
            first.communicate(timeout=20)
    unlocked = state("plan", cwd=second, extra=["-input=false"])
    print(unlocked.stdout)
    assert unlocked.returncode == 0 and "No changes." in unlocked.stdout
    print("PASS 9: normal completion releases the lock; the next plan succeeds")
    command(["docker", "stop", name])
    failed = state("plan", cwd=second, extra=["-input=false", "-lock-timeout=1s"])
    print(failed.stdout)
    assert failed.returncode != 0
    local_states = [file for file in second.rglob("terraform.tfstate") if file.parent.name != ".terraform"]
    assert not local_states, "a local fallback resource state unexpectedly appeared"
    print("PASS 10: offline RustFS fails instead of creating local state")
    command(["docker", "rm", name])
    scratch = unit.parent
    port = urlsplit(env["RUSTFS_ENDPOINT"]).port
    command(["docker", "run", "-d", "--name", name, "--env-file", str(scratch / "docker.env"),
             "-v", f"{scratch / 'data'}:/data", "-p", f"127.0.0.1:{port}:9000", IMAGE, "/data"])
    wait_health(env["RUSTFS_ENDPOINT"])
    recovered = state("plan", cwd=second, extra=["-input=false"])
    print(recovered.stdout)
    assert recovered.returncode == 0 and "No changes." in recovered.stdout
    assert client.get_object(Bucket=bucket, Key="more-naive/prod/verify/terraform.tfstate")["ContentLength"] > 0
    print("PASS 11: replacement container reloads the same persisted remote state")


if __name__ == "__main__":
    main(after_state=check_lock)
    print("5 additional lock/outage checks passed (11 backend checks total)")
