import argparse
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("bootstrap", Path(__file__).with_name("bootstrap.py"))
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapGuardTest(unittest.TestCase):
    def setUp(self):
        self.key = tempfile.NamedTemporaryFile()
        self.addCleanup(self.key.close)
        self.args = argparse.Namespace(environment="prod", node="prod-node", user="study",
                                       key_file=self.key.name, role="server", host="node.ts.net", apply=True)

    def test_dev_never_contacts_ssh(self):
        self.args.environment = "dev"
        with patch.object(bootstrap.subprocess, "run") as ssh:
            with self.assertRaisesRegex(ValueError, "prod"):
                bootstrap.execute(self.args)
            ssh.assert_not_called()

    def test_missing_token_never_contacts_ssh(self):
        with patch.dict(bootstrap.os.environ, {}, clear=True), patch.object(bootstrap.subprocess, "run") as ssh:
            with self.assertRaisesRegex(ValueError, "K3S_TOKEN"):
                bootstrap.execute(self.args)
            ssh.assert_not_called()

    def test_public_or_mixed_dns_rejected(self):
        tailnet = (2, 1, 6, "", ("100.90.91.104", 22))
        public = (2, 1, 6, "", ("8.8.8.8", 22))
        for answers in [[public], [tailnet, public]]:
            with self.subTest(answers=answers), patch.object(bootstrap.socket, "getaddrinfo", return_value=answers):
                with self.assertRaisesRegex(ValueError, "tailnet"):
                    bootstrap.tailnet_host("node.ts.net")

    def test_wrong_remote_hostname_never_installs(self):
        reply = argparse.Namespace(stdout='study\nwrong-node\n{"BackendState":"Running"}')
        with patch.dict(bootstrap.os.environ, {"K3S_TOKEN": "test-only-token"}), \
             patch.object(bootstrap, "tailnet_host"), \
             patch.object(bootstrap.subprocess, "run", return_value=reply) as ssh:
            with self.assertRaisesRegex(ValueError, "does not match"):
                bootstrap.execute(self.args)
            self.assertEqual(ssh.call_count, 1)
            self.assertNotIn("test-only-token", str(ssh.call_args))

    def test_preflight_does_not_install(self):
        self.args.apply = False
        reply = argparse.Namespace(stdout='study\nprod-node\n{"BackendState":"Running"}')
        with patch.dict(bootstrap.os.environ, {"K3S_TOKEN": "test-only-token"}), \
             patch.object(bootstrap, "tailnet_host"), \
             patch.object(bootstrap.subprocess, "run", return_value=reply) as ssh:
            bootstrap.execute(self.args)
            self.assertEqual(ssh.call_count, 1)


if __name__ == "__main__":
    unittest.main()
