import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from verify import verify


class VerifyGuardTests(unittest.TestCase):
    def args(self, **changes):
        values = dict(environment="prod", context="more-naive-prod", expected_server="https://100.90.1.2:6443",
                      node=["server"], write_smoke=False)
        return SimpleNamespace(**{**values, **changes})

    def result(self, command, **kwargs):
        if "config" in command:
            return json.dumps({"clusters": [{"cluster": {"server": "https://100.90.1.2:6443"}}]})
        if "nodes" in command:
            return json.dumps({"items": [{"metadata": {"name": "server"}}]})
        return ""

    @patch("verify.subprocess.check_output")
    def test_dev_and_wrong_context_never_contact_cluster(self, call):
        for args in [self.args(environment="dev"), self.args(context="default")]:
            with self.assertRaises(ValueError):
                verify(args)
        call.assert_not_called()

    @patch("verify.subprocess.check_output")
    def test_wrong_server_never_creates_namespace(self, call):
        call.side_effect = self.result
        with self.assertRaises(ValueError):
            verify(self.args(expected_server="https://100.90.9.9:6443", write_smoke=True))
        self.assertEqual(call.call_count, 1)

    @patch("verify.subprocess.check_output")
    def test_wrong_inventory_never_creates_namespace(self, call):
        call.side_effect = self.result
        with self.assertRaises(ValueError):
            verify(self.args(node=["other"], write_smoke=True))
        self.assertEqual(call.call_count, 2)

    @patch("verify.subprocess.check_output")
    def test_without_opt_in_only_checks_context_nodes_and_ready(self, call):
        call.side_effect = self.result
        verify(self.args())
        self.assertEqual(call.call_count, 3)
        self.assertFalse(any("create" in invocation.args[0] for invocation in call.call_args_list))

    @patch("verify.secrets.token_hex", return_value="owned")
    @patch("verify.subprocess.check_output")
    def test_failed_probe_cleans_only_owned_namespace(self, call, token):
        def respond(command, **kwargs):
            if "run" in command:
                raise OSError("probe unavailable")
            return self.result(command, **kwargs)
        call.side_effect = respond
        with self.assertRaises(OSError):
            verify(self.args(write_smoke=True))
        final = call.call_args_list[-1].args[0]
        self.assertIn("delete", final)
        self.assertIn("more-naive-network-owned", final)


if __name__ == "__main__":
    unittest.main()
