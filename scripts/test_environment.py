"""Exercise the standard direnv entrypoint with owned, non-secret fixtures."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class EnvironmentContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="more-naive-env-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / "config/env"
        self.config.mkdir(parents=True)
        source = Path(__file__).resolve().parents[1] / "config/env/.envrc"
        shutil.copyfile(source, self.config / ".envrc")
        self.environment = {"PATH": os.environ["PATH"], "HOME": str(self.root),
                            "XDG_CONFIG_HOME": str(self.root / "xdg")}
        self.dev = self.root / "env.dev"
        self.prod = self.root / "env.prod"
        self.dev.write_text("DB_USERNAME=dev-fixture\nDB_PASSWORD='dev password'\n")
        self.prod.write_text("DB_USERNAME=prod-fixture\nDB_PASSWORD='prod password'\n")
        subprocess.run(["direnv", "allow", str(self.config)], env=self.environment,
                       capture_output=True, check=True)

    def run_environment(self, selected="dev", cwd=None, arguments=None):
        environment = dict(self.environment)
        if selected is not None:
            environment["MORE_NAIVE_ENV"] = selected
        return subprocess.run(
            ["direnv", "exec", str(self.config), "bash", "-c", arguments or
             'printf \'{"username":"%s","password":"%s"}\' "$DB_USERNAME" "$DB_PASSWORD"'],
            env=environment, cwd=cwd or self.root, capture_output=True, text=True,
        )

    def test_same_keys_select_different_environment_values(self):
        self.assertEqual(json.loads(self.run_environment().stdout)["username"], "dev-fixture")
        self.assertEqual(json.loads(self.run_environment("prod").stdout)["username"], "prod-fixture")

    def test_root_and_subdirectory_read_the_same_file(self):
        self.assertEqual(self.run_environment().stdout,
                         self.run_environment(cwd=self.config).stdout)

    def test_environment_is_required_before_command(self):
        result = self.run_environment(None, arguments="touch invoked")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "invoked").exists())

    def test_unknown_environment_stops_before_command(self):
        result = self.run_environment("staging", arguments="touch invoked")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "invoked").exists())

    def test_missing_selected_file_does_not_fall_back(self):
        self.prod.unlink()
        result = self.run_environment("prod", arguments="touch invoked")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "invoked").exists())

    def test_unselected_file_is_not_parsed(self):
        self.prod.write_text("malformed secret fixture\n")
        self.assertEqual(self.run_environment().returncode, 0)

    def test_single_quoted_shell_syntax_remains_literal(self):
        self.dev.write_text("DB_USERNAME=fixture\nDB_PASSWORD='$(touch invoked) $HOME `id`'\n")
        result = self.run_environment()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["password"], "$(touch invoked) $HOME `id`")
        self.assertFalse((self.root / "invoked").exists())

    def test_malformed_secret_is_suppressed_and_command_is_not_run(self):
        self.dev.write_text("DB_PASSWORD=private-fixture invalid syntax\n")
        result = self.run_environment(arguments="touch invoked")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("private-fixture", result.stdout + result.stderr)
        self.assertFalse((self.root / "invoked").exists())

    def test_file_cannot_promote_dev_selection_to_prod(self):
        self.dev.write_text("MORE_NAIVE_ENV=prod\n")
        result = self.run_environment(arguments="touch invoked")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "invoked").exists())


class StatePreflightTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.profile = Path(self.temporary.name) / "fixture.credentials"
        self.profile.write_text("fixture only\n")
        self.profile.chmod(0o600)
        self.script = Path(__file__).resolve().parents[1] / "infra/terragrunt/state-preflight.sh"
        self.environment = {"PATH": os.environ["PATH"], "MORE_NAIVE_ENV": "prod",
                            "RUSTFS_ENDPOINT": "http://127.0.0.1:9000", "RUSTFS_BUCKET": "fixture",
                            "RUSTFS_REGION": "us-east-1", "RUSTFS_CREDENTIALS_FILE": str(self.profile)}

    def run_guard(self, **changes):
        return subprocess.run(["bash", str(self.script)], env={**self.environment, **changes},
                              capture_output=True, text=True)

    def test_private_profile_and_loopback_or_tls_are_accepted(self):
        for endpoint in ("http://127.0.0.1:9000", "http://[::1]:9000", "https://fixture.ts.net"):
            self.assertEqual(self.run_guard(RUSTFS_ENDPOINT=endpoint).returncode, 0)

    def test_bad_target_and_dev_stop_without_secret_output(self):
        for endpoint in ("", "http://8.8.8.8:9000", "http://127.0.0.1:9000@public.example", "https://private-marker@example.net"):
            result = self.run_guard(RUSTFS_ENDPOINT=endpoint)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("private-marker", result.stdout + result.stderr)
        self.assertNotEqual(self.run_guard(MORE_NAIVE_ENV="dev").returncode, 0)

    def test_missing_or_insecure_profile_is_not_created_or_changed(self):
        before = self.profile.read_bytes()
        self.profile.chmod(0o644)
        self.assertNotEqual(self.run_guard().returncode, 0)
        self.assertEqual(self.profile.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.profile.read_bytes(), before)
        missing = self.profile.with_name("absent")
        self.assertNotEqual(self.run_guard(RUSTFS_CREDENTIALS_FILE=str(missing)).returncode, 0)
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
