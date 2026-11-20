import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class BootstrapGuardTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.binary = self.root / 'bin'; self.binary.mkdir()
        key = self.root / 'key'; key.write_text('fixture'); key.chmod(0o600)
        self.environment = {'PATH': str(self.binary) + ':' + os.environ['PATH'], 'HOME': str(self.root),
            'FIXTURE_ROOT': str(self.root), 'MORE_NAIVE_ENV': 'prod', 'SSH_HOST': 'fixture.ts.net',
            'SSH_USER': 'study', 'SSH_KEY_FILE': str(key), 'K3S_NODE_NAME': 'prod-node',
            'K3S_ROLE': 'server', 'K3S_TOKEN': 'test-only-token'}
        (self.root/'dns').write_text('fixture.ts.net. 60 IN A 100.90.91.104\n')
        (self.root/'hostname').write_text('prod-node')
        (self.root/'status').write_text('{"BackendState":"Running"}')
        for name, text in {'tailscale': '''case $1 in status) cat "$FIXTURE_ROOT/status" ;; ping) test ! -f "$FIXTURE_ROOT/ping-failure" ;; esac''', 'dig': 'cat "$FIXTURE_ROOT/dns"', 'ssh': '''printf '%s\\n' "$*" >> "$FIXTURE_ROOT/calls"
case "$*" in *'id -un'*) printf 'study\\n%s\\n' "$(cat "$FIXTURE_ROOT/hostname")" ;; *tailscale*) exit 127 ;; *) true ;; esac'''} .items():
            binary = self.binary/name; binary.write_text('#!/usr/bin/env bash\nset -eu\n'+text+'\n'); binary.chmod(0o700)
        self.script = Path(__file__).with_name('preflight.sh')

    def invoke(self, **changes):
        return subprocess.run(['bash', str(self.script)], env={**self.environment, **changes}, capture_output=True, text=True)

    def calls(self):
        file=self.root/'calls'
        return file.read_text().splitlines() if file.exists() else []

    def test_dev_never_contacts_ssh(self):
        self.assertNotEqual(self.invoke(MORE_NAIVE_ENV='dev').returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_missing_token_never_contacts_ssh(self):
        self.assertNotEqual(self.invoke(K3S_TOKEN='').returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_public_or_mixed_dns_rejected(self):
        for records in ['fixture.ts.net. 60 IN A 8.8.8.8\n', 'fixture.ts.net. 60 IN A 100.90.91.104\nfixture.ts.net. 60 IN AAAA 2001:4860:4860::8888\n']:
            (self.root/'dns').write_text(records)
            self.assertNotEqual(self.invoke().returncode, 0)
            self.assertEqual(self.calls(), [])
        self.assertEqual(self.invoke(SSH_HOST="FD7A:115C:A1E0::1").returncode, 0)

    def test_wrong_remote_hostname_never_installs(self):
        (self.root/'hostname').write_text('wrong-node')
        result=self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls()), 1)
        self.assertNotIn('test-only-token', str(self.calls())+result.stdout+result.stderr)

    def test_stopped_operator_tailnet_refuses_before_sudo(self):
        (self.root/'status').write_text('{"BackendState":"Stopped"}')
        result=self.invoke();self.assertNotEqual(result.returncode,0)
        self.assertFalse(any('sudo' in call for call in self.calls()))

    def test_unreachable_tailnet_peer_refuses_before_sudo(self):
        (self.root/'ping-failure').touch()
        result=self.invoke();self.assertNotEqual(result.returncode,0)
        self.assertFalse(any('sudo' in call for call in self.calls()))

    def test_preflight_does_not_install(self):
        result=self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls()), 2)
        self.assertFalse(any('tailscale' in call for call in self.calls()))
        self.assertTrue(all('StrictHostKeyChecking=yes' in call for call in self.calls()))
        self.assertFalse(any('install.sh' in call or 'python' in call for call in self.calls()))


if __name__ == '__main__': unittest.main()
