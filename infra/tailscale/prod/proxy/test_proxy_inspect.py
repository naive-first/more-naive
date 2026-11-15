import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class ProxyGuards(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);binary=self.root/'bin';binary.mkdir()
        self.script=Path(__file__).with_name('inspect_proxy.sh').resolve()
        key=self.root/'key';key.write_text('not a private key');key.chmod(0o600)
        self.env={'PATH':str(binary)+':'+os.environ['PATH'],'FIXTURE_ROOT':str(self.root),'MORE_NAIVE_ENV':'prod',
                  'PROXY_HOST':'vm.ts.net','PROXY_USER':'study','PROXY_EXPECTED_HOST':'confirmed-proxy','PROXY_KEY_FILE':str(key)}
        commands={
          'ssh':r'''#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$FIXTURE_ROOT/calls"
if [[ ${!#} == 'id -un; hostname' ]]; then printf 'study\nconfirmed-proxy\n'; else bash -c "${!#}"; fi
''',
          'dig':r'''#!/usr/bin/env bash
[[ $* == *'AAAA '* ]] && exit 0
if [[ ${!#} == vm.ts.net ]]; then ip=100.90.91.104; else ip=10.0.0.2; fi
[[ ! -f $FIXTURE_ROOT/public ]] || ip=8.8.8.8
printf 'fixture 0 IN A %s\n' "$ip"
''',
          'tailscale':r'''#!/usr/bin/env bash
if [[ $1 == serve ]]; then
 echo '{"TCP":{"443":{}},"Web":{"proxy.ts.net:443":{"Handlers":{"/":{"Proxy":"http://user:fixture-secret@localhost"}}}}}'
else echo '{"BackendState":"Running","Self":{"DNSName":"proxy.ts.net","TailscaleIPs":["100.90.91.104"]},"Peer":{"other":"fixture-peer-private"}}'; fi
''',
          'sudo':'#!/bin/bash\nexit 0\n',
          'hostname':'#!/bin/bash\necho confirmed-proxy\n',
          'id':'#!/bin/bash\necho study\n',
          'curl':r'''#!/usr/bin/env bash
printf '%s\n' "$*" > "$FIXTURE_ROOT/http"
echo -n 503
'''}
        for name,body in commands.items():
            path=binary/name;path.write_text(body);path.chmod(0o700)

    def invoke(self,**changes):
        return subprocess.run(['bash',str(self.script)],env={**self.env,**changes},text=True,capture_output=True)

    def test_dev_and_missing_key_never_contact_ssh(self):
        for c in [{'MORE_NAIVE_ENV':'dev'},{'PROXY_KEY_FILE':'missing'}]:self.assertNotEqual(self.invoke(**c).returncode,0)
        self.assertFalse((self.root/'calls').exists())

    def test_public_ssh_address_rejected(self):
        (self.root/'public').touch();self.assertNotEqual(self.invoke().returncode,0)
        self.assertFalse((self.root/'calls').exists())

    def test_query_or_credentials_in_upstream_rejected(self):
        for url in ['http://name:secret@10.0.0.1/','http://10.0.0.1/?token=secret']:
            self.assertNotEqual(self.invoke(PROXY_UPSTREAM_URL=url,PROXY_GATEWAY_HOST='api.internal').returncode,0)
        self.assertFalse((self.root/'calls').exists())

    def test_remote_command_keeps_hostkey_checks_and_contains_no_mutation(self):
        r=self.invoke();self.assertEqual(r.returncode,0,r.stderr)
        calls=(self.root/'calls').read_text();self.assertIn('StrictHostKeyChecking=yes',calls);self.assertIn('BatchMode=yes',calls)
        self.assertNotIn('serve reset',calls);self.assertNotIn('funnel',calls)

    def test_remote_summary_excludes_peers_and_proxy_credentials(self):
        r=self.invoke();self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)['serve_tcp_ports'],['443'])
        self.assertNotIn('fixture-peer-private',r.stdout);self.assertNotIn('fixture-secret',r.stdout)

    def test_private_upstream_is_pinned_and_reports_status_without_redirects(self):
        r=self.invoke(PROXY_UPSTREAM_URL='http://gateway.internal:8080/',PROXY_GATEWAY_HOST='api.internal')
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['upstream_status'],'503')
        args=(self.root/'http').read_text();self.assertIn('--resolve gateway.internal:8080:10.0.0.2',args)
        self.assertIn('Host: api.internal',args);self.assertNotIn('--location',args)

    def test_private_ipv6_literal_needs_no_dns_override(self):
        r=self.invoke(PROXY_UPSTREAM_URL='http://[fd00::1]:8080/',PROXY_GATEWAY_HOST='api.internal')
        self.assertEqual(r.returncode,0,r.stderr)
        args=(self.root/'http').read_text();self.assertIn('http://[fd00::1]:8080/',args);self.assertNotIn('--resolve',args)

    def test_public_upstream_stops_before_http_request(self):
        (self.root/'public').touch()
        r=self.invoke(PROXY_HOST='100.90.91.104',PROXY_UPSTREAM_URL='http://gateway.internal/',PROXY_GATEWAY_HOST='api.internal')
        self.assertNotEqual(r.returncode,0);self.assertFalse((self.root/'http').exists())


if __name__=='__main__':unittest.main()
