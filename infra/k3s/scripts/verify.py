#!/usr/bin/env python3
"""Verify the explicit prod cluster and optionally create disposable network probes."""
import argparse
import json
import secrets
import subprocess


def verify(args):
    if args.environment != "prod" or args.context != "more-naive-prod":
        raise ValueError("explicit prod/more-naive-prod is required")
    if not args.expected_server.startswith("https://") or not args.node or len(set(args.node)) != len(args.node):
        raise ValueError("expected HTTPS API server and unique node names are required")
    kubectl = ["kubectl", "--context", args.context, "--request-timeout=30s"]

    def run(*command):
        return subprocess.check_output([*kubectl, *command], text=True, timeout=180)

    config = json.loads(run("config", "view", "--minify", "-o", "json"))
    if config["clusters"][0]["cluster"]["server"] != args.expected_server:
        raise ValueError("API server differs; no probe created")
    nodes = json.loads(run("get", "nodes", "-o", "json"))["items"]
    if {node["metadata"]["name"] for node in nodes} != set(args.node):
        raise ValueError("node inventory differs; no probe created")
    for node in args.node:
        run("wait", "node/" + node, "--for=condition=Ready", "--timeout=120s")
    print("PASS: context, API server, exact node inventory, and Ready")
    if not args.write_smoke:
        print("DNS/Pod communication NOT_RUN; pass --write-smoke for disposable probes")
        return
    namespace = "more-naive-network-" + secrets.token_hex(5)
    run("create", "namespace", namespace)
    try:
        pods = []
        for index, node in enumerate(args.node):
            name = "probe-" + str(index)
            overrides = {"spec": {"nodeName": node, "automountServiceAccountToken": False,
                                  "securityContext": {"runAsUser": 1000, "runAsGroup": 1000}}}
            run("-n", namespace, "run", name, "--image=busybox:1.37.0", "--restart=Never", "--overrides=" + json.dumps(overrides),
                "--command", "--", "sh", "-ec", "mkdir /tmp/www; echo ok >/tmp/www/index.html; httpd -f -p 8080 -h /tmp/www")
            run("-n", namespace, "wait", "pod/" + name, "--for=condition=Ready", "--timeout=120s")
            pod = json.loads(run("-n", namespace, "get", "pod", name, "-o", "json"))
            pods.append((name, pod["status"]["podIP"]))
        for name, _ in pods:
            run("-n", namespace, "exec", name, "--", "nslookup", "kubernetes.default.svc.cluster.local")
            for _, address in pods:
                host = "[" + address + "]" if ":" in address else address
                if run("-n", namespace, "exec", name, "--", "wget", "-qO-", "-T", "10", f"http://{host}:8080").strip() != "ok":
                    raise ValueError("unexpected peer HTTP result")
        print(f"PASS: DNS on {len(pods)} nodes and {len(pods) ** 2} Pod HTTP paths")
    finally:
        run("delete", "namespace", namespace, "--wait=true", "--timeout=120s")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument("--node", action="append", required=True)
    parser.add_argument("--write-smoke", action="store_true")
    try:
        verify(parser.parse_args())
    except (ValueError, KeyError, subprocess.SubprocessError, OSError) as error:
        parser.exit(1, f"verification stopped: {type(error).__name__}: {error}\n")


if __name__ == "__main__":
    main()
