import argparse
import importlib.util
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
        with patch.object(bootstrap, "run") as run:
            with self.assertRaisesRegex(ValueError, "prod"):
                bootstrap.execute(self.args)
            run.assert_not_called()

    def test_other_server_does_not_install(self):
        with patch.object(bootstrap, "run", return_value=subprocess.CompletedProcess([], 0, "https://other:6443")) as run:
            with self.assertRaisesRegex(ValueError, "mismatch"):
                bootstrap.execute(self.args)
            self.assertEqual(run.call_count, 1)

    def test_preflight_only_renders(self):
        self.args.apply = False
        with patch.object(bootstrap, "run", return_value=subprocess.CompletedProcess([], 0, "https://prod:6443")) as run:
            bootstrap.execute(self.args)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args.args[0][:2], ["helm", "template"])


if __name__ == "__main__":
    unittest.main()
