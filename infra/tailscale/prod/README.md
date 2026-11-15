# prod Tailscale 접근

신규 노드는 Tailscale 1.104.7 Linux amd64 정적 배포본을 checksum으로 검증합니다. [공식 정적 설치 문서](https://tailscale.com/docs/install/static)에 따라 daemon을 지속 서비스로 관리합니다. 실행 호스트에는 Bash·jq·direnv, 최초 설치에는 curl·sha256sum·tar·install·systemctl이 필요합니다. 기존 등록 노드는 재가입·자동 업그레이드·SSH 설정 변경을 하지 않고 Running과 기대 node 이름을 확인합니다.

## 첫 노드 등록

공인 SSH를 기본 개방하지 않습니다. 운영자가 공급자의 console/cloud-init 등 신뢰한 초기 진입 경로에서 실제 node hostname·OS 사용자와 권한을 확인합니다. `node/register.sh`는 그 노드에서 실행하며 기본은 확인만 합니다. 예시를 실제 값으로 대체합니다.

```bash
MORE_NAIVE_ENV=prod direnv exec config/env bash infra/tailscale/prod/node/register.sh
```

최초 설치/등록에는 root·Linux amd64·systemd와 [정책 검토](policies/README.md)가 필요합니다. 검토·허용한 `config/env/.envrc`와 `env.prod`의 `TAILSCALE_EXPECTED_HOST`·`TAILSCALE_NODE_NAME`·`SSH_USER`·`TAILSCALE_TAGS`·`TAILSCALE_AUTH_KEY`를 direnv로 전달하며 값을 명령 인자/Git/Terraform state에 적지 않습니다. 노드 console에 전달할 때도 비밀을 화면이나 로그에 출력하지 않습니다. `--apply --policy-reviewed`가 있어야 신규 설치/등록을 진행합니다. auth key는 임시 0600 파일로 전달한 뒤 제거합니다. 기존 daemon state/service는 덮어쓰지 않습니다.

```bash
python3 -m unittest discover -s infra/tailscale/prod/node -p 'test*.py' -v
```

로컬 guard 테스트는 실제 tailnet 등록의 증거가 아닙니다. 운영자는 신규 등록 뒤 `tailscale status`와 `tailscale version`을 확인하고 허용 운영자·OS 사용자로 SSH → hostname/user → `sudo -n true`를 확인합니다. 비허용 테스트 identity/OS 사용자로 거부도 확인합니다. node 재시작 뒤 재연결과 daemon 자동 실행을 확인합니다.

## 재연결과 장애 진단

Running인 기존 노드는 등록 인증을 다시 제출하지 않습니다. 키 만료/NeedsLogin이나 node-name 불일치는 도구가 중단하며 관리자가 기존 node identity·승인/만료·tag/policy·daemon 상태를 확인합니다. 인증 실패는 키의 유효기간/재사용/태그 권한을 확인하되 auth key 자체를 로그로 출력하지 않습니다. 기존 노드의 SSH가 꺼져 있으면 관리자가 현재 설정과 승인 정책을 대조한 뒤 별도로 활성화합니다.

2026-11-14 제공된 대상은 `study@study-k3s-access.tail373827.ts.net`(tailnet IP `100.90.91.104`)입니다. 이 VM의 node/proxy 역할은 선택하지 않았습니다. 이 변경에서는 운영 연결이나 신규 가입을 실행하지 않았습니다. 따라서 허용/거부·sudo·재시작/재연결은 NOT_RUN입니다. VM/tailnet 운영자가 #8의 실제 node 정보와 개인키/known_hosts·현재 정책을 준비한 뒤 위 확인을 수행해야 #37을 완료합니다. dev 노드, Funnel, 공인 관리 포트는 추가하지 않습니다.
