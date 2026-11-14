#!/usr/bin/env python3
"""지정한 tailnet 노드만 설치하고 토큰은 SSH stdin으로 전달한다."""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys

VERSION = "v1.35.10+k3s1"
REMOTE = r'''
import hashlib,json,os,pathlib,subprocess,socket,sys,urllib.request
p=json.load(sys.stdin)
if socket.gethostname()!=p['node']: raise SystemExit('remote hostname mismatch')
if os.geteuid()!=0: raise SystemExit('sudo root required')
directory=pathlib.Path('/etc/rancher/k3s')
config=directory/'config.yaml'
token=directory/'more-naive-token'
text='node-name: '+json.dumps(p['node'])+'\nwrite-kubeconfig-mode: "0600"\n'
text+='token-file: /etc/rancher/k3s/more-naive-token\n'
if p['role']=='server': text+='disable:\n  - traefik\n  - servicelb\n'
else: text+='server: '+json.dumps(p['server'])+'\n'
if pathlib.Path('/usr/local/bin/k3s').exists():
 version=subprocess.check_output(['/usr/local/bin/k3s','--version'],text=True).splitlines()[0]
 if p['version'] not in version: raise SystemExit('existing k3s version differs; explicit upgrade required')
 if not config.exists() or config.read_text()!=text: raise SystemExit('existing config differs; review before changes')
 if not token.exists() or token.read_text()!=p['token']: raise SystemExit('existing token differs; review before changes')
 unit='k3s' if p['role']=='server' else 'k3s-agent'
 subprocess.run(['systemctl','is-active','--quiet',unit],check=True)
 print('existing pinned installation active; no changes')
 raise SystemExit(0)
if config.exists(): raise SystemExit('unowned k3s config exists; refusing overwrite')
url='https://raw.githubusercontent.com/k3s-io/k3s/v1.35.10%2Bk3s1/install.sh'
installer=urllib.request.urlopen(url,timeout=60).read()
if hashlib.sha256(installer).hexdigest()!='8598e002e61d658fed7b7542fc6d2c66d8da6eae69e088830105d2ee1ffb6d91':
 raise SystemExit('installer checksum mismatch')
os.umask(0o077)
directory.mkdir(parents=True,exist_ok=True)
config.write_text(text);config.chmod(0o600)
token.write_text(p['token']);token.chmod(0o600)
env=os.environ.copy();env['INSTALL_K3S_VERSION']=p['version'];env['INSTALL_K3S_EXEC']=p['role']
subprocess.run(['sh','-s','-'],input=installer,env=env,check=True)
print('pinned installation completed')
'''


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
    if not token or "\n" in token:
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
    if not args.apply:
        print("preflight only; pass --apply to install")
        return
    payload = {"node": args.node, "role": args.role, "token": token, "server": server, "version": VERSION}
    subprocess.run([*ssh, shlex.join(["sudo", "-n", "python3", "-c", REMOTE])],
                   input=json.dumps(payload), text=True, timeout=600, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--role", required=True, choices=["server", "agent"])
    parser.add_argument("--apply", action="store_true")
    try:
        execute(parser.parse_args())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"bootstrap stopped: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
