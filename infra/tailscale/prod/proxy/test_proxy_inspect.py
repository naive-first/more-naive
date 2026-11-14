import json
import io
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import subprocess

from inspect_proxy import inspect, REMOTE


class ProxyGuards(unittest.TestCase):
    def args(self, key, **changes):
        return SimpleNamespace(**{**dict(environment="prod", host="vm.tailnet.ts.net", user="study", key_file=str(key),
                                         expected_host="confirmed-proxy", upstream_url="", gateway_host=""), **changes})

    def key(self, directory):
        key = Path(directory) / "fixture-key"
        key.write_text("fixture, not an SSH private key")
        key.chmod(0o600)
        return key

    @patch("inspect_proxy.subprocess.check_output")
    def test_dev_and_missing_key_never_contact_ssh(self, call):
        for args in [self.args("missing", environment="dev"), self.args("missing")]:
            with self.assertRaises(ValueError):
                inspect(args)
        call.assert_not_called()

    @patch("inspect_proxy.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 22))])
    @patch("inspect_proxy.subprocess.check_output")
    def test_public_ssh_address_rejected(self, call, resolve):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                inspect(self.args(self.key(directory)))
        call.assert_not_called()

    @patch("inspect_proxy.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("100.90.91.104", 22))])
    @patch("inspect_proxy.subprocess.check_output")
    def test_query_or_credentials_in_upstream_rejected(self, call, resolve):
        with tempfile.TemporaryDirectory() as directory:
            key = self.key(directory)
            for url in ["http://name:secret@10.0.0.1/", "http://10.0.0.1/?token=secret"]:
                with self.assertRaises(ValueError):
                    inspect(self.args(key, upstream_url=url, gateway_host="api.internal"))
        call.assert_not_called()

    @patch("inspect_proxy.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("100.90.91.104", 22))])
    @patch("inspect_proxy.subprocess.check_output", return_value='{"hostname":"confirmed-proxy"}')
    def test_remote_command_keeps_hostkey_checks_and_contains_no_mutation(self, call, resolve):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn("confirmed-proxy", inspect(self.args(self.key(directory))))
        command = call.call_args.args[0]
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertIn("BatchMode=yes", command)
        self.assertIn("confirmed-proxy", json.loads(call.call_args.kwargs["input"]).values())
        self.assertNotIn("serve reset", command[-1])
        self.assertNotIn("funnel", command[-1])

    def test_remote_summary_excludes_peers_and_proxy_credentials(self):
        def read(command, **kwargs):
            if "sudo" in command:
                return subprocess.CompletedProcess(command, 0)
            body = ({"BackendState": "Running", "Self": {"DNSName": "proxy.ts.net", "TailscaleIPs": ["100.90.91.104"]},
                     "Peer": {"other": "fixture-peer-private"}} if "status" in command and "serve" not in command else
                    {"TCP": {"443": {}}, "Web": {"proxy.ts.net:443": {"Handlers": {"/": {"Proxy": "http://user:fixture-secret@localhost"}}}}})
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(body))
        payload = io.StringIO(json.dumps({"expected_host": "proxy", "user": "study", "upstream": "", "gateway_host": ""}))
        output = io.StringIO()
        with patch("sys.stdin", payload), patch("socket.gethostname", return_value="proxy"), \
             patch("pwd.getpwuid", return_value=SimpleNamespace(pw_name="study")), \
             patch("subprocess.run", side_effect=read), redirect_stdout(output):
            exec(compile(REMOTE, "proxy-remote", "exec"), {})
        summary = json.loads(output.getvalue())
        self.assertEqual(summary["serve_tcp_ports"], ["443"])
        self.assertNotIn("fixture-peer-private", output.getvalue())
        self.assertNotIn("fixture-secret", output.getvalue())


if __name__ == "__main__":
    unittest.main()
