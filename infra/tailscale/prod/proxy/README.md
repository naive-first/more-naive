# prod Istio 사설 릴레이

Proxmox의 `more-naive-vm.tail373827.ts.net:443`이 TLS를 종료하고 원래 Host와 경로를 `172.30.104.10:18080`으로 보냅니다. VM의 `more-naive-gateway-relay.service`는 이 IPv4 주소에만 바인딩하고 `istio-system/service/istio-ingressgateway` 포트 80으로 전달합니다.

[prod GitOps 라우트와 Helm URL](../../../argocd/README.md#tailnet의-argocd-경로-적용)을 먼저 확인합니다. 릴레이 설치는 SSH 대상 VM에 사설 IP가 할당돼 있고 k3s와 Istio ingress Deployment 및 `/api/tests`가 준비된 뒤 실행합니다. `env.prod`에 표준 SSH 값과 `PROXY_EXPECTED_HOST=more-naive-vm`을 설정합니다. 프로비저닝은 Istio prod values에서 Host를 읽습니다. 기존 `PROXY_HTTPS_HOSTNAME=more-naive-vm.tail373827.ts.net`은 운영 점검과 smoke에서 사용합니다.

```bash
umask 077
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale-proxy run -- init -input=false
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale-proxy run -- plan -input=false -out=/absolute/private/tailscale-proxy.tfplan
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale-proxy run -- apply -input=false /absolute/private/tailscale-proxy.tfplan
```

기존 `more-naive/prod/tailscale-proxy/terraform.tfstate`와 `terraform_data.proxy`를 사용합니다. 전환 계획에서 이 프로비저닝 marker만 교체됩니다. 프로비저닝은 기존 unit이 알려진 loopback 버전 또는 새 사설 버전과 일치하는지 확인합니다. 현재 VM의 `10-private-listener.conf`가 새 unit과 같은 명령을 설정하면 그대로 두고, 사설 주소에서 이미 동작하는 릴레이를 재시작하지 않습니다. 새 VM은 unit으로 사설 주소에 직접 바인딩합니다.

```bash
MORE_NAIVE_ENV=prod direnv exec config/env bash infra/tailscale/prod/proxy/inspect_proxy.sh
```

운영 점검은 VM의 사설 바인딩과 Host 기반 내부 HTTP `/api/tests`·`/argocd/`를 검사하고, 실행자 쪽 tailnet HTTPS에서도 동일한 두 경로의 200을 확인합니다. 장애 시 VM의 주소 및 `journalctl -u more-naive-gateway-relay.service`, ingress Pod/Service, Proxmox 포워딩을 차례로 확인합니다. 선택한 Pod가 종료되면 systemd가 포트 포워딩을 다시 시작합니다. [kubectl port-forward 문서](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_port-forward/)
