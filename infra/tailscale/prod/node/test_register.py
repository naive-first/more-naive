import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from register import register


class RegistrationGuards(unittest.TestCase):
    def args(self, **changes):
        return SimpleNamespace(**{**dict(environment="prod", expected_host="prod-node", node_name="prod-node",
                                         os_user="study", tag=[], apply=False, policy_reviewed=False), **changes})

    @patch("register.socket.gethostname", return_value="prod-node")
    @patch("register.subprocess.check_output")
    def test_environment_and_host_guard(self, call, hostname):
        for args in [self.args(environment="dev"), self.args(expected_host="other")]:
            with self.assertRaises(ValueError):
                register(args)
        call.assert_not_called()

    @patch("register.socket.gethostname", return_value="prod-node")
    @patch("register.pwd.getpwnam")
    @patch("register.shutil.which", return_value="/usr/bin/tailscale")
    @patch("register.subprocess.check_output")
    @patch("register.subprocess.run")
    def test_existing_node_never_rejoins(self, run, status, which, user, hostname):
        status.return_value = json.dumps({"BackendState": "Running", "Self": {"HostName": "prod-node", "ID": "existing"}})
        register(self.args(apply=True))
        run.assert_not_called()

    @patch("register.socket.gethostname", return_value="prod-node")
    @patch("register.pwd.getpwnam")
    @patch("register.shutil.which", return_value="/usr/bin/tailscale")
    @patch("register.subprocess.check_output")
    @patch("register.subprocess.run")
    def test_expired_existing_node_stops(self, run, status, which, user, hostname):
        status.return_value = json.dumps({"BackendState": "NeedsLogin", "Self": {"ID": "existing"}})
        with self.assertRaises(ValueError):
            register(self.args(apply=True, policy_reviewed=True))
        run.assert_not_called()

    @patch("register.socket.gethostname", return_value="prod-node")
    @patch("register.pwd.getpwnam")
    @patch("register.shutil.which", return_value="/usr/bin/tailscale")
    @patch("register.subprocess.check_output", return_value='{"BackendState":"NeedsLogin"}')
    @patch("register.subprocess.run")
    @patch.dict("register.os.environ", {}, clear=True)
    def test_missing_auth_key_never_registers(self, run, status, which, user, hostname):
        with self.assertRaises(ValueError):
            register(self.args(apply=True, policy_reviewed=True))
        run.assert_not_called()

    @patch("register.socket.gethostname", return_value="prod-node")
    @patch("register.pwd.getpwnam")
    @patch("register.shutil.which", return_value=None)
    @patch("register.urllib.request.urlopen")
    def test_missing_binary_preflight_never_installs(self, download, which, user, hostname):
        register(self.args())
        download.assert_not_called()

    def test_join_uses_private_temporary_file_and_removes_it(self):
        observed = []
        def submit(command, **kwargs):
            key_arg = next(value for value in command if value.startswith("--auth-key=file:"))
            key_file = Path(key_arg.removeprefix("--auth-key=file:"))
            self.assertEqual(key_file.read_text(), "fixture-join-key")
            self.assertEqual(key_file.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("fixture-join-key", " ".join(command))
            observed.append(key_file)
        with patch("register.socket.gethostname", return_value="prod-node"), \
             patch("register.pwd.getpwnam"), patch("register.shutil.which", return_value="tailscale"), \
             patch("register.subprocess.check_output", side_effect=['{"BackendState":"NeedsLogin"}', "1.104.7\n"]), \
             patch("register.subprocess.run", side_effect=submit), \
             patch.dict("register.os.environ", {"TAILSCALE_AUTH_KEY": "fixture-join-key"}, clear=True):
            register(self.args(apply=True, policy_reviewed=True))
        self.assertEqual(len(observed), 1)
        self.assertFalse(observed[0].exists())


if __name__ == "__main__":
    unittest.main()
