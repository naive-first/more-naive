# Prod tailnet HTTPS

SSH 관리 진입점은 `study@more-naive-vm.tail373827.ts.net`(100.90.91.104)입니다. 실제 Ubuntu/k3s 노드 이름은 `more-naive-vm`입니다. VM에 설치하고 로그인한 Tailscale 노드는 별도 IP `100.90.159.52`와 DNS `more-naive-vm-1.tail373827.ts.net`을 받았습니다. HTTPS에는 인증된 노드의 실제 DNS를 사용합니다.

경로는 tailnet 클라이언트 → Tailscale Serve HTTPS 443 → `127.0.0.1:18080` → Istio gateway Service:80 → Host가 일치하는 `/api/tests` backend입니다. Serve가 인증서를 관리하고 원래 Host를 전달합니다. gateway는 ClusterIP이며 Funnel·공인 LB·NodePort를 추가하지 않습니다.

## 설치와 적용

공통 `config/env/env.prod`에 실제 SSH 검증값과 `PROXY_EXPECTED_HOST=more-naive-vm`, `PROXY_HTTPS_HOSTNAME=more-naive-vm-1.tail373827.ts.net`을 설정합니다. 개인키·인증값은 저장소 밖에 보관합니다. Terraform 1.17.2·Terragrunt 1.2.2와 실행 호스트의 SSH/jq, VM의 k3s·curl·jq·systemd가 필요합니다.

Tailscale 설치도 선언된 native Terraform provisioner로 수행합니다. 고정 버전·checksum 설치와 서비스 시작은 첫 unit, HTTPS relay와 Serve 설정은 두 번째 unit이 담당합니다.

```bash
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale run -- init
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale run -- plan
# 설치 plan을 검토한 뒤 적용
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale run -- apply
```

처음 설치한 노드의 로그인은 VM 운영자가 비공개 브라우저 인증으로 완료합니다. 로그인 링크와 auth key를 PR에 남기지 않습니다. `tailscale status --json`의 Running과 Self.DNSName을 확인한 뒤, 그 DNS를 prod Gateway·VirtualService에 반영하고 Argo의 Synced/Healthy를 확인합니다.

```bash
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale-proxy run -- init
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale-proxy run -- plan
# terraform_data.proxy의 대상과 변경을 검토한 뒤 적용
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale-proxy run -- apply
```

이 unit은 `bootstrap.sh`와 relay systemd unit을 SSH file provisioner로 전달하고 remote-exec로 설치합니다. 사전 검사에서 prod·실제 OS 이름·로그인 DNS·gateway 경로·443 소유권·Funnel 비활성을 확인합니다. 기존 다른 Serve 설정과 서비스는 덮어쓰지 않습니다. HTTPS 기능 활성화 동의가 필요하면 원문은 VM `/var/lib/more-naive-proxy/serve-approval.txt`(0600)에만 저장합니다. 운영자가 비공개 링크로 동의한 뒤 plan을 다시 검토하고 apply합니다.

relay는 `kubectl port-forward --address=127.0.0.1`로만 바인딩합니다. 선택한 gateway Pod가 바뀌어 port-forward가 끝나면 systemd가 다시 연결합니다. 서비스와 Tailscale daemon은 부팅 시 시작하도록 설정합니다. VM 재부팅 후 검증은 실제 재부팅을 수행한 경우에만 완료로 기록합니다.

## 확인

```bash
MORE_NAIVE_ENV=prod direnv exec config/env bash infra/tailscale/prod/proxy/inspect_proxy.sh
curl --fail --silent --show-error --output /dev/null https://more-naive-vm-1.tail373827.ts.net/api/tests
bash -n infra/tailscale/prod/proxy/bootstrap.sh
terraform fmt -check infra/terraform/modules/tailscale-proxy
```

VM에서는 `systemctl is-active/is-enabled more-naive-gateway-relay.service`, loopback 18080 바인딩, `tailscale serve status --json`의 HTTPS 443 대상과 Funnel 비활성을 확인합니다. 전체 status·peer·kubeconfig·state 대신 필요한 필드만 기록합니다. 잘못된 Host와 API 밖 경로는 404여야 합니다. 실제 CRUD·backend/DB 재시작 영속성은 직접 만든 행만으로 검증하고 정리합니다. 운영 PVC 삭제·백업/복원은 수행하지 않습니다.

[Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)는 localhost HTTP upstream을 사용합니다. [kubectl port-forward](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_port-forward/)는 선택한 Pod 종료 시 연결도 종료하므로 systemd 재시작을 사용합니다.
