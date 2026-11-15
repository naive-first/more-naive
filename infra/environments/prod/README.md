# prod PostgreSQL

prod namespace `more-naive-prod`에 PostgreSQL 한 개를 배포하는 선언입니다. 2026-11-15 실제 prod에서 Argo Application `Synced/Healthy`, `postgres-0` 1/1 Running, 5Gi PVC Bound를 확인했습니다. Service DNS를 통한 비밀번호 인증 SQL에서 DB/사용자 `more_naive`, 서버 17.12와 `SELECT 1` 성공을 확인했습니다. [실제 배포·확인 명령과 raw 결과](https://github.com/naive-first/more-naive/pull/48#issuecomment-6894361467)를 참조합니다. DB Pod 재시작 후 데이터 보존과 backend migration/readiness는 아직 검증하지 않았습니다.

Argo CD 3.6.1의 `more-naive-db` 프로젝트와 자기 저장소만 사용합니다. [여러 source의 values 참조](https://argo-cd.readthedocs.io/en/stable/user-guide/multiple_sources/)로 `platform.yaml` → `postgres.yaml`을 적용하며 release/Service 이름은 `postgres`입니다. `main` merge 후 [자동 sync/self-heal](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)를 사용하고 prune은 비활성입니다. Application이 namespace를 생성하지 않으며 prod bootstrap이 namespace와 Argo 프로젝트를 준비해야 합니다.

| 준비할 입력 | 담당·확인 시점 |
| --- | --- |
| prod kube context/API 서버와 namespace | 운영자, bootstrap/설정 주입 전 |
| ConfigMap `more-naive-config`, Secret `more-naive-db` | 운영자 입력 → #16 주입 코드, DB sync 전 |
| StorageClass `local-path`, 5Gi 용량과 파일 접근 경계 | 클러스터 운영자, DB sync 전 |
| repo 읽기와 namespaced DB 리소스 권한 | Argo CD 관리자, Application 등록 전 |

DB 이름·사용자·URL과 비밀번호 실제 값은 Git에 없습니다. `platform.yaml`은 key 참조만 제공하고 DB/application chart가 같은 Secret/ConfigMap을 만들지 않습니다. prod namespace의 backend sidecar 주입과 별도로 DB Pod는 `sidecar.istio.io/inject: "false"`로 제외합니다. storage와 resource는 이 values에서 조정하고 자격 증명을 values에 추가하지 않습니다.

```sh
helm lint infra/charts/postgres --strict -f infra/environments/prod/platform.yaml -f infra/environments/prod/postgres.yaml
helm template postgres infra/charts/postgres --namespace more-naive-prod -f infra/environments/prod/platform.yaml -f infra/environments/prod/postgres.yaml
```

예상 결과는 두 Service, 단일 StatefulSet, PVC template과 정확한 Secret/ConfigMap 참조입니다. 실제 sync 후에는 운영자가 명시한 prod context에서 `StatefulSet/postgres` rollout, PVC Bound, Service `postgres` DNS·DB 인증과 backend migration/readiness를 확인합니다. PVC Pending은 StorageClass/용량·노드 상태부터, DB 실패는 Secret/ConfigMap key와 실제 DB role·Pod 로그부터 확인하며 값은 출력하지 않습니다.

데이터 보존 검증은 별도 prod 쓰기 opt-in과 재시작 영향 확인 후 진행합니다. 자신이 만든 `test` 행의 id/value와 PVC UID를 기록하고, 승인한 DB Pod 재시작 후 같은 PVC UID와 같은 행을 읽습니다. 마지막에 그 id의 행만 정리합니다. PVC를 삭제하거나 기존 다른 행을 변경하지 않습니다. 실제 API·재시작 검증 흐름은 #24/#26과 연결하며 이 선언의 렌더링으로 수행했다고 기록하지 않습니다.

재실행은 같은 release·namespace·PVC를 유지합니다. 설정 변경 시 #16 주입 코드를 실행하고 필요한 Pod만 재시작합니다. DB role 비밀번호와 Secret은 함께 맞춰야 하며 Secret 변경만으로 기존 DB 비밀번호가 바뀌지 않습니다. StatefulSet 삭제·축소에 PVC를 Retain하지만 PVC 직접 삭제·노드/디스크 손실까지 막지는 못합니다. 단일 노드/디스크는 HA가 아니고 백업·보관·복원 리허설을 추가하지 않습니다. 운영자가 삭제할 때에는 App/StatefulSet과 PVC/실제 데이터를 구분하여 영향과 권한을 확인해야 합니다.
