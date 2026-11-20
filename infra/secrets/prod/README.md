# prod 설정 주입

운영자 관리 호스트에서 루트 `env.prod`의 앱/DB 값만 기존 prod namespace에 주입합니다. Bash·jq·direnv과 해당 k3s 버전의 kubectl이 필요합니다. kubeconfig에 지정 context와 API 서버가 등록되어 있고 namespace 조회, ConfigMap/Secret 생성·patch·조회 권한이 있어야 합니다.

```sh
MORE_NAIVE_ENV=prod direnv exec config/env bash scripts/inject-config.sh --apply
```

[표준 환경 구성](../../../scripts/README.md)이 `env.prod`의 공통 키를 읽습니다. 대상 namespace는 `more-naive-prod`로 제한하며, kubeconfig의 해당 context API 서버는 `KUBE_SERVER`와 일치해야 합니다. 환경 생략/dev·필수값 누락·불일치에서는 쓰기 전에 실패합니다. namespace 자체는 먼저 platform bootstrap에서 생성합니다.

| 루트 입력 | 리소스/key | Pod에서 소비할 값 |
| --- | --- | --- |
| `DB_DATABASE` | ConfigMap `more-naive-config` / `DB_DATABASE` | PostgreSQL `POSTGRES_DB` |
| `DB_USERNAME` | 같은 ConfigMap / `DB_USERNAME` | PostgreSQL `POSTGRES_USER`, backend `DB_USERNAME` |
| DB 이름·prod namespace | 같은 ConfigMap / `DB_URL` | `jdbc:postgresql://postgres.<namespace>.svc.cluster.local:5432/<database>` |
| `DB_PASSWORD` | Secret `more-naive-db` / `DB_PASSWORD` | PostgreSQL `POSTGRES_PASSWORD`, backend `DB_PASSWORD` |

DB Service 이름은 `postgres`, 포트는 5432 계약입니다. `KUBE_CONTEXT`, `KUBE_SERVER`, `NAMESPACE`는 대상 검증에만 사용합니다. URL database 부분은 URL 인코딩합니다. local DB·RustFS·cloud·SSH·Tailscale·registry 인증은 이 두 객체에 넣지 않습니다. Secret은 `data`로 인코딩하여 stdin으로 전달하며 base64는 암호화가 아닙니다. cluster 저장 보호·접근 제어는 [Kubernetes Secret 경계](https://kubernetes.io/docs/concepts/configuration/secret/)를 따릅니다.

후속 `infra/environments/prod/platform.yaml`은 다음 이름/key 참조만 가지며 실제 값 객체를 생성하지 않습니다. 공용 platform 파일은 전체 배치 조정자가 연결합니다.

```yaml
platform:
  configMapName: more-naive-config
  secretName: more-naive-db
  keys:
    database: DB_DATABASE
    username: DB_USERNAME
    url: DB_URL
    password: DB_PASSWORD
```

이 도구만 두 객체의 값을 소유합니다. chart/Argo CD Application 경로에 같은 Secret/ConfigMap을 넣지 않고 자동 prune도 사용하지 않습니다. `--server-side --field-manager=more-naive-config`로 [field 소유권](https://kubernetes.io/docs/reference/using-api/server-side-apply/)을 기록하며 충돌을 강제로 덮지 않습니다. 두 객체의 데이터 key/값을 API로 다시 읽어 일치를 검증하고 성공 시 값 없이 `verified`만 출력합니다. 자식 stderr에 값이 들어올 수 있어 실패 출력도 요약만 제공합니다.

최초 bootstrap과 `env.prod` 변경 시 이 도구를 실행합니다. 동일 이름의 두 객체를 갱신하므로 재실행할 수 있습니다. Kubernetes의 두 객체 갱신은 하나의 트랜잭션이 아니며 실패하면 일부만 반영됐을 수 있습니다. 대상·권한·field 충돌을 값 출력 없이 확인한 뒤 같은 입력으로 재실행하고 성공 검증까지 완료합니다. 기존 객체에 예상하지 않은 data key가 남아 있으면 성공으로 보고하지 않으며 소유권을 먼저 확인합니다.

Secret/ConfigMap 환경변수 변경은 이미 실행 중인 Pod에 자동 적용되지 않습니다. 일반 앱 설정은 운영자가 영향·순서를 확인해 backend Pod를 재시작하고 readiness와 CRUD를 확인합니다. DB 비밀번호 변경은 DB role의 실제 비밀번호와 Secret을 일치시킨 뒤 backend를 재시작하여 연결을 확인해야 합니다. Secret 갱신이나 PostgreSQL Pod 재시작만으로 기존 DB role 비밀번호가 변경됐다고 판정하지 않습니다. 이 도구는 SQL·Pod 재시작·삭제를 수행하지 않습니다.

구문과 대상 확인은 기존 Bash·kubectl 명령을 사용합니다.

```bash
bash -n scripts/inject-config.sh
bash -n scripts/check-cluster.sh
MORE_NAIVE_ENV=prod direnv exec config/env bash scripts/check-cluster.sh
MORE_NAIVE_ENV=prod direnv exec config/env kubectl --context more-naive-prod --namespace more-naive-prod get configmap/more-naive-config secret/more-naive-db
```

객체 조회는 존재·종류·key 수만 보여 주며 값 일치 검증을 대신하지 않습니다. 최초 주입이나 설정 변경 때 상단의 `--apply` 명령이 값 없이 `verified`를 출력하는지 확인하고, 실제 소비 Pod의 준비 상태를 확인합니다. 명령 예시를 실제 수행 결과로 기록하지 않습니다. 로컬 `env.prod`/kubeconfig/생성 Secret을 Git·이미지·PR 로그에 넣지 않습니다. `env.prod` 삭제는 이미 주입된 객체를 삭제하지 않으며 Secret/ConfigMap을 별도로 삭제하면 새 Pod가 준비되지 않을 수 있습니다.
