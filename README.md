# More Naive

PostgreSQL `test` 테이블의 생성·조회·수정·삭제를 확인하는 최소 prod API를 구축합니다. dev는 비활성 문서 구조로만 유지합니다.

[prod 배포 계약](docs/decisions/prod.md)에서 고정 버전, 입력과 state/설정 소유권, 실제 확인한 연결 정보와 남은 운영 입력을 확인합니다. 각 구현은 별도 이슈/PR로 추가하며, 문서의 목표를 실제 배포 완료로 취급하지 않습니다.

## 실행 문서

prod k3s·Argo CD·PostgreSQL·backend·Istio gateway를 배포했습니다. VM Tailscale 설치·로그인을 완료하고 `https://more-naive-vm-1.tail373827.ts.net/api/tests`에서 인증서 검증을 포함한 HTTP 200과 잘못된 Host/API 밖 경로의 404를 확인했습니다. CRUD·재시작 영속성은 아래 smoke로 별도 검증합니다.

| 작업 | 정본 문서 |
| --- | --- |
| `env.dev`·`env.prod` 공통 키 전달 | [scripts](scripts/README.md) |
| local 앱·PostgreSQL 테스트·최소 API | [backend](backend/README.md) |
| RustFS 영속 bootstrap | [RustFS](infra/terragrunt/bootstrap/rustfs/README.md) |
| state 인증·버킷·native 잠금 | [state backend](infra/terragrunt/state-README.md) |
| prod Terraform/Terragrunt native 실행 | [Terragrunt](infra/terragrunt/README.md) |
| 대상 노드 확인·k3s 설치 | [k3s](infra/k3s/README.md)·[prod 확인](infra/k3s/config/prod/README.md) |
| Tailscale 노드·proxy 현황 | [기존 proxy](infra/tailscale/prod/proxy/README.md)·[신규 노드 PR #64](https://github.com/naive-first/more-naive/pull/64) |
| Argo CD 설치·권한·자동 sync | [Argo CD](infra/argocd/README.md) |
| Istio·gateway·prod 배포 | [infra](infra/README.md) |
| 앱/DB 설정 외부 주입 | [Secret/ConfigMap](infra/secrets/prod/README.md) |
| PostgreSQL prod values·PVC | [prod DB](infra/environments/prod/README.md) |

## Argo CD·API에 접속하기

**먼저 관리자에게 Tailscale 접근 권한을 받고, 승인된 계정으로 Tailscale에 연결해야 합니다.** 아래 주소는 Tailscale 사설 네트워크(tailnet) 안에서 사용합니다. URL만 전달받아서는 접속할 수 없습니다.

1. 프로젝트 관리자에게 사용할 계정을 알려 주고 tailnet 초대와 대상 서비스 접근 허용을 요청합니다. 기기 승인이 필요한 경우 승인까지 받습니다.
2. 내 PC에 Tailscale 클라이언트를 설치하고 초대받은 계정으로 로그인한 뒤 해당 tailnet에 연결합니다. CLI를 쓰는 환경에서는 `tailscale status`로 연결 상태를 확인합니다.
3. API 사용자는 HTTPS 서비스 접근 권한을, Argo CD 운영자는 추가로 VM SSH·sudo 권한과 Argo CD 로그인 계정을 전달받습니다. Tailscale 연결만으로 SSH·Argo CD 권한이 부여되지는 않습니다.

### API 조회

API 주소는 `https://more-naive-vm-1.tail373827.ts.net/api/tests`입니다. 브라우저에서 열거나 다음 읽기 전용 요청으로 확인합니다. 정상 응답은 HTTP 200과 JSON 배열이며 데이터가 없으면 `[]`입니다.

```bash
curl --fail --silent --show-error \
  https://more-naive-vm-1.tail373827.ts.net/api/tests
```

상세 조회는 `/api/tests/{id}`이며 생성·수정·삭제 요청과 응답은 [backend API 문서](backend/README.md)를 따릅니다. 관리용 SSH DNS인 `more-naive-vm.tail373827.ts.net`과 HTTPS 서비스 DNS인 `more-naive-vm-1.tail373827.ts.net`을 구분합니다.

### Argo CD 화면

Argo CD는 ClusterIP로만 열려 있고 공개 접속 URL은 없습니다. 승인받은 운영자는 로컬 PC의 터미널에서 다음 SSH 연결을 유지합니다. `study` 계정의 SSH 인증과 VM에서 `sudo k3s kubectl`을 실행할 권한이 필요하며, 별도 개인키를 전달받았다면 SSH의 `-i` 옵션으로 지정합니다.

```bash
ssh -o ExitOnForwardFailure=yes -t \
  -L 127.0.0.1:18081:127.0.0.1:18081 \
  study@more-naive-vm.tail373827.ts.net \
  'sudo k3s kubectl -n argocd port-forward --address=127.0.0.1 service/argocd-server 18081:443'
```

`Forwarding from 127.0.0.1:18081` 메시지가 나오면 같은 PC의 브라우저에서 `https://127.0.0.1:18081`을 열고 관리자가 전달한 Argo CD 계정으로 로그인합니다. 로컬 터널 주소와 서버 인증서가 맞지 않아 경고가 나오면 관리자에게 인증서와 접속 대상을 확인합니다. 비밀번호·개인키를 README나 PR에 적지 않습니다. 사용을 마치면 터미널에서 `Ctrl+C`로 연결을 종료합니다.

### 접속이 안 될 때

| 증상 | 확인할 항목 |
| --- | --- |
| DNS 조회 실패·연결 시간 초과 | Tailscale 연결과 올바른 tailnet·기기 승인·대상 서비스 접근 정책을 관리자에게 확인합니다. |
| API 인증서 오류·404 | 위 HTTPS 서비스 DNS와 `/api/tests` 경로를 확인합니다. TLS 검증을 끄지 않고, 계속 실패하면 [proxy 운영 문서](infra/tailscale/prod/proxy/README.md)를 따라 운영자가 점검합니다. |
| SSH 인증·sudo 거부 | 승인된 SSH 사용자·개인키·VM sudo 권한을 확인합니다. API 접근 권한과 별도입니다. |
| 로컬 18081 포트 사용 중 | 기존 사용 프로세스를 확인하고 다른 로컬 포트를 선택해 SSH `-L`의 첫 포트와 브라우저 주소를 함께 바꿉니다. |
| Argo CD 화면은 열리지만 로그인·조회 거부 | Argo CD 계정과 역할 권한을 관리자에게 요청합니다. 설치·권한 설정은 [Argo CD 운영 문서](infra/argocd/README.md)를 따릅니다. |

## local 검증과 prod 구축

local은 루트 `env.dev`의 `DB_*`를 선택해 앱과 Compose 테스트 DB를 실행합니다. CI는 별도 테스트 값을 주입하며 `env.prod`가 필요하지 않습니다. 준비/명령/검증은 backend·scripts 문서를 따릅니다. dev 자원/자격 증명을 생성하지 않습니다.

최초 prod 구축은 RustFS 관리 호스트·네트워크/서버 공급자·노드/SSH·proxy/TLS 입력이 먼저 확정돼야 합니다. 준비된 코드의 실행 순서는 RustFS bootstrap→버킷/최소 권한→잠금·장애 중단 검증→native Terraform/Terragrunt→Tailscale/k3s→외부 설정 주입→Argo CD bootstrap의 단계별 Ready 대기→검증 이미지 설정 PR입니다. provider와 #8 실행 계약이 미확정이므로 이 전체 순서를 자동 연결하는 최상위 bootstrap은 아직 구현하지 않았습니다. 이 문단을 완성된 진입점으로 취급하지 않습니다.

반복 배포는 PostgreSQL 테스트를 통과한 이미지의 public 익명 digest pull을 확인한 설정 PR을 main에 merge하면 Argo CD가 자동 sync합니다. `env.prod`만 바꾼 경우에는 선택된 Secret/ConfigMap 주입 코드를 다시 실행하고 Pod 반영을 확인해야 하며 Git 변경으로 자동 갱신되는 값과 구분합니다. 최초 GHCR package 공개 전환과 Actions 자동 PR 허용 설정은 저장소 관리자가 준비합니다.

## prod smoke

`env.prod`의 `NAMESPACE=more-naive-prod`·`KUBE_CONTEXT`·`KUBE_SERVER`·`PROXY_HTTPS_HOSTNAME`을 준비하고 `config/env/.envrc`를 검토·허용합니다. Bash·curl·jq·kubectl·direnv가 필요합니다. `scripts/smoke.sh`는 지정한 context의 API 주소와 tailnet HTTPS origin을 확인합니다. 기본은 목록 조회만 수행하며 쓰기/Pod 재시작이 없습니다. 쓰기는 `--allow-write`, backend/DB 재시작은 각각 추가 opt-in이 필요합니다.

```bash
MORE_NAIVE_ENV=prod direnv exec config/env bash scripts/smoke.sh
```

실제 대상과 영향을 확인한 후 `--allow-write`를 추가하면 직접 만든 두 행으로 생성→조회→수정→삭제/404를 확인하고 직접 만든 행만 정리합니다. `--restart-backend` 또는 `--restart-db`를 추가하면 해당 workload만 rollout restart하고 저장값을 재조회합니다. PVC 삭제·전체 테이블 정리·백업/복원은 실행하지 않습니다. 정리에 실패하면 출력한 도구 소유 row ID만 확인합니다.

기존 관리 진입 DNS와 HTTPS 서비스 DNS는 다릅니다. 실제 로그인된 VM의 `PROXY_HTTPS_HOSTNAME=more-naive-vm-1.tail373827.ts.net`을 사용합니다. HTTPS는 Serve→loopback relay→Istio로 연결하며 [설치·plan·apply와 확인](infra/tailscale/prod/proxy/README.md)을 따릅니다. 이전 호환 digest/config를 Git revert하는 복구와 DB 데이터 복원을 혼동하지 않습니다. 설치/삭제·state/PVC 영향과 실패 진단은 각 정본 문서에서 확인합니다.

### smoke 확인 절차

```bash
bash -n scripts/smoke.sh
MORE_NAIVE_ENV=dev bash scripts/smoke.sh
```

두 번째 명령은 exit 2로 중단하고 HTTP 요청이나 Pod 변경을 실행하지 않아야 합니다. 실제 prod 검증은 위의 읽기 전용 실행으로 시작합니다. 쓰기를 허용한 실행에서는 생성 응답의 id/value, 수정 후 재조회와 control 행 불변, 삭제 뒤 404 및 직접 만든 행의 정리 결과를 기록합니다. backend/DB 재시작은 각각의 opt-in을 준 경우에만 같은 행을 재조회합니다. 로컬 문법·입력 검사를 운영 CRUD·재시작 데이터 보존 결과로 기록하지 않습니다.
