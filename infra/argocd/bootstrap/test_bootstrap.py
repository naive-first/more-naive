import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("argocd_bootstrap", Path(__file__).with_name("bootstrap.py"))
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapGuardTest(unittest.TestCase):
    def setUp(self):
        self.args = argparse.Namespace(environment="prod", context="prod", expected_server="https://prod:6443", apply=True)

    def test_dev_does_not_run_commands(self):
        self.args.environment = "dev"
        with patch.object(bootstrap.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "prod"):
                bootstrap.execute(self.args)
            run.assert_not_called()

    def test_other_server_does_not_install(self):
        with patch.object(bootstrap.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "https://other:6443")) as run:
            with self.assertRaisesRegex(ValueError, "mismatch"):
                bootstrap.execute(self.args)
            self.assertEqual(run.call_count, 1)

    def test_preflight_only_renders(self):
        self.args.apply = False
        with patch.object(bootstrap.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "https://prod:6443")) as run:
            bootstrap.execute(self.args)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args.args[0][:2], ["helm", "template"])

    def test_apply_registers_after_rollout_without_helm_install(self):
        with patch.object(bootstrap.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "https://prod:6443")) as run:
            bootstrap.execute(self.args)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertFalse(any(command[:2] == ["helm", "upgrade"] for command in commands))
            rollout = next(i for i, command in enumerate(commands) if "rollout" in command)
            root = next(i for i, command in enumerate(commands) if command[-1].endswith("/root.yaml"))
            self.assertLess(rollout, root)

    def test_repository_secret_uses_stdin_and_filtered_child_environment(self):
        with patch.dict(os.environ, {"ARGO_REPO_TOKEN": "private-repo-fixture", "RUSTFS_STATE_SECRET_KEY": "private-state-fixture"}), \
             patch.object(bootstrap.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "https://prod:6443")) as run:
            bootstrap.execute(self.args)
            injections = [call for call in run.call_args_list if "--server-side" in call.args[0]]
            self.assertEqual(len(injections), 1)
            self.assertEqual(json.loads(injections[0].kwargs["input"])["kind"], "Secret")
            for call in run.call_args_list:
                self.assertNotIn("private-repo-fixture", str(call.args))
                self.assertNotIn("ARGO_REPO_TOKEN", call.kwargs["env"])
                self.assertNotIn("RUSTFS_STATE_SECRET_KEY", call.kwargs["env"])


if __name__ == "__main__":
    unittest.main()
