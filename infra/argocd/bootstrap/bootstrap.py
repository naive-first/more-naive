#!/usr/bin/env python3
"""고정 Helm values로 Argo CD를 설치하고 prod root만 등록한다."""

import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
CHART = "oci://ghcr.io/argoproj/argo-helm/argo-cd"
CHART_VERSION = "10.18.0"


def run(command, **options):
    return subprocess.run(command, check=True, text=True, **options)


def execute(args):
    if args.environment != "prod" or not args.context or not args.expected_server.startswith("https://"):
        raise ValueError("explicit prod context and HTTPS API endpoint required")
    kubectl = ["kubectl", "--context", args.context]
    endpoint = run([*kubectl, "config", "view", "--minify", "-o",
                    "jsonpath={.clusters[0].cluster.server}"], capture_output=True).stdout
    if endpoint != args.expected_server:
        raise ValueError("context API endpoint mismatch")
    values = ROOT / "infra/environments/prod/argocd.yaml"
    run(["helm", "template", "argocd", CHART, "--version", CHART_VERSION,
         "--namespace", "argocd", "--values", str(values)], stdout=subprocess.DEVNULL)
    if not args.apply:
        print("prod context/endpoint and chart rendering verified; no cluster writes")
        return
    for name in ["argocd", "istio-system", "more-naive-prod"]:
        namespace = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": name}}
        run([*kubectl, "apply", "-f", "-"], input=json.dumps(namespace), stdout=subprocess.DEVNULL)
    token = os.environ.get("ARGO_REPO_TOKEN")
    if token:
        secret = {"apiVersion": "v1", "kind": "Secret", "metadata": {
            "name": "more-naive-repository", "namespace": "argocd",
            "labels": {"argocd.argoproj.io/secret-type": "repository"}},
            "data": {key: base64.b64encode(value.encode()).decode() for key, value in {
                "type": "git", "url": "https://github.com/naive-first/more-naive.git",
                "username": os.environ.get("ARGO_REPO_USERNAME", "x-access-token"), "password": token}.items()}}
        # Secret의 렌더링/오류 본문은 로그에 출력하지 않는다.
        result = subprocess.run([*kubectl, "apply", "--server-side", "--field-manager=more-naive-bootstrap", "-f", "-"],
                                input=json.dumps(secret), text=True, capture_output=True)
        if result.returncode:
            raise ValueError("repository credential injection failed (details suppressed)")
    run(["helm", "upgrade", "--install", "argocd", CHART, "--version", CHART_VERSION,
         "--namespace", "argocd", "--kube-context", args.context, "--values", str(values),
         "--wait", "--timeout", "10m"])
    for resource in ["deployment/argocd-server", "deployment/argocd-repo-server", "statefulset/argocd-application-controller"]:
        run([*kubectl, "-n", "argocd", "rollout", "status", resource, "--timeout=300s"])
    project = ROOT / "infra/argocd/bootstrap/prod/project.yaml"
    if project.exists():
        run([*kubectl, "apply", "-f", str(project)])
    run([*kubectl, "apply", "-f", str(ROOT / "infra/argocd/projects/prod")])
    stages = [
        ("istio-base", "istio-system", "crd/gateways.networking.istio.io", "Established"),
        ("istiod", "istio-system", "deployment/istiod", "Available"),
        ("istio-gateway", "istio-system", "deployment/istio-ingressgateway", "Available"),
        ("postgres", "more-naive-prod", "statefulset/postgres", None),
        ("backend", "more-naive-prod", "deployment/backend", "Available"),
    ]
    for name, namespace, resource, condition in stages:
        declaration = ROOT / f"infra/argocd/applications/prod/{name}.yaml"
        if not declaration.exists():
            continue
        run([*kubectl, "apply", "-f", str(declaration)])
        for field, value in [("sync.status", "Synced"), ("health.status", "Healthy")]:
            run([*kubectl, "-n", "argocd", "wait", f"application/{name}",
                 f"--for=jsonpath={{.status.{field}}}={value}", "--timeout=600s"])
        if condition:
            run([*kubectl, "-n", namespace, "wait", resource, f"--for=condition={condition}", "--timeout=300s"])
        else:
            run([*kubectl, "-n", namespace, "rollout", "status", resource, "--timeout=300s"])
    run([*kubectl, "apply", "-f", str(ROOT / "infra/argocd/bootstrap/prod/root.yaml")])
    run([*kubectl, "-n", "argocd", "wait", "application/more-naive-prod",
         "--for=jsonpath={.status.sync.status}=Synced", "--timeout=300s"])
    print("Argo CD Ready and prod root Synced")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument("--apply", action="store_true")
    try:
        execute(parser.parse_args())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"Argo bootstrap stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
