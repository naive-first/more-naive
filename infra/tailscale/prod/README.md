# prod Tailscale 접근

Tailscale이 없는 VM도 배포 경로에서 설치합니다. 고정 `1.104.7` Linux amd64 정적 배포본의 checksum을 검증하고 `more-naive-tailscaled.service`를 설치·자동 시작합니다. 기존 등록 노드는 재가입·자동 업그레이드·SSH 설정 변경을 하지 않습니다. [공식 정적 설치 문서](https://tailscale.com/docs/install/static)를 따릅니다.

## VM 설치

표준 `env.prod`의 `SSH_HOST`·`SSH_USER`·`SSH_KEY_FILE`·`SSH_HOST_KEY`·`SSH_EXPECTED_HOST`와 실제 OS 호스트명인 `TAILSCALE_EXPECTED_HOST`를 준비합니다. 현재 SSH 목적지는 `more-naive-vm.tail373827.ts.net`, OS/k3s 이름은 `more-naive-vm`입니다. `100.90.91.104`는 기존 SSH 진입 주소이며 새로 설치할 guest의 tailnet identity로 자동 이전하지 않습니다.

설치 unit은 기존 RustFS backend의 `more-naive/prod/tailscale/terraform.tfstate`를 사용합니다. RustFS 자체 bootstrap state는 기존 local 경로에 유지합니다. Terraform CLI `1.17.2`, Terragrunt `1.2.2`, Bash·OpenSSH·dig·direnv가 필요합니다. VM에는 Linux amd64·systemd·비대화 sudo와 curl·sha256sum·tar·install·jq·pgrep이 필요합니다.

```bash
umask 077
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale run -- init -input=false
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale run -- plan -input=false -out=/absolute/private/tailscale.tfplan
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale run -- apply -input=false /absolute/private/tailscale.tfplan
```

init/plan/apply 전에 실제 SSH user/hostname·tailnet 주소·기존 host key를 확인합니다. native file/remote-exec provisioner가 설치 스크립트와 systemd unit만 임시 0700 경로로 전달해 `register.sh --apply --install-only`를 실행하고 전달 파일을 정리합니다. 개인키 경로는 ephemeral 변수이며 가입 키는 Terraform 입력·plan/state에 포함하지 않습니다.

신규 설치 전 기존 state·package/managed service·daemon을 확인해 덮어쓰지 않습니다. 이미 CLI가 있으면 설치나 서비스 재시작 없이 상태만 확인합니다. 변경이 없는 후속 Terragrunt plan은 no-op입니다. 외부에서 패키지·서비스를 삭제한 경우에는 실제 상태를 확인한 뒤 설치 resource의 명시적 교체를 검토하며 자동으로 등록 identity를 재생성하지 않습니다.

## Tailnet 가입

설치와 가입은 구분합니다. `NeedsLogin`은 바이너리·daemon 설치 완료이며 tailnet 접속·Serve·HTTPS 성공이 아닙니다. 인증이 없어도 설치 단계는 완료합니다. 가입하려면 VM의 신뢰한 console에서 `TAILSCALE_EXPECTED_HOST`·`TAILSCALE_NODE_NAME`·`SSH_USER`·`TAILSCALE_TAGS`·`TAILSCALE_AUTH_KEY`를 준비하고 [정책](policies/README.md)을 검토합니다.

```bash
MORE_NAIVE_ENV=prod direnv exec config/env bash infra/tailscale/prod/node/register.sh --apply --policy-reviewed
```

이 명령은 노드에서 실행합니다. root가 필요하며 auth key는 임시 0600 파일로 전달한 뒤 삭제합니다. 키를 명령 인자·Git·로그·Terraform state에 적지 않습니다. 현재 Running인 노드는 이름을 확인한 뒤 등록이나 SSH 설정을 바꾸지 않습니다. 기존 identity가 있으나 NeedsLogin이면 자동 재가입하지 않고 승인·만료·정책을 확인합니다. 새 VM의 실제 IP/DNS는 가입 후 조회하며 기존 장비와 이름이 같아도 같은 identity/IP가 된다고 가정하지 않습니다.

## 확인

```bash
bash -n infra/tailscale/prod/node/register.sh
MORE_NAIVE_ENV=dev bash infra/tailscale/prod/node/register.sh --install-only
```

두 번째 명령은 exit 2로 다운로드·등록 전에 거절돼야 합니다. 설치 후 VM에서 `tailscale version`, `systemctl is-active more-naive-tailscaled.service`, `systemctl is-enabled more-naive-tailscaled.service`와 `tailscale status --json`의 BackendState를 확인합니다. 전체 peer 목록·daemon state·인증값은 공유하지 않습니다.

가입 후 허용 운영자의 SSH·hostname/user·sudo와 비허용 identity/사용자의 거절, 실제 DNS와 Serve 설정, 재연결을 확인합니다. prod HTTPS CRUD·workload 재시작 데이터 보존은 #26에서 고유 검증 행만 사용합니다. 설치 확인을 tailnet 가입·HTTPS 성공으로 기록하지 않으며 dev 노드·Funnel·공인 관리 포트를 추가하지 않습니다.
