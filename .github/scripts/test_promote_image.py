import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

DIGEST='sha256:'+'a'*64
SOURCE='b'*40
IMAGE='ghcr.io/naive-first/more-naive-backend'
VALUES='infra/environments/prod/backend.yaml'
APPLICATION='infra/argocd/applications/prod/backend.yaml'


class PromotionTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.repo=self.root/'work';self.repo.mkdir();binary=self.root/'bin';binary.mkdir()
        self.script=Path(__file__).with_name('promote-image.sh').resolve()
        self.env={**os.environ,'PATH':str(binary)+':'+os.environ['PATH'],'FIXTURE_ROOT':str(self.root),'GITHUB_REPOSITORY':'naive-first/more-naive','GITHUB_REF':'refs/heads/main','SOURCE_SHA':SOURCE,'IMAGE_DIGEST':DIGEST,'GITHUB_STEP_SUMMARY':str(self.root/'summary')}
        self.git('init','-b','main');self.git('config','user.name','Fixture');self.git('config','user.email','fixture@example.invalid')
        self.remote=self.root/'origin.git';subprocess.run(['git','init','--bare','-q',str(self.remote)],check=True)
        self.git('remote','add','origin',str(self.remote))
        self.values=f'image:\n  repository: {IMAGE}\n  digest: ""\nreplicaCount: 1\n'
        for name,body in {VALUES:self.values,APPLICATION+'.example':'kind: Application\n'}.items():
            path=self.repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
        docker=binary/'docker';docker.write_text(r'''#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$FIXTURE_ROOT/docker-calls"
[[ $(cat "$2/config.json") == '{"auths":{}}' ]]
if [[ $3 == pull ]]; then
 [[ ! -f $FIXTURE_ROOT/private ]] || { echo 'anonymous denied' >&2; exit 1; }
 echo 'raw anonymous pull stdout'
else printf '["%s"]\n' "$5"; fi
''');docker.chmod(0o700)
        gh=binary/'gh';gh.write_text(r'''#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$FIXTURE_ROOT/gh-calls"
if [[ $2 == list ]]; then
 [[ ! -f $FIXTURE_ROOT/open ]] || echo 'https://github.com/naive-first/more-naive/pull/999'
else
 for ((i=1;i<=$#;i++)); do if [[ ${!i} == --body-file ]]; then ((i+=1)); cat "${!i}" > "$FIXTURE_ROOT/body"; fi; done
 touch "$FIXTURE_ROOT/open"
 echo 'https://github.com/naive-first/more-naive/pull/999'
fi
''');gh.chmod(0o700)

    def git(self,*args):
        r=subprocess.run(['git',*args],cwd=self.repo,text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr);return r.stdout.strip()

    def publish_main(self):
        self.git('add','-A');self.git('commit','-qm','fixture');self.git('push','-q','origin','main')
        self.base=self.git('rev-parse','HEAD');return 'ci/backend-'+SOURCE[:12]+'-'+DIGEST[7:19]+'-'+self.base[:7]

    def invoke(self,**changes):
        return subprocess.run(['bash',str(self.script)],cwd=self.repo,env={**self.env,**changes},text=True,capture_output=True)

    def changes(self,branch):
        self.git('fetch','-q','origin',branch)
        return self.git('diff','--no-renames','--name-only',self.base,'FETCH_HEAD').splitlines()

    def test_only_image_digest_changes_on_later_promotion(self):
        (self.repo/(APPLICATION+'.example')).rename(self.repo/APPLICATION)
        branch=self.publish_main();r=self.invoke();self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        self.assertEqual(self.changes(branch),[VALUES])
        self.assertEqual(self.git('show','FETCH_HEAD:'+VALUES),self.values.replace('digest: ""','digest: "'+DIGEST+'"').strip())

    def test_unknown_repository_or_duplicate_digest_is_rejected(self):
        self.publish_main()
        for body in [self.values.replace(IMAGE,'ghcr.io/unapproved/image'),self.values.replace('  digest:','  digest: "old"\n  digest:')]:
            (self.repo/VALUES).write_text(body);self.git('add',VALUES);self.git('commit','-qm','bad fixture');self.git('push','-q','origin','main')
            r=self.invoke();self.assertNotEqual(r.returncode,0)
        self.assertFalse((self.root/'gh-calls').exists())
        self.assertEqual(self.git('ls-remote','--heads','origin').count('refs/heads/'),1)

    def test_invalid_digest_or_source_stops_before_pull_or_api(self):
        for changes in [{'IMAGE_DIGEST':'latest'},{'SOURCE_SHA':'main'},{'GITHUB_REPOSITORY':'untrusted/repo'},{'GITHUB_REF':'refs/heads/dev'}]:self.assertNotEqual(self.invoke(**changes).returncode,0)
        self.assertFalse((self.root/'docker-calls').exists());self.assertFalse((self.root/'gh-calls').exists())

    def test_private_image_failure_stops_before_configuration_changes(self):
        self.publish_main();(self.root/'private').touch();r=self.invoke();self.assertNotEqual(r.returncode,0)
        self.assertIn('anonymous denied',r.stdout);self.assertIn('[exit=1]',r.stdout)
        self.assertFalse((self.root/'gh-calls').exists());self.assertEqual(self.git('ls-remote','--heads','origin').count('refs/heads/'),1)

    def test_first_promotion_atomically_sets_digest_and_activates_application(self):
        branch=self.publish_main();r=self.invoke();self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        self.assertEqual(set(self.changes(branch)),{VALUES,APPLICATION,APPLICATION+'.example'})
        body=(self.root/'body').read_text();self.assertIn('raw anonymous pull stdout',body);self.assertIn('[exit=0]',body)
        self.assertIn(SOURCE,body);self.assertIn(DIGEST,body);self.assertNotIn('closes #',body)
        r=self.invoke();self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual((self.root/'gh-calls').read_text().count('pr create'),1)

    def test_existing_divergent_branch_is_never_overwritten(self):
        branch=self.publish_main();self.git('checkout','-qb',branch)
        (self.repo/'unrelated').write_text('do not overwrite');self.git('add','unrelated');self.git('commit','-qm','divergent');self.git('push','-q','origin',branch)
        before=self.git('rev-parse','HEAD');r=self.invoke();self.assertNotEqual(r.returncode,0)
        self.assertIn(before,self.git('ls-remote','origin','refs/heads/'+branch));self.assertFalse((self.root/'gh-calls').exists())

    def test_missing_deployment_prerequisite_does_not_create_a_branch(self):
        (self.repo/(APPLICATION+'.example')).unlink();self.publish_main();r=self.invoke();self.assertNotEqual(r.returncode,0)
        self.assertFalse((self.root/'gh-calls').exists());self.assertEqual(self.git('ls-remote','--heads','origin').count('refs/heads/'),1)

    def test_same_active_digest_is_idempotent(self):
        (self.repo/(APPLICATION+'.example')).rename(self.repo/APPLICATION)
        (self.repo/VALUES).write_text(self.values.replace('digest: ""','digest: "'+DIGEST+'"'));self.publish_main()
        r=self.invoke();self.assertEqual(r.returncode,0,r.stderr+r.stdout);self.assertIn('Already promoted',r.stdout)
        self.assertFalse((self.root/'gh-calls').exists());self.assertEqual(self.git('ls-remote','--heads','origin').count('refs/heads/'),1)


if __name__=='__main__':unittest.main()
