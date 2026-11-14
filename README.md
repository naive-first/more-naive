# More Naive

PostgreSQL `test` 테이블의 생성·조회·수정·삭제를 확인하는 최소 prod API를 구축합니다. dev는 비활성 문서 구조로만 유지합니다.

[prod 배포 계약](docs/decisions/prod.md)에서 고정 버전, 입력과 state/설정 소유권, 실제 확인한 연결 정보와 남은 운영 입력을 확인합니다. 각 구현은 별도 이슈/PR로 추가하며, 문서의 목표를 실제 배포 완료로 취급하지 않습니다.

## 실행 문서

아래 링크는 관련 선행 PR이 합쳐진 구조를 기준으로 합니다. 실제 prod 배포는 아직 완료하지 않았습니다.

| 작업 | 정본 문서 |
| --- | --- |
| 루트 `.env`·선택된 입력 전달 | [scripts](scripts/README.md) |
| local 앱·PostgreSQL 테스트·최소 API | [backend](backend/README.md) |
| RustFS 영속 bootstrap | [RustFS](infra/terragrunt/bootstrap/rustfs/README.md) |
| state 인증·버킷·native 잠금 | [state backend](infra/terragrunt/state-README.md) |
| prod 전용 Terragrunt | [Terragrunt](infra/terragrunt/README.md) |
| 대상 노드 확인·k3s 설치 | [k3s](infra/k3s/README.md)·[prod 확인](infra/k3s/config/prod/README.md) |
| Tailscale 노드·proxy 현황 | [Tailscale](infra/tailscale/prod/README.md) |
| Argo CD 설치·권한·자동 sync | [Argo CD](infra/argocd/README.md) |
| Istio·gateway·prod 배포 | [infra](infra/README.md) |
| 앱/DB 설정 외부 주입 | [Secret/ConfigMap](infra/secrets/prod/README.md) |
| PostgreSQL prod values·PVC | [prod DB](infra/environments/prod/README.md) |

## local 검증과 prod 구축

local은 루트 `.env`의 `LOCAL_DB_*`를 선택해 앱과 Compose 테스트 DB를 실행합니다. CI는 별도 테스트 값을 주입하며 prod `.env`가 필요하지 않습니다. 준비/명령/검증은 backend·scripts 문서를 따릅니다. dev 자원/자격 증명을 생성하지 않습니다.

최초 prod 구축은 RustFS 관리 호스트·네트워크/서버 공급자·노드/SSH·proxy/TLS 입력이 먼저 확정돼야 합니다. 준비된 코드의 실행 순서는 RustFS bootstrap→버킷/최소 권한→잠금·장애 중단 검증→prod Terragrunt→Tailscale/k3s→외부 설정 주입→Argo CD bootstrap의 단계별 Ready 대기→검증 이미지 설정 PR입니다. provider와 #8 실행 계약이 미확정이므로 이 전체 순서를 자동 연결하는 최상위 bootstrap은 아직 구현하지 않았습니다. 이 문단을 완성된 진입점으로 취급하지 않습니다.

반복 배포는 PostgreSQL 테스트를 통과한 이미지의 public 익명 digest pull을 확인한 설정 PR을 main에 merge하면 Argo CD가 자동 sync합니다. 로컬 `.env`만 바꾼 경우에는 선택된 Secret/ConfigMap 주입 코드를 다시 실행하고 Pod 반영을 확인해야 하며 Git 변경으로 자동 갱신되는 값과 구분합니다. 최초 GHCR package 공개 전환과 Actions 자동 PR 허용 설정은 저장소 관리자가 준비합니다.

## prod smoke

`scripts/smoke.py`는 지정한 context의 API 주소와 tailnet HTTPS origin을 확인합니다. 기본은 목록 조회만 수행하며 쓰기/Pod 재시작이 없습니다. 쓰기는 `--allow-write`, backend/DB 재시작은 각각 추가 opt-in이 필요합니다.

```bash
python3 scripts/smoke.py --environment prod --context '<prod-context>' \
  --expected-server 'https://<실제 API 주소>:6443' --url 'https://<실제 tailnet hostname>'
```

실제 대상과 영향을 확인한 후 `--allow-write`를 추가하면 직접 만든 두 행으로 생성→조회→수정→삭제/404를 확인하고 직접 만든 행만 정리합니다. `--restart-backend` 또는 `--restart-db`를 추가하면 해당 workload만 rollout restart하고 저장값을 재조회합니다. PVC 삭제·전체 테이블 정리·백업/복원은 실행하지 않습니다. 정리에 실패하면 출력한 도구 소유 row ID만 확인합니다.

실제 prod HTTPS CRUD/Pod 재시작은 접근 입력이 없어 미수행입니다. 이전 호환 digest/config를 Git revert하는 복구와 DB 데이터 복원을 혼동하지 않습니다. 설치/삭제·state/PVC 영향과 실패 진단은 각 정본 문서에서 확인합니다.
