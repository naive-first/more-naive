#!/usr/bin/env python3
"""prod 대상과 opt-in을 확인한 뒤 직접 만든 test 행만 검증한다."""

import argparse
import json
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid


def api(base, method, suffix="", value=None):
    payload = json.dumps({"value": value}).encode() if value is not None else None
    request = Request(
        base.rstrip("/") + "/api/tests" + suffix,
        data=payload,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        response = urlopen(request, timeout=20)
    except HTTPError as error:
        response = error
    with response:
        body = response.read()
        status = response.status
    print(f"{method} /api/tests{suffix}: {status}")
    return status, json.loads(body) if body else None


def execute(args):
    parsed = urlsplit(args.url)
    if args.environment != "prod" or args.namespace != "more-naive-prod":
        raise ValueError("explicit prod and more-naive-prod namespace required")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".ts.net")
    ):
        raise ValueError("tailnet HTTPS URL required")
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ["", "/"]
    ):
        raise ValueError(
            "use the HTTPS origin without credentials, path, query or fragment"
        )
    if (args.restart_backend or args.restart_db) and not args.allow_write:
        raise ValueError("Pod restart requires explicit --allow-write")
    if not args.context or not args.expected_server.startswith("https://"):
        raise ValueError("prod context and HTTPS Kubernetes API required")
    kubectl = ["kubectl", "--context", args.context]
    actual = subprocess.run(
        [
            *kubectl,
            "config",
            "view",
            "--minify",
            "-o",
            "jsonpath={.clusters[0].cluster.server}",
        ],
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    if actual != args.expected_server:
        raise ValueError("context API endpoint mismatch")
    status, rows = api(args.url, "GET")
    if status != 200 or not isinstance(rows, list):
        raise ValueError("test list is not ready")
    if not args.allow_write:
        print("read-only verification passed; no rows or Pods changed")
        return
    owned = set()
    try:
        records = []
        for label in ["target", "control"]:
            value = f"smoke-{uuid.uuid4()}-{label}"
            status, record = api(args.url, "POST", value=value)
            if (
                status != 201
                or not isinstance(record, dict)
                or not isinstance(record.get("id"), int)
            ):
                raise ValueError(
                    "create failed; inspect request outcome before retrying"
                )
            owned.add(record["id"])
            if record.get("value") != value:
                raise ValueError("created value differs")
            records.append(record)
        target, control = records
        suffix = f"/{target['id']}"
        changed = f"smoke-{uuid.uuid4()}-updated"
        if api(args.url, "PUT", suffix, changed) != (
            200,
            {"id": target["id"], "value": changed},
        ):
            raise ValueError("update contract mismatch")
        for enabled, resource in [
            (args.restart_backend, "deployment/backend"),
            (args.restart_db, "statefulset/postgres"),
        ]:
            if enabled:
                subprocess.run(
                    [*kubectl, "-n", args.namespace, "rollout", "restart", resource],
                    check=True,
                )
                subprocess.run(
                    [
                        *kubectl,
                        "-n",
                        args.namespace,
                        "rollout",
                        "status",
                        resource,
                        "--timeout=300s",
                    ],
                    check=True,
                )
        if api(args.url, "GET", suffix) != (
            200,
            {"id": target["id"], "value": changed},
        ):
            raise ValueError("readback/persistence contract mismatch")
        if api(args.url, "GET", f"/{control['id']}") != (200, control):
            raise ValueError("control row was changed")
        if api(args.url, "DELETE", suffix) != (204, None):
            raise ValueError("delete contract mismatch")
        owned.remove(target["id"])
        for method in ["GET", "DELETE"]:
            if api(args.url, method, suffix)[0] != 404:
                raise ValueError("deleted row must return 404")
        print("owned-row CRUD/persistence verification passed")
    finally:
        remaining = []
        for record_id in sorted(owned):
            try:
                if api(args.url, "DELETE", f"/{record_id}")[0] not in [204, 404]:
                    remaining.append(record_id)
            except Exception:
                remaining.append(record_id)
        if remaining:
            raise ValueError(
                f"cleanup failed; only these owned row IDs need cleanup: {remaining}"
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--namespace", default="more-naive-prod")
    parser.add_argument("--context", required=True)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--restart-backend", action="store_true")
    parser.add_argument("--restart-db", action="store_true")
    try:
        execute(parser.parse_args())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"smoke stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
