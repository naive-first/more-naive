import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class EnvironmentCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "scripts").mkdir()
        source = Path(__file__).with_name("env.py")
        shutil.copyfile(source, self.root / "scripts" / "env.py")
        self.dotenv = self.root / "env.dev"
        self.output = self.root / "child.json"
        self.dotenv.write_text(
            "DB_URL=jdbc:postgresql://localhost:5432/local\n"
            "DB_USERNAME=local_user\n"
            "DB_PASSWORD=local_password\n",
            encoding="utf-8",
        )

    def run_command(
        self,
        consumer: str = "app",
        extra: dict[str, str] | None = None,
        cwd: Path | None = None,
        env_name: str = "dev",
    ) -> subprocess.CompletedProcess[str]:
        environment = {"PATH": os.environ["PATH"], "HOME": str(self.root)}
        environment.update(extra or {})
        script = "import json,os,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(json.dumps(dict(os.environ)))"
        return subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts" / "env.py"),
                "--env",
                env_name,
                consumer,
                "--",
                sys.executable,
                "-c",
                script,
                str(self.output),
            ],
            env=environment,
            cwd=cwd or self.root,
            capture_output=True,
            text=True,
        )

    def child(self) -> dict[str, str]:
        return json.loads(self.output.read_text())

    def test_root_and_subdirectory_use_same_dotenv(self) -> None:
        self.assertEqual(self.run_command().returncode, 0)
        root_environment = self.child()
        self.assertEqual(self.run_command(cwd=self.root / "scripts").returncode, 0)
        self.assertEqual(self.child(), root_environment)
        self.assertEqual(
            self.child()["DB_URL"], "jdbc:postgresql://localhost:5432/local"
        )

    def test_other_consumer_and_inherited_secrets_are_not_forwarded(self) -> None:
        with self.dotenv.open("a") as dotenv:
            dotenv.write("RUSTFS_STATE_SECRET_KEY=state-secret\n")
        result = self.run_command(
            extra={"GH_TOKEN": "github-secret", "PYTHONPATH": "injected"}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            {
                "GH_TOKEN",
                "PYTHONPATH",
                "RUSTFS_STATE_SECRET_KEY",
            }.isdisjoint(self.child())
        )
        self.assertEqual(self.child()["DB_PASSWORD"], "local_password")

    def test_selected_process_value_overrides_file(self) -> None:
        result = self.run_command(extra={"DB_USERNAME": "ci_user"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.child()["DB_USERNAME"], "ci_user")

    def test_empty_override_fails_before_child_without_logging_values(self) -> None:
        result = self.run_command(
            extra={"DB_PASSWORD": "", "GH_TOKEN": "private-marker"}
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("DB_PASSWORD", result.stderr)
        self.assertNotIn("private-marker", result.stderr + result.stdout)
        self.assertFalse(self.output.exists())

    def test_quotes_spaces_and_shell_syntax_are_literal(self) -> None:
        marker = self.root / "must-not-exist"
        self.dotenv.write_text(
            "# comment\nDB_URL = 'jdbc:postgresql://localhost/local'\n"
            'DB_USERNAME = "a user"\n'
            f"DB_PASSWORD='$(touch {marker}) $HOME `id`'\n"
        )
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.child()["DB_USERNAME"], "a user")
        self.assertEqual(self.child()["DB_PASSWORD"], f"$(touch {marker}) $HOME `id`")
        self.assertFalse(marker.exists())

    def test_invalid_dotenv_fails_without_echoing_secret_line(self) -> None:
        self.dotenv.write_text("export PRIVATE=secret-marker\n")
        result = self.run_command()
        self.assertEqual(result.returncode, 2)
        self.assertIn("line 1", result.stderr)
        self.assertNotIn("secret-marker", result.stderr + result.stdout)
        self.assertFalse(self.output.exists())

    def test_duplicate_key_fails(self) -> None:
        with self.dotenv.open("a") as dotenv:
            dotenv.write("DB_PASSWORD=duplicate\n")
        result = self.run_command()
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())

    def test_unclosed_quote_fails(self) -> None:
        self.dotenv.write_text("DB_PASSWORD='private-marker\n")
        result = self.run_command()
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("private-marker", result.stderr)

    def test_prod_does_not_fall_back_to_dev_file(self) -> None:
        result = self.run_command("cluster-config", env_name="prod")
        self.assertEqual(result.returncode, 2)
        self.assertIn("DB_PASSWORD", result.stderr)
        self.assertFalse(self.output.exists())

    def test_environment_files_share_keys_and_select_different_values(self) -> None:
        (self.root / "env.prod").write_text(
            "DB_URL=jdbc:postgresql://fixture/prod\n"
            "DB_USERNAME=prod_user\nDB_PASSWORD=prod_fixture\n"
        )
        self.assertEqual(self.run_command(env_name="prod").returncode, 0)
        self.assertEqual(self.child()["DB_USERNAME"], "prod_user")
        self.assertEqual(self.child()["DB_PASSWORD"], "prod_fixture")
        prod_keys = set(self.child())
        self.assertEqual(self.run_command().returncode, 0)
        self.assertEqual(self.child()["DB_USERNAME"], "local_user")
        self.assertEqual(set(self.child()), prod_keys)

    def test_unselected_file_is_not_parsed(self) -> None:
        (self.root / "env.prod").write_text("export PRIVATE=invalid\n")
        self.assertEqual(self.run_command().returncode, 0)

    def test_prod_does_not_fall_back_to_legacy_dotenv_or_prefixed_keys(self) -> None:
        (self.root / ".env").write_text(self.dotenv.read_text())
        result = self.run_command(
            env_name="prod",
            extra={
                "PROD_DB_URL": "fixture",
                "PROD_DB_USERNAME": "fixture",
                "PROD_DB_PASSWORD": "private-marker",
            },
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("private-marker", result.stderr + result.stdout)
        self.assertFalse(self.output.exists())

    def test_environment_selection_is_required(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts/env.py"),
                "app",
                "--",
                sys.executable,
                "-c",
                "raise SystemExit(0)",
            ],
            env={"PATH": os.environ["PATH"]},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--env", result.stderr)

    def test_unknown_environment_stops_before_child(self) -> None:
        result = self.run_command(env_name="staging")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())

    def test_dev_infrastructure_stops_before_child(self) -> None:
        self.dotenv.write_text(
            "KUBE_CONTEXT=fixture\nKUBE_SERVER=https://fixture:6443\n"
            "NAMESPACE=fixture\n"
        )
        result = self.run_command("argocd")
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires --env prod", result.stderr)
        self.assertFalse(self.output.exists())

    def test_unknown_consumer_fails_before_child(self) -> None:
        result = self.run_command("dev")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())

    def test_compose_uses_same_database_key_names(self) -> None:
        self.dotenv.write_text(
            "DB_DATABASE=local\nDB_USERNAME=user\nDB_PASSWORD=password\nDB_PORT=5432\n"
        )
        result = self.run_command("compose")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.child()["DB_DATABASE"], "local")
        self.assertEqual(self.child()["DB_PASSWORD"], "password")

    def test_bootstrap_and_state_credentials_stay_separate(self) -> None:
        (self.root / "env.prod").write_text(
            "RUSTFS_ADMIN_ACCESS_KEY=admin-fixture\nRUSTFS_ADMIN_SECRET_KEY=admin-fixture-secret\n"
            "RUSTFS_DATA_DIR=/srv/rustfs\nRUSTFS_STATE_PATH=/srv/state/rustfs.tfstate\n"
            "RUSTFS_ENDPOINT=http://127.0.0.1:9000\nRUSTFS_BUCKET=state\nRUSTFS_REGION=us-east-1\n"
            "RUSTFS_STATE_ACCESS_KEY=state-fixture\nRUSTFS_STATE_SECRET_KEY=state-fixture-secret\n"
        )
        result = self.run_command(
            "rustfs-bootstrap",
            extra={"AWS_SECRET_ACCESS_KEY": "cloud-fixture"},
            env_name="prod",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.child()["TF_VAR_admin_access_key"], "admin-fixture")
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", self.child())
        self.assertNotIn("RUSTFS_STATE_SECRET_KEY", self.child())
        result = self.run_command("rustfs-state", env_name="prod")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.child()["RUSTFS_STATE_ACCESS_KEY"], "state-fixture")
        self.assertNotIn("TF_VAR_admin_secret_key", self.child())
        self.assertNotIn("RUSTFS_ADMIN_SECRET_KEY", self.child())

    def _state_inputs(self) -> dict[str, str]:
        return {
            "RUSTFS_ENDPOINT": "http://127.0.0.1:9000", "RUSTFS_BUCKET": "fixture",
            "RUSTFS_REGION": "us-east-1", "RUSTFS_STATE_ACCESS_KEY": "state-fixture",
            "RUSTFS_STATE_SECRET_KEY": "state-secret-fixture",
            "RUSTFS_ADMIN_ACCESS_KEY": "admin-fixture", "RUSTFS_ADMIN_SECRET_KEY": "admin-secret-fixture",
            "XDG_STATE_HOME": str(self.root / "profiles"),
        }

    def test_profile_is_private_and_stable_after_atomic_rotation(self) -> None:
        inputs = self._state_inputs()
        result = self.run_command("rustfs-state", inputs, env_name="prod")
        self.assertEqual(result.returncode, 0, result.stderr)
        credential = Path(self.child()["RUSTFS_CREDENTIALS_FILE"])
        self.assertEqual(credential.stat().st_mode & 0o777, 0o600)
        self.assertEqual(credential.parent.stat().st_mode & 0o777, 0o700)
        previous_inode = credential.stat().st_ino
        inputs["RUSTFS_STATE_SECRET_KEY"] = "rotated-fixture"
        result = self.run_command("rustfs-state", inputs, env_name="prod")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.child()["RUSTFS_CREDENTIALS_FILE"], str(credential))
        self.assertNotEqual(credential.stat().st_ino, previous_inode)
        self.assertIn("rotated-fixture", credential.read_text())

    def test_admin_profile_does_not_overwrite_state_profile(self) -> None:
        inputs = self._state_inputs()
        self.assertEqual(self.run_command("rustfs-state", inputs, env_name="prod").returncode, 0)
        credential = Path(self.child()["RUSTFS_CREDENTIALS_FILE"])
        original = credential.read_bytes()
        self.assertEqual(self.run_command("rustfs-admin", inputs, env_name="prod").returncode, 0)
        self.assertNotEqual(self.child()["RUSTFS_CREDENTIALS_FILE"], str(credential))
        self.assertEqual(credential.read_bytes(), original)
        self.assertNotIn("RUSTFS_STATE_SECRET_KEY", self.child())

    def test_insecure_profile_directory_stops_before_child(self) -> None:
        inputs = self._state_inputs()
        directory = self.root / "profiles/more-naive/rustfs"
        directory.mkdir(parents=True)
        directory.chmod(0o755)
        result = self.run_command("rustfs-state", inputs, env_name="prod")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())

    def test_multiline_credentials_fail_without_secret_output(self) -> None:
        inputs = self._state_inputs()
        inputs["RUSTFS_STATE_SECRET_KEY"] = "private-marker\n[default]"
        result = self.run_command("rustfs-state", inputs, env_name="prod")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("private-marker", result.stdout + result.stderr)
        self.assertFalse(self.output.exists())

    def test_file_is_optional_when_selected_inputs_are_in_process(self) -> None:
        self.dotenv.unlink()
        result = self.run_command(
            extra={
                "DB_URL": "jdbc:postgresql://ci/local",
                "DB_USERNAME": "ci",
                "DB_PASSWORD": "ci-fixture",
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.child()["DB_USERNAME"], "ci")

    def test_child_exit_status_is_preserved(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts/env.py"),
                "--env",
                "dev",
                "app",
                "--",
                sys.executable,
                "-c",
                "raise SystemExit(7)",
            ],
            env={"PATH": os.environ["PATH"]},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 7)

    def test_agent_without_join_token_stops_before_command(self) -> None:
        (self.root / "env.prod").write_text(
            "SSH_HOST=fixture\nSSH_USER=fixture\nSSH_KEY_FILE=/fixture/key\n"
            "KUBE_CONTEXT=fixture\nNAMESPACE=more-naive-prod\n"
            "K3S_NODE_NAME=fixture\nK3S_ROLE=agent\nK3S_SERVER_URL=https://fixture:6443\n"
        )
        result = self.run_command("k3s", env_name="prod")
        self.assertEqual(result.returncode, 2)
        self.assertIn("K3S_TOKEN", result.stderr)
        self.assertFalse(self.output.exists())

    def test_missing_executable_does_not_echo_arguments(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts/env.py"),
                "--env",
                "dev",
                "app",
                "--",
                str(self.root / "missing-command"),
                "private-argument",
            ],
            env={"PATH": os.environ["PATH"]},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 127)
        self.assertNotIn("private-argument", result.stderr + result.stdout)

    def test_argocd_has_cluster_binding_and_no_database_or_state_secrets(self) -> None:
        (self.root / "env.prod").write_text(
            "KUBE_CONTEXT=fixture\nKUBE_SERVER=https://fixture:6443\n"
            "NAMESPACE=more-naive-prod\nARGO_REPO_USERNAME=read-only\n"
            "ARGO_REPO_TOKEN=repo-fixture\nDB_PASSWORD=database-fixture\n"
            "RUSTFS_STATE_SECRET_KEY=state-fixture\n"
        )
        result = self.run_command("argocd", env_name="prod")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.child()["KUBE_SERVER"], "https://fixture:6443")
        self.assertEqual(self.child()["ARGO_REPO_TOKEN"], "repo-fixture")
        self.assertNotIn("DB_PASSWORD", self.child())
        self.assertNotIn("RUSTFS_STATE_SECRET_KEY", self.child())


if __name__ == "__main__":
    unittest.main()
