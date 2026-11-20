import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class BootstrapGuardTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name); source=Path(__file__).resolve().parents[3]
        for relative in ['scripts/check-cluster.sh','infra/argocd/bootstrap/bootstrap.sh',
                         'infra/argocd/bootstrap/repository-secret.jq','infra/environments/prod/argocd.yaml',
                         'infra/argocd/bootstrap/prod/root.yaml']:
            target=self.root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/relative,target)
        binary=self.root/'bin';binary.mkdir();(self.root/'server').write_text('https://prod:6443')
        self.environment={'PATH':str(binary)+':'+os.environ['PATH'],'HOME':str(self.root),'FIXTURE_ROOT':str(self.root),
                          'MORE_NAIVE_ENV':'prod','KUBE_CONTEXT':'prod','KUBE_SERVER':'https://prod:6443'}
        common='''#!/usr/bin/env bash
set -eu
printf '%s %s\\n' "$(basename "$0")" "$*" >> "$FIXTURE_ROOT/calls"
env > "$FIXTURE_ROOT/child-environment"
'''
        kubectl=binary/'kubectl';kubectl.write_text(common+'''case "$*" in
 *'config view'*) cat "$FIXTURE_ROOT/server" ;;
 *'--server-side'*) cat > "$FIXTURE_ROOT/secret" ;;
 *'condition=Established'*) [[ ! -f $FIXTURE_ROOT/fail-crd ]] ;;
esac
''');kubectl.chmod(0o700)
        helm=binary/'helm';helm.write_text(common);helm.chmod(0o700)
        self.script=self.root/'infra/argocd/bootstrap/bootstrap.sh'

    def invoke(self, apply=False, **changes):
        return subprocess.run(['bash',str(self.script),*(['--apply'] if apply else [])],
                              env={**self.environment,**changes},capture_output=True,text=True)

    def calls(self):
        p=self.root/'calls';return p.read_text().splitlines() if p.exists() else []

    def test_dev_does_not_run_commands(self):
        self.assertNotEqual(self.invoke(MORE_NAIVE_ENV='dev').returncode,0)
        self.assertEqual(self.calls(),[])

    def test_other_server_does_not_install(self):
        (self.root/'server').write_text('https://other:6443')
        self.assertNotEqual(self.invoke().returncode,0)
        self.assertEqual(len(self.calls()),1)

    def test_preflight_only_renders(self):
        result=self.invoke();self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(self.calls()),2)
        self.assertTrue(self.calls()[-1].startswith('helm template'))
        self.assertFalse(any(' apply ' in call for call in self.calls()))

    def test_crd_failure_stops_control_plane_and_root_registration(self):
        declarations=self.root/'infra/argocd/applications/prod';declarations.mkdir(parents=True)
        for name in ['istio-base','istiod']:(declarations/f'{name}.yaml').write_text('fixture')
        (self.root/'fail-crd').touch()
        result=self.invoke(True);self.assertNotEqual(result.returncode,0)
        calls='\n'.join(self.calls())
        self.assertIn('istio-base.yaml',calls)
        self.assertNotIn('istiod.yaml',calls);self.assertNotIn('/root.yaml',calls)

    def test_apply_registers_after_rollout_without_helm_install(self):
        declarations=self.root/'infra/argocd/applications/prod';declarations.mkdir(parents=True)
        for name in ['istio-base','istiod','istio-gateway','postgres','backend']:(declarations/f'{name}.yaml').write_text('fixture')
        result=self.invoke(True);self.assertEqual(result.returncode,0,result.stderr)
        calls=self.calls();self.assertFalse(any('helm upgrade' in call for call in calls))
        rollout=next(i for i,call in enumerate(calls) if 'rollout status' in call)
        root=next(i for i,call in enumerate(calls) if call.endswith('/root.yaml'))
        self.assertLess(rollout,root)
        positions=[next(i for i,c in enumerate(calls) if c.endswith('/'+name+'.yaml')) for name in ['istio-base','istiod','istio-gateway','postgres','backend']]
        self.assertEqual(positions,sorted(positions));self.assertLess(positions[-1],root)
        self.assertTrue(any('statefulset/postgres --timeout=300s' in c for c in calls))

    def test_repository_secret_uses_stdin_and_filtered_child_environment(self):
        result=self.invoke(True,ARGO_REPO_TOKEN='private-repo-fixture',RUSTFS_STATE_SECRET_KEY='private-state-fixture')
        self.assertEqual(result.returncode,0,result.stderr)
        obj=json.loads((self.root/'secret').read_text())
        self.assertEqual(obj['kind'],'Secret')
        self.assertEqual(base64.b64decode(obj['data']['password']),b'private-repo-fixture')
        self.assertEqual(base64.b64decode(obj['data']['username']),b'x-access-token')
        self.assertNotIn('private-repo-fixture','\n'.join(self.calls())+result.stdout+result.stderr)
        env=(self.root/'child-environment').read_text()
        self.assertNotIn('ARGO_REPO_TOKEN=',env);self.assertNotIn('RUSTFS_STATE_SECRET_KEY=',env)


if __name__=='__main__':unittest.main()
