import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class VerifyGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);binary=self.root/'bin';binary.mkdir()
        self.environment={'PATH':str(binary)+':'+os.environ['PATH'],'HOME':str(self.root),'FIXTURE_ROOT':str(self.root),
                          'MORE_NAIVE_ENV':'prod','KUBE_CONTEXT':'more-naive-prod','KUBE_SERVER':'https://fixture:6443'}
        (self.root/'server').write_text('https://fixture:6443')
        (self.root/'nodes').write_text(json.dumps({'items':[{'metadata':{'name':'node-a'}},{'metadata':{'name':'node-b'}}]}))
        executable=binary/'kubectl';executable.write_text('''#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$FIXTURE_ROOT/calls"
case "$*" in
 *'config view'*) cat "$FIXTURE_ROOT/server" ;;
 *'get nodes'*) cat "$FIXTURE_ROOT/nodes" ;;
 *'wait pod/'*) [[ ! -f $FIXTURE_ROOT/fail ]] ;;
 *'get pod'*) if [[ $* == *probe-0* ]]; then echo '{"status":{"podIP":"10.42.0.1"}}'; else echo '{"status":{"podIP":"10.42.0.2"}}'; fi ;;
 *'wget'*) echo ok ;;
esac
''');executable.chmod(0o700)
        self.script=Path(__file__).with_name('verify.sh')

    def invoke(self, extra=None, **changes):
        return subprocess.run(['bash',str(self.script),'--node','node-a','--node','node-b',*(extra or [])],
                              env={**self.environment,**changes},capture_output=True,text=True)

    def calls(self):
        p=self.root/'calls';return p.read_text().splitlines() if p.exists() else []

    def test_dev_and_wrong_context_never_contact_cluster(self):
        for change in ({'MORE_NAIVE_ENV':'dev'},{'KUBE_CONTEXT':'other'}):
            self.assertNotEqual(self.invoke(**change).returncode,0)
            self.assertEqual(self.calls(),[])

    def test_wrong_server_never_creates_namespace(self):
        (self.root/'server').write_text('https://other:6443')
        self.assertNotEqual(self.invoke(['--write-smoke']).returncode,0)
        self.assertFalse(any('create namespace' in call for call in self.calls()))

    def test_wrong_inventory_never_creates_namespace(self):
        (self.root/'nodes').write_text('{"items":[]}')
        self.assertNotEqual(self.invoke(['--write-smoke']).returncode,0)
        self.assertFalse(any('create namespace' in call for call in self.calls()))

    def test_without_opt_in_only_checks_context_nodes_and_ready(self):
        result=self.invoke();self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('NOT_RUN',result.stdout)
        self.assertFalse(any('create namespace' in call for call in self.calls()))

    def test_failed_probe_cleans_only_owned_namespace(self):
        (self.root/'fail').touch();self.assertNotEqual(self.invoke(['--write-smoke']).returncode,0)
        creates=[call.split('create namespace ',1)[1] for call in self.calls() if 'create namespace ' in call]
        deletes=[call.split('delete namespace ',1)[1].split()[0] for call in self.calls() if 'delete namespace ' in call]
        self.assertEqual(len(creates),1);self.assertTrue(creates[0].startswith('more-naive-network-'))
        self.assertEqual(deletes,creates)

    def test_opt_in_checks_all_dns_and_peer_paths_then_cleans_namespace(self):
        result=self.invoke(['--write-smoke'])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(sum('nslookup' in call for call in self.calls()),2)
        self.assertEqual(sum('wget' in call for call in self.calls()),4)
        self.assertEqual(sum('http://10.42.0.1:8080' in call for call in self.calls()),2)
        self.assertEqual(sum('http://10.42.0.2:8080' in call for call in self.calls()),2)
        self.assertEqual(sum('delete namespace more-naive-network-' in call for call in self.calls()),1)


if __name__=='__main__':unittest.main()
