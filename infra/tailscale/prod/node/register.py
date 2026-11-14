#!/usr/bin/env python3
"""Prepare a new Linux amd64 node from its trusted console; preserve existing enrollment."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import urllib.request

VERSION = "1.104.7"
CHECKSUM = "e56693ff74a64f2591b7e819c280635a100aae1ddfb0ef058fcd052b7cd8d16c"


def register(args):
    if args.environment != "prod" or args.expected_host != socket.gethostname():
        raise ValueError("explicit prod and matching console hostname are required")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", args.node_name):
        raise ValueError("invalid node name")
    pwd.getpwnam(args.os_user)
    if any(not re.fullmatch(r"tag:[a-zA-Z0-9-]+", tag) for tag in args.tag):
        raise ValueError("invalid tag")
    if not shutil.which("tailscale"):
        if not args.apply:
            print(f"NOT_RUN: new node needs pinned Tailscale {VERSION}; preflight only")
            return
        if os.geteuid() != 0 or platform.system() != "Linux" or platform.machine() != "x86_64":
            raise ValueError("first installation supports root on Linux amd64 only")
        if not args.policy_reviewed or not os.environ.get("TAILSCALE_AUTH_KEY"):
            raise ValueError("reviewed network/SSH policy and external join key required before installation")
        if Path("/var/lib/tailscale/tailscaled.state").exists() or Path("/etc/systemd/system/tailscaled.service").exists():
            raise ValueError("existing daemon state/service requires operator review")
        unit = Path("/etc/systemd/system/more-naive-tailscaled.service")
        if unit.exists():
            raise ValueError("existing managed service requires review")
        archive = urllib.request.urlopen(f"https://pkgs.tailscale.com/stable/tailscale_{VERSION}_amd64.tgz", timeout=60).read()
        if hashlib.sha256(archive).hexdigest() != CHECKSUM:
            raise ValueError("official static archive checksum mismatch")
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as source:
            for name, destination in [("tailscale", "/usr/local/bin/tailscale"), ("tailscaled", "/usr/local/sbin/tailscaled")]:
                target = Path(destination)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.extractfile(f"tailscale_{VERSION}_amd64/{name}").read())
                target.chmod(0o755)
        unit.write_text("[Unit]\nDescription=More Naive Tailscale\nAfter=network-online.target\nWants=network-online.target\n[Service]\nExecStart=/usr/local/sbin/tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/run/tailscale/tailscaled.sock\nRuntimeDirectory=tailscale\nStateDirectory=tailscale\nRestart=on-failure\n[Install]\nWantedBy=multi-user.target\n")
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", "--now", "more-naive-tailscaled.service"], check=True)
    status = json.loads(subprocess.check_output(["tailscale", "status", "--json"], text=True))
    if status.get("BackendState") == "Running":
        if status.get("Self", {}).get("HostName") != args.node_name:
            raise ValueError("existing node name differs; enrollment unchanged")
        print("Existing node Running; enrollment and SSH settings unchanged")
        return
    if status.get("Self", {}).get("ID"):
        raise ValueError("existing enrollment is not Running; operator must diagnose before rejoining")
    if not args.apply:
        print("NOT_RUN: registration requires explicit --apply and reviewed policy")
        return
    if not args.policy_reviewed or not os.environ.get("TAILSCALE_AUTH_KEY"):
        raise ValueError("reviewed policy and external TAILSCALE_AUTH_KEY required")
    if subprocess.check_output(["tailscale", "version"], text=True).splitlines()[0] != VERSION:
        raise ValueError("new node binary version differs from the pinned version")
    with tempfile.TemporaryDirectory(prefix="more-naive-tailnet-") as temporary:
        key_file = Path(temporary) / "join-key"
        key_file.write_text(os.environ["TAILSCALE_AUTH_KEY"])
        key_file.chmod(0o600)
        subprocess.run(["tailscale", "up", "--ssh", "--hostname=" + args.node_name,
                        "--advertise-tags=" + ",".join(args.tag), "--auth-key=file:" + str(key_file)], check=True)
    print("Registration command completed; operator SSH allow/deny and restart checks remain required")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--node-name", required=True)
    parser.add_argument("--os-user", required=True)
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--policy-reviewed", action="store_true")
    parser.add_argument("--apply", action="store_true")
    try:
        register(parser.parse_args())
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"registration stopped: {type(error).__name__}\n")


if __name__ == "__main__":
    main()
