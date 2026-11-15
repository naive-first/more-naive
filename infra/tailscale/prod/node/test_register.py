import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class RegistrationGuards(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.bin=self.root/'bin';self.bin.mkdir()
        self.script=Path(__file__).with_name('register.sh').resolve()
        for name in ['bash','hostname','id','uname','jq','mktemp','rm']:
            (self.bin/name).symlink_to(shutil.which(name))
        self.env={'PATH':str(self.bin),'HOME':str(self.root),'FIXTURE_ROOT':str(self.root),'MORE_NAIVE_ENV':'prod',
                  'TAILSCALE_EXPECTED_HOST':subprocess.check_output(['hostname'],text=True).strip(),
                  'TAILSCALE_NODE_NAME':'prod-node','SSH_USER':subprocess.check_output(['id','-un'],text=True).strip()}
        (self.root/'status').write_text('{"BackendState":"NeedsLogin"}')

    def binary(self):
        tool=self.bin/'tailscale';tool.write_text('''#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$FIXTURE_ROOT/calls"
case $1 in
 status) /bin/cat "$FIXTURE_ROOT/status";;
 version) echo 1.104.7;;
 up)
   [[ -z ${TAILSCALE_AUTH_KEY-} ]]
   for arg in "$@"; do
     if [[ $arg == --auth-key=file:* ]]; then
       path=${arg#--auth-key=file:}
       [[ $(/usr/bin/stat -c %a "$path") == 600 ]]
       [[ $(/usr/bin/stat -c %a "${path%/*}") == 700 ]]
       [[ $(/bin/cat "$path") == fixture-join-key ]]
       printf '%s' "$path" > "$FIXTURE_ROOT/key-path"
     fi
   done;;
esac
''');tool.chmod(0o700)

    def run_script(self,*args,**changes):
        return subprocess.run(['/bin/bash',str(self.script),*args],env={**self.env,**changes},text=True,capture_output=True)

    def test_environment_and_host_guard(self):
        self.binary()
        for changes in [{'MORE_NAIVE_ENV':'dev'},{'TAILSCALE_EXPECTED_HOST':'other'}]:
            self.assertNotEqual(self.run_script(**changes).returncode,0)
        self.assertFalse((self.root/'calls').exists())

    def test_existing_node_never_rejoins(self):
        self.binary();(self.root/'status').write_text('{"BackendState":"Running","Self":{"HostName":"prod-node","ID":"existing"}}')
        r=self.run_script('--apply');self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual((self.root/'calls').read_text().splitlines(),['status --json'])

    def test_expired_existing_node_stops(self):
        self.binary();(self.root/'status').write_text('{"BackendState":"NeedsLogin","Self":{"ID":"existing"}}')
        r=self.run_script('--apply','--policy-reviewed',TAILSCALE_AUTH_KEY='fixture-join-key')
        self.assertNotEqual(r.returncode,0);self.assertNotIn('up ',(self.root/'calls').read_text())

    def test_missing_auth_key_never_registers(self):
        self.binary();r=self.run_script('--apply','--policy-reviewed')
        self.assertNotEqual(r.returncode,0);self.assertNotIn('up ',(self.root/'calls').read_text())

    def test_missing_binary_preflight_never_installs(self):
        r=self.run_script();self.assertEqual(r.returncode,0,r.stderr);self.assertIn('NOT_RUN',r.stdout)

    def test_join_uses_private_temporary_file_and_removes_it(self):
        self.binary();r=self.run_script('--apply','--policy-reviewed',TAILSCALE_AUTH_KEY='fixture-join-key')
        self.assertEqual(r.returncode,0,r.stderr);path=Path((self.root/'key-path').read_text())
        self.assertFalse(path.exists());self.assertNotIn('fixture-join-key',(self.root/'calls').read_text()+r.stdout+r.stderr)

    def test_existing_managed_service_prevents_download_and_binary_writes(self):
        r=subprocess.run(['docker','run','--rm','--network','none','--user','0',
                          '-v',str(self.script.parent)+':/source:ro','--entrypoint','bash','eclipse-temurin:21-jre-jammy','-c',
                          '''set -eu
mkdir -p /etc/systemd/system /fixture
: > /etc/systemd/system/more-naive-tailscaled.service
export MORE_NAIVE_ENV=prod TAILSCALE_EXPECTED_HOST=$(hostname) TAILSCALE_NODE_NAME=prod-node SSH_USER=root TAILSCALE_AUTH_KEY=fixture
if bash /source/register.sh --apply --policy-reviewed > /fixture/output 2>&1; then exit 1; fi
grep -q 'existing managed service' /fixture/output
test ! -e /usr/local/bin/tailscale
test ! -e /usr/local/sbin/tailscaled
'''],text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)


if __name__=='__main__':unittest.main()
