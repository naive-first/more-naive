import argparse
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "smoke", Path(__file__).with_name("smoke.py")
)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class SmokeTest(unittest.TestCase):
    def setUp(self):
        self.args = argparse.Namespace(
            environment="prod",
            namespace="more-naive-prod",
            context="prod",
            expected_server="https://prod:6443",
            url="https://fixture.tail373827.ts.net",
            allow_write=False,
            restart_backend=False,
            restart_db=False,
        )

    def test_default_only_reads(self):
        with (
            patch.object(
                smoke.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, "https://prod:6443"),
            ),
            patch.object(smoke, "api", return_value=(200, [])) as api,
        ):
            smoke.execute(self.args)
            api.assert_called_once_with(self.args.url, "GET")

    def test_other_cluster_never_calls_api(self):
        with (
            patch.object(
                smoke.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, "https://other:6443"),
            ),
            patch.object(smoke, "api") as api,
        ):
            with self.assertRaisesRegex(ValueError, "mismatch"):
                smoke.execute(self.args)
            api.assert_not_called()

    def test_bad_origin_and_restart_without_optin_do_not_call_commands(self):
        for change in [
            {"url": "http://fixture.tail373827.ts.net"},
            {"url": "https://public.example.com"},
            {"url": "https://user:pass@fixture.ts.net"},
            {"restart_backend": True},
            {"environment": "dev"},
        ]:
            args = argparse.Namespace(**(vars(self.args) | change))
            with (
                self.subTest(change=change),
                patch.object(smoke.subprocess, "run") as run,
            ):
                with self.assertRaises(ValueError):
                    smoke.execute(args)
                run.assert_not_called()

    def verify_ownership(self, fail_update):
        rows = {999: "pre-existing"}
        modified = []

        def endpoint(base, method, suffix="", value=None):
            if method == "POST":
                record_id = max(rows) + 1
                rows[record_id] = value
                modified.append(record_id)
                return 201, {"id": record_id, "value": value}
            if not suffix:
                return 200, [{"id": key, "value": value} for key, value in rows.items()]
            record_id = int(suffix[1:])
            if record_id not in rows:
                return 404, {"message": "not found"}
            if method == "PUT":
                if fail_update:
                    return 500, {"message": "fixture failure"}
                rows[record_id] = value
                modified.append(record_id)
            if method == "DELETE":
                modified.append(record_id)
                del rows[record_id]
                return 204, None
            return 200, {"id": record_id, "value": rows[record_id]}

        self.args.allow_write = True
        with (
            patch.object(
                smoke.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, "https://prod:6443"),
            ),
            patch.object(smoke, "api", side_effect=endpoint),
        ):
            if fail_update:
                with self.assertRaisesRegex(ValueError, "update"):
                    smoke.execute(self.args)
            else:
                smoke.execute(self.args)
        self.assertEqual(rows, {999: "pre-existing"})
        self.assertNotIn(999, modified)

    def test_success_cleans_only_owned_rows(self):
        self.verify_ownership(False)

    def test_partial_failure_cleans_only_owned_rows(self):
        self.verify_ownership(True)


if __name__ == "__main__":
    unittest.main()
