# prod k3s bootstrap

Terraform 1.17.2의 `terraform_data`와 `file`/`remote-exec` provisioner로 고정 k3s `v1.35.10+k3s1`을 설치합니다. `scripts/preflight.sh`는 DNS·SSH 사용자·hostname·관리 호스트의 Tailscale Running/peer 도달·sudo 권한만 읽어서 확인합니다. 관리 호스트의 Bash·dig·jq·OpenSSH·Tailscale 기본 도구를 사용하며 운영에 Python이 필요하지 않습니다.

운영자가 대상 SSH 주소의 tailnet 연결, owner-only SSH 개인키와 known_hosts, 신뢰한 **서버 host public key**를 먼저 준비합니다. `env.prod`의 공통 `SSH_HOST`, `SSH_USER`, `SSH_KEY_FILE`, `SSH_HOST_KEY`, `K3S_NODE_NAME`, `K3S_ROLE`, `K3S_TOKEN`을 사용합니다. `SSH_HOST_KEY`는 개인키나 known_hosts 전체 행이 아닌 `ssh-ed25519 AAAA…` 형태의 서버 공개키입니다. 검증하지 않은 ssh-keyscan 결과를 그대로 신뢰하지 않습니다. agent에는 `K3S_SERVER_URL=https://<사설 server>:6443`도 필요합니다.

RustFS의 기존 버킷·전용 state 인증을 준비한 후 저장소 루트에서 실행합니다. 이 unit은 `more-naive/prod/k3s/terraform.tfstate`를 사용하며 bootstrap local state를 이전하지 않습니다.

```bash
umask 077
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/k3s run -- init -input=false
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/k3s run -- plan -input=false -out=/absolute/private/k3s.tfplan
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/k3s run -- apply -input=false /absolute/private/k3s.tfplan
```

대상은 운영자가 정한 실제 k3s 노드입니다. 제공 VM `system-design-study`의 prod 설치가 승인됐습니다. Tailscale gateway가 SSH를 VM으로 전달하는 경로도 지원하며, 관리 호스트에서 peer 도달을 확인하고 VM의 host key·hostname·sudo를 대조합니다. VM 내부 Tailscale 데몬은 요구하지 않습니다. direnv의 표준 dotenv로 읽고 env 파일을 shell source하지 않으며 token/private key는 argv·Git·로그에 쓰지 않습니다. Terraform ephemeral 변수와 connection으로 전달하므로 plan/state에 저장하지 않습니다. 원격 전송 파일은 사용자 전용 임시 디렉터리에 쓰고 root 설치 단계에서 정리합니다.

server는 Traefik·ServiceLB를 비활성화하고 kubeconfig·token을 0600으로 저장합니다. 고정 installer SHA256을 검증한 후 설치합니다. 매 apply는 실행 기록을 교체하며 기존 설치의 버전·기본 구성·token·서비스 일치를 다시 확인합니다. 기존 값이 다르면 중단합니다. 일치하는 prod server에서는 [TLS SAN drop-in](config/prod/README.md)을 관리하고, 파일 내용이 달라진 경우에만 k3s를 재시작합니다. 따라서 재실행 plan에는 `terraform_data` 교체가 표시됩니다. 이 자원 삭제에는 원격 uninstall 작업이 없습니다.

설치 실패 후 남은 구성은 운영자가 확인합니다. DNS/known_hosts·키 권한, 원격 사용자·hostname, `sudo -n true`, `tailscale status`, `systemctl status k3s` 순으로 진단합니다. state/plan이나 token·kubeconfig를 PR에 첨부하지 않습니다. 실제 prod 설치·Ready/DNS 확인은 별도 운영 단계이며 로컬 fixture 검증으로 완료했다고 주장하지 않습니다. uninstall·데이터/PVC 삭제·백업/복원은 포함하지 않습니다.
