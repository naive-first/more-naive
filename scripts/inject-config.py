#!/usr/bin/env python3
"""prod 앱/DB 설정 두 객체만 검증한 클러스터에 주입한다."""

import argparse
import base64
import json
import re
import subprocess
import sys
from urllib.parse import quote

from env import build_environment


def kubectl(
    environment: dict[str, str], arguments: list[str], payload: str | None = None
) -> str:
    command = [
        "kubectl",
        "--context",
        environment["KUBE_CONTEXT"],
        "--namespace",
        environment["NAMESPACE"],
        "--request-timeout=30s",
        *arguments,
    ]
    process_environment = {
        key: value for key, value in environment.items() if not key.startswith("DB_") and key not in ("KUBE_CONTEXT", "KUBE_SERVER", "NAMESPACE")
    }
    result = subprocess.run(
        command,
        input=payload,
        env=process_environment,
        text=True,
        capture_output=True,
        timeout=45,
    )
    if result.returncode:
        raise ValueError(
            "kubectl failed; check access, namespace and field ownership without rendering secrets"
        )
    return result.stdout


def inject(environment: dict[str, str]) -> None:
    namespace = environment["NAMESPACE"]
    if not re.fullmatch(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?", namespace):
        raise ValueError("NAMESPACE must be a Kubernetes namespace name")
    config = json.loads(
        kubectl(environment, ["config", "view", "--minify", "-o", "json"])
    )
    clusters = config.get("clusters", [])
    if (
        len(clusters) != 1
        or clusters[0].get("cluster", {}).get("server")
        != environment["KUBE_SERVER"]
    ):
        raise ValueError("selected context server differs from KUBE_SERVER")
    selected_namespace = json.loads(
        kubectl(environment, ["get", "namespace", namespace, "-o", "json"])
    )
    if selected_namespace.get("metadata", {}).get("name") != namespace:
        raise ValueError("namespace identity could not be verified")
    config_data = {
        "DB_DATABASE": environment["DB_DATABASE"],
        "DB_USERNAME": environment["DB_USERNAME"],
        "DB_URL": f"jdbc:postgresql://postgres.{namespace}.svc.cluster.local:5432/"
        + quote(environment["DB_DATABASE"], safe=""),
    }
    secret_data = {
        "DB_PASSWORD": base64.b64encode(
            environment["DB_PASSWORD"].encode()
        ).decode()
    }
    objects = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "more-naive-config", "namespace": namespace},
            "data": config_data,
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {"name": "more-naive-db", "namespace": namespace},
            "data": secret_data,
        },
    ]
    kubectl(
        environment,
        ["apply", "--server-side", "--field-manager=more-naive-config", "-f", "-"],
        json.dumps({"apiVersion": "v1", "kind": "List", "items": objects}),
    )
    for kind, name, expected in (
        ("configmap", "more-naive-config", config_data),
        ("secret", "more-naive-db", secret_data),
    ):
        actual = json.loads(kubectl(environment, ["get", kind, name, "-o", "json"]))
        if actual.get("data") != expected:
            raise ValueError(f"{kind} {name} readback differs; values suppressed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=("prod",))
    parser.add_argument("--context", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--apply", action="store_true", required=True)
    args = parser.parse_args()
    try:
        environment = build_environment("cluster-config", "prod")
        if (
            args.context != environment["KUBE_CONTEXT"]
            or args.namespace != environment["NAMESPACE"]
        ):
            raise ValueError("explicit context/namespace differs from prod inputs")
        inject(environment)
    except (
        OSError,
        UnicodeError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.TimeoutExpired,
    ) as error:
        if isinstance(error, ValueError) and not isinstance(
            error, (json.JSONDecodeError, UnicodeError)
        ):
            print(f"config: {error}", file=sys.stderr)
        else:
            print(
                "config: input/cluster response failed; values suppressed",
                file=sys.stderr,
            )
        return 2
    print("verified: prod more-naive-config and more-naive-db; values suppressed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
