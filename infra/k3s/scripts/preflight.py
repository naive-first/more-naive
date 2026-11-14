#!/usr/bin/env python3
"""명시한 prod tailnet 노드의 신원과 설치 선행 조건만 확인한다."""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

VERSION = "v1.35.10+k3s1"


def tailnet_host(host):
    try:
        addresses = socket.getaddrinfo(host, 22, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise ValueError("SSH hostname cannot be resolved") from error
    networks = [ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48")]
    if not addresses or any(
        not any(ipaddress.ip_address(item[4][0]) in network for network in networks)
        for item in addresses
    ):
        raise ValueError("SSH target must resolve exclusively to tailnet addresses")


def execute(args):
    if args.environment != "prod":
        raise ValueError("only explicit prod is supported")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,62}", args.node):
        raise ValueError("invalid expected node hostname")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", args.user):
        raise ValueError("invalid SSH OS user")
    key = Path(args.key_file).expanduser()
    if not key.is_file() or key.stat().st_mode & 0o077:
        raise ValueError("SSH private key requires an existing owner-only file")
    token = os.environ.get("K3S_TOKEN", "")
    if not token or any(char in token for char in "\r\n\x00"):
        raise ValueError("K3S_TOKEN is required and must be one line")
    server = os.environ.get("K3S_SERVER_URL", "")
    if args.role == "agent" and not re.fullmatch(r"https://[A-Za-z0-9.:[\]-]+:6443", server):
        raise ValueError("agent requires K3S_SERVER_URL=https://<private-server>:6443")
    tailnet_host(args.host)
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes",
           "-o", "ConnectTimeout=10", "-i", str(key), f"{args.user}@{args.host}"]
    probe = subprocess.run(
        [*ssh, "id -un; hostname; sudo -n true && tailscale status --json"],
        capture_output=True, text=True, timeout=30, check=True,
    )
    user, node, status = probe.stdout.split("\n", 2)
    if user != args.user or node != args.node or json.loads(status).get("BackendState") != "Running":
        raise ValueError("remote user/hostname/Tailscale status does not match")
    print(f"verified prod node {node}; role={args.role}; version={VERSION}")
    print("preflight passed; installation is managed by Terraform")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--role", required=True, choices=["server", "agent"])
    try:
        execute(parser.parse_args())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"bootstrap stopped: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
