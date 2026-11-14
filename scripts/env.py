#!/usr/bin/env python3
"""선택한 루트 env.dev/env.prod에서 실행 목적에 필요한 입력만 전달한다."""

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


DATABASE_KEYS = ("DATABASE", "USERNAME", "PASSWORD")
SSH_KEYS = ("SSH_HOST", "SSH_USER", "SSH_KEY_FILE")
CONSUMERS: dict[str, tuple[str, ...]] = {
    "app": ("DB_URL", "DB_USERNAME", "DB_PASSWORD"),
    "compose": tuple(f"DB_{key}" for key in DATABASE_KEYS) + ("DB_PORT",),
    "cluster-config": tuple(f"DB_{key}" for key in DATABASE_KEYS)
    + ("KUBE_CONTEXT", "KUBE_SERVER", "NAMESPACE"),
    "argocd": ("KUBE_CONTEXT", "KUBE_SERVER", "NAMESPACE"),
    "rustfs-bootstrap": (
        "RUSTFS_ADMIN_ACCESS_KEY",
        "RUSTFS_ADMIN_SECRET_KEY",
        "RUSTFS_DATA_DIR",
        "RUSTFS_STATE_PATH",
        "RUSTFS_ENDPOINT",
    ),
    "rustfs-state": (
        "RUSTFS_ENDPOINT",
        "RUSTFS_BUCKET",
        "RUSTFS_REGION",
        "RUSTFS_STATE_ACCESS_KEY",
        "RUSTFS_STATE_SECRET_KEY",
    ),
    "rustfs-admin": (
        "RUSTFS_ENDPOINT",
        "RUSTFS_BUCKET",
        "RUSTFS_REGION",
        "RUSTFS_ADMIN_ACCESS_KEY",
        "RUSTFS_ADMIN_SECRET_KEY",
    ),
    "k3s": SSH_KEYS + ("KUBE_CONTEXT", "NAMESPACE", "K3S_NODE_NAME", "K3S_ROLE"),
    "tailscale-node": SSH_KEYS + ("TAILSCALE_NODE_NAME",),
    "tailscale-proxy": (
        "PROXY_SSH_HOST",
        "PROXY_SSH_USER",
        "PROXY_SSH_KEY_FILE",
        "PROXY_HTTPS_HOSTNAME",
        "ISTIO_UPSTREAM_URL",
        "KUBE_CONTEXT",
    ),
}
OPTIONAL_KEYS: dict[str, tuple[str, ...]] = {
    "argocd": ("ARGO_REPO_USERNAME", "ARGO_REPO_TOKEN"),
    "rustfs-bootstrap": ("RUSTFS_NAME", "RUSTFS_ALLOW_DESTROY"),
    "rustfs-state": ("RUSTFS_STATE_UNIT",),
    "rustfs-admin": ("RUSTFS_STATE_UNIT",),
    "k3s": ("K3S_SERVER_URL", "K3S_TOKEN"),
    "tailscale-node": ("TAILSCALE_AUTH_KEY", "TAILSCALE_TAGS"),
}
CONSUMERS["argocd-terraform"] = CONSUMERS["argocd"] + CONSUMERS["rustfs-state"]
OPTIONAL_KEYS["argocd-terraform"] = OPTIONAL_KEYS["argocd"]
RENAMES = {
    "rustfs-bootstrap": {
        "RUSTFS_ADMIN_ACCESS_KEY": "TF_VAR_admin_access_key",
        "RUSTFS_ADMIN_SECRET_KEY": "TF_VAR_admin_secret_key",
    },
}
PROCESS_KEYS = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TMP",
    "TEMP",
    "JAVA_HOME",
    "SystemRoot",
    "ComSpec",
    "PATHEXT",
)
DOCKER_KEYS = ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")


