import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


FAKE_KUBECTL = """#!/usr/bin/env python3
import json,os,pathlib,sys
root=pathlib.Path(os.environ['HOME']); args=sys.argv[1:]
(root/'child-environment.json').write_text(json.dumps(dict(os.environ)))
with (root/'calls.jsonl').open('a') as log: log.write(json.dumps(args)+'\\n')
if (root/'fail').exists():
 print('fixture-password-must-not-leak',file=sys.stderr);sys.exit(1)
if 'config' in args:
 print(json.dumps({'clusters':[{'cluster':{'server':(root/'server').read_text()}}]}));sys.exit()
if 'namespace' in args:
 print(json.dumps({'metadata':{'name':'more-naive-prod'}}));sys.exit()
if 'apply' in args:
 payload=json.load(sys.stdin);(root/'state.json').write_text(json.dumps(payload));sys.exit()
state=json.loads((root/'state.json').read_text())
kind='ConfigMap' if 'configmap' in args else 'Secret'
obj=next(item for item in state['items'] if item['kind']==kind)
if (root/'tamper').exists(): obj['data']={}
print(json.dumps(obj))
"""


class InjectConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        scripts = self.root / "scripts"
        scripts.mkdir()
        for name in ("env.py", "inject-config.py"):
            source = Path(__file__).with_name(name)
            shutil.copyfile(source, scripts / name)
        binary = self.root / "bin"
        binary.mkdir()
        kubectl = binary / "kubectl"
        kubectl.write_text(FAKE_KUBECTL)
        kubectl.chmod(0o755)
        (self.root / "server").write_text("https://fixture:6443")
        self.dotenv = self.root / "env.prod"
        self.dotenv.write_text(
            "KUBE_CONTEXT=fixture-prod\nKUBE_SERVER=https://fixture:6443\n"
            "NAMESPACE=more-naive-prod\nDB_DATABASE=more_naive\n"
            "DB_USERNAME=more_naive\nDB_PASSWORD=fixture-password-must-not-leak\n"
            "LOCAL_DB_PASSWORD=local-secret\nRUSTFS_ADMIN_SECRET_KEY=rustfs-secret\n"
        )
        self.environment = {
            "HOME": str(self.root),
            "PATH": str(binary) + os.pathsep + os.environ["PATH"],
        }

    def run_command(
        self, extra: list[str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts/inject-config.py"),
                "--environment",
                "prod",
                "--context",
                "fixture-prod",
                "--namespace",
                "more-naive-prod",
                "--apply",
                *(extra or []),
            ],
            cwd=self.root,
            env=self.environment,
            capture_output=True,
            text=True,
        )

    def calls(self) -> list[list[str]]:
        log = self.root / "calls.jsonl"
        return (
            [json.loads(line) for line in log.read_text().splitlines()]
            if log.exists()
            else []
        )

    def test_selected_objects_are_applied_over_stdin_and_verified(self) -> None:
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        objects = json.loads((self.root / "state.json").read_text())["items"]
        config, secret = objects
        self.assertEqual(config["metadata"]["name"], "more-naive-config")
        self.assertEqual(
            config["data"],
            {
                "DB_DATABASE": "more_naive",
                "DB_USERNAME": "more_naive",
                "DB_URL": "jdbc:postgresql://postgres.more-naive-prod.svc.cluster.local:5432/more_naive",
            },
        )
        self.assertEqual(secret["metadata"]["name"], "more-naive-db")
        self.assertEqual(
            secret["data"],
            {
                "DB_PASSWORD": base64.b64encode(
                    b"fixture-password-must-not-leak"
                ).decode()
            },
        )
        self.assertNotIn(
            "fixture-password-must-not-leak",
            result.stdout + result.stderr + json.dumps(self.calls()),
        )
        self.assertTrue(
            all("--context" in call and "fixture-prod" in call for call in self.calls())
        )
        self.assertIn("verified", result.stdout)
        child_environment = json.loads(
            (self.root / "child-environment.json").read_text()
        )
        self.assertNotIn("DB_PASSWORD", child_environment)

    def test_repeat_updates_same_resource_names(self) -> None:
        self.assertEqual(self.run_command().returncode, 0)
        self.dotenv.write_text(
            self.dotenv.read_text().replace(
                "fixture-password-must-not-leak", "replacement-fixture"
            )
        )
        self.assertEqual(self.run_command().returncode, 0)
        objects = json.loads((self.root / "state.json").read_text())["items"]
        self.assertEqual(len(objects), 2)
        self.assertEqual(
            objects[1]["data"]["DB_PASSWORD"],
            base64.b64encode(b"replacement-fixture").decode(),
        )

    def test_wrong_environment_refuses_before_kubectl(self) -> None:
        result = self.run_command(["--environment", "dev"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_wrong_context_refuses_before_kubectl(self) -> None:
        result = self.run_command(["--context", "wrong"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_wrong_namespace_refuses_before_kubectl(self) -> None:
        result = self.run_command(["--namespace", "other"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_wrong_server_stops_before_apply(self) -> None:
        (self.root / "server").write_text("https://wrong-cluster:6443")
        result = self.run_command()
        self.assertEqual(result.returncode, 2)
        self.assertFalse(any("apply" in call for call in self.calls()))

    def test_missing_password_stops_before_kubectl(self) -> None:
        self.dotenv.write_text(
            self.dotenv.read_text().replace(
                "DB_PASSWORD=fixture-password-must-not-leak", "DB_PASSWORD="
            )
        )
        result = self.run_command()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_kubectl_error_cannot_echo_secret(self) -> None:
        (self.root / "fail").touch()
        result = self.run_command()
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(
            "fixture-password-must-not-leak", result.stdout + result.stderr
        )

    def test_readback_mismatch_is_not_success(self) -> None:
        (self.root / "tamper").touch()
        result = self.run_command()
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("verified", result.stdout)

    def test_missing_apply_opt_in_stops_before_kubectl(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts/inject-config.py"),
                "--environment",
                "prod",
                "--context",
                "fixture-prod",
                "--namespace",
                "more-naive-prod",
            ],
            env=self.environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
