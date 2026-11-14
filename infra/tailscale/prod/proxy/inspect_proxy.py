#!/usr/bin/env python3
"""Read a confirmed proxy's non-secret status without changing Serve or network settings."""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import shlex
import socket
import subprocess
from urllib.parse import urlsplit

REMOTE = r'''
import ipaddress,json,pwd,os,socket,subprocess,sys,urllib.request,urllib.error,urllib.parse
p=json.load(sys.stdin)
if socket.gethostname()!=p['expected_host'] or pwd.getpwuid(os.getuid()).pw_name!=p['user']:
 raise SystemExit('remote hostname/user mismatch')
def read(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=20)
 return r.stdout if r.returncode==0 else None
status=read(['tailscale','status','--json'])
status=json.loads(status) if status else {}
serve=read(['tailscale','serve','status','--json'])
serve=json.loads(serve) if serve else {}
out={'hostname':socket.gethostname(),'user':p['user'],'tailscale_state':status.get('BackendState'),
 'dns_name':status.get('Self',{}).get('DNSName'),'tailnet_ips':status.get('Self',{}).get('TailscaleIPs',[]),
 'serve_tcp_ports':sorted(serve.get('TCP',{})),'serve_web_hosts':sorted(serve.get('Web',{})),
 'sudo_noninteractive':subprocess.run(['sudo','-n','true'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0}
if p['upstream']:
 u=urllib.parse.urlsplit(p['upstream'])
 addresses=socket.getaddrinfo(u.hostname,u.port or (443 if u.scheme=='https' else 80),type=socket.SOCK_STREAM)
 if not addresses or any(ipaddress.ip_address(a[4][0]).is_global for a in addresses):
  raise SystemExit('upstream must resolve exclusively to private addresses from this VM')
 try:
  request=urllib.request.Request(p['upstream'],headers={'Host':p['gateway_host']},method='GET')
  class NoRedirect(urllib.request.HTTPRedirectHandler):
   def redirect_request(self,*args,**kwargs): return None
  with urllib.request.build_opener(NoRedirect).open(request,timeout=10) as response: out['upstream_status']=response.status
 except urllib.error.HTTPError as error: out['upstream_status']=error.code
else: out['upstream_status']='NOT_RUN: actual private upstream not supplied'
print(json.dumps(out,indent=2))
'''


def inspect(args):
    if args.environment != "prod" or not re.fullmatch(r"[a-z_][a-z0-9_-]*", args.user):
        raise ValueError("explicit prod and valid OS user are required")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}", args.expected_host):
        raise ValueError("confirmed remote hostname is required")
    key = Path(args.key_file).expanduser()
    if not key.is_file() or key.stat().st_mode & 0o077:
        raise ValueError("existing owner-only private key required")
    addresses = socket.getaddrinfo(args.host, 22, type=socket.SOCK_STREAM)
    networks = [ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48")]
    if not addresses or any(not any(ipaddress.ip_address(item[4][0]) in net for net in networks) for item in addresses):
        raise ValueError("SSH target must resolve exclusively to tailnet addresses")
    if bool(args.upstream_url) != bool(args.gateway_host):
        raise ValueError("upstream and gateway Host must be supplied together")
    if args.upstream_url:
        url = urlsplit(args.upstream_url)
        if url.scheme not in ["http", "https"] or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("upstream must be an explicit HTTP(S) URL without credentials/query/fragment")
    payload = {"expected_host": args.expected_host, "user": args.user, "upstream": args.upstream_url, "gateway_host": args.gateway_host}
    command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes",
               "-o", "ConnectTimeout=10", "-i", str(key), args.user + "@" + args.host,
               shlex.join(["python3", "-c", REMOTE])]
    return subprocess.check_output(command, input=json.dumps(payload), text=True, timeout=60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--upstream-url", default="")
    parser.add_argument("--gateway-host", default="")
    try:
        print(inspect(parser.parse_args()))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"proxy inspection stopped: {type(error).__name__}\n")


if __name__ == "__main__":
    main()