def read_dotenv(dotenv: Path) -> dict[str, str]:
    if not dotenv.exists():
        return {}
    values: dict[str, str] = {}
    for number, line in enumerate(dotenv.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*(.*)", line)
        if match is None:
            raise ValueError(f"invalid dotenv syntax at line {number}")
        key, value = match.groups()
        if key in values:
            raise ValueError(f"duplicate dotenv key at line {number}")
        if value.startswith(("'", '"')):
            quote = value[0]
            if len(value) < 2 or value[-1] != quote or quote in value[1:-1]:
                raise ValueError(f"invalid quoted value at line {number}")
            value = value[1:-1]
        if "\x00" in value:
            raise ValueError(f"invalid dotenv value at line {number}")
        values[key] = value
    return values


def _prepare_rustfs_credentials(environment: dict[str, str], consumer: str) -> None:
    endpoint = urlsplit(environment["RUSTFS_ENDPOINT"])
    if (endpoint.scheme not in ("http", "https") or not endpoint.hostname
            or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment):
        raise ValueError("RUSTFS_ENDPOINT must be an explicit http(s) URL")
    if endpoint.scheme == "http" and endpoint.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("HTTP backend is allowed only on loopback")
    prefix = "RUSTFS_ADMIN" if consumer == "rustfs-admin" else "RUSTFS_STATE"
    if any(any(char in value for char in "\r\n\x00") for value in environment.values()):
        raise ValueError("RustFS inputs must be single-line values")
    base = Path(environment.get("XDG_STATE_HOME", str(Path(environment["HOME"]) / ".local/state")))
    if not base.is_absolute():
        raise ValueError("credential state directory must be absolute")
    directory = base / "more-naive/rustfs"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.stat().st_mode & 0o077 or directory.stat().st_uid != os.getuid():
        raise ValueError("credential directory must be owned by the current user with mode 0700")
    identity = hashlib.sha256((environment["RUSTFS_ENDPOINT"] + environment["RUSTFS_BUCKET"]).encode()).hexdigest()[:16]
    destination = directory / f"{identity}-{consumer}.credentials"
    descriptor, temporary = tempfile.mkstemp(prefix=".credentials-", dir=directory)
    try:
        with os.fdopen(descriptor, "w") as output:
            for section in ("more-naive-state", "profile more-naive-state"):
                output.write(f"[{section}]\naws_access_key_id = {environment[prefix + '_ACCESS_KEY']}\n"
                             f"aws_secret_access_key = {environment[prefix + '_SECRET_KEY']}\n\n")
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    environment["RUSTFS_CREDENTIALS_FILE"] = str(destination)
    environment["AWS_EC2_METADATA_DISABLED"] = "true"


def build_environment(consumer: str, environment: str) -> dict[str, str]:
    if environment not in ("dev", "prod"):
        raise ValueError("environment must be dev or prod")
    if consumer not in CONSUMERS:
        raise ValueError("unknown consumer")
    if environment == "dev" and consumer not in ("app", "compose"):
        raise ValueError(f"{consumer} requires --env prod")
    required = CONSUMERS[consumer]
    selected = required + OPTIONAL_KEYS.get(consumer, ())
    values = read_dotenv(Path(__file__).resolve().parent.parent / f"env.{environment}")
    inputs = {key: os.environ.get(key, values.get(key, "")) for key in selected}
    missing = [key for key in required if not inputs[key].strip()]
    if missing:
        raise ValueError("missing required inputs: " + ", ".join(missing))
    if consumer == "k3s" and inputs["K3S_ROLE"] == "agent":
        if not inputs["K3S_SERVER_URL"].strip() or not inputs["K3S_TOKEN"].strip():
            raise ValueError("agent requires K3S_SERVER_URL and K3S_TOKEN")
    process_keys = PROCESS_KEYS
    if consumer in ("app", "compose", "rustfs-bootstrap"):
        process_keys += DOCKER_KEYS
    if consumer in ("cluster-config", "argocd", "argocd-terraform", "k3s", "tailscale-proxy"):
        process_keys += ("KUBECONFIG",)
    if consumer.startswith("rustfs-"):
        os.umask(0o077)
        process_keys += ("XDG_STATE_HOME", "TG_DOWNLOAD_DIR", "TG_NO_COLOR", "TG_NON_INTERACTIVE", "TG_LOG_LEVEL")
    child_environment = {
        key: os.environ[key] for key in process_keys if key in os.environ
    }
    renames = RENAMES.get(consumer, {})
    child_environment.update(
        {renames.get(key, key): value for key, value in inputs.items() if value}
    )
    if consumer in ("rustfs-state", "rustfs-admin"):
        _prepare_rustfs_credentials(child_environment, consumer)
    if consumer == "argocd-terraform":
        os.umask(0o077)
        keys = ("XDG_STATE_HOME", "TG_DOWNLOAD_DIR", "TG_NO_COLOR", "TG_NON_INTERACTIVE", "TG_LOG_LEVEL")
        child_environment.update({key: os.environ[key] for key in keys if key in os.environ})
        _prepare_rustfs_credentials(child_environment, "rustfs-state")
        child_environment["RUSTFS_STATE_UNIT"] = "argocd"
    return child_environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("dev", "prod"), required=True)
    parser.add_argument("consumer", choices=CONSUMERS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after --")
    try:
        environment = build_environment(args.consumer, args.env)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"env: {error}", file=sys.stderr)
        return 2
    try:
        return subprocess.run(command, env=environment).returncode
    except OSError:
        print("env: could not start child command", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main())
