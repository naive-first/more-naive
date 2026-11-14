# PostgreSQL chart

PostgreSQL 17.12 단일 replica, 내부 ClusterIP/Headless Service와 PVC를 렌더링합니다. 환경별 namespace·StorageClass·설정 객체 이름은 호출자가 입력합니다. 실제 배포와 Pod 재시작 데이터 확인은 #36 범위입니다.

Helm 4.3.2, Kubernetes 1.35 기준으로 검증합니다. PostgreSQL 이미지는 `postgres:17.12-alpine`입니다. 운영자는 해당 namespace에 DB ConfigMap/Secret을 먼저 주입하고 PVC를 만들 권한이 있어야 합니다. chart는 이 객체의 값이나 namespace를 생성하지 않습니다.

| 입력 | 의미 |
| --- | --- |
| `platform.configMapName` | DB 이름·사용자가 있는 기존 ConfigMap |
| `platform.secretName` | DB 비밀번호가 있는 기존 Secret |
| `platform.keys.database/username/password` | 기본 `DB_DATABASE/DB_USERNAME/DB_PASSWORD`, 명시적 key 참조 |
| `image.repository/tag` | 버전 고정한 PostgreSQL 이미지 |
| `storage.className/size` | 실제 환경 StorageClass 이름과 PVC 요청 용량 |
| `resources` | PostgreSQL CPU·메모리 요청/상한 |

환경 공통 참조를 담은 `platform.yaml`을 먼저, `postgres.yaml`을 나중에 적용합니다. 실제 prod values는 후속 이슈에서 추가합니다. 아래는 비밀값 없는 렌더링 fixture입니다.

```sh
helm lint infra/charts/postgres --strict --set platform.configMapName=fixture-config --set platform.secretName=fixture-secret --set storage.className=local-path
helm template postgres infra/charts/postgres --namespace fixture --set platform.configMapName=fixture-config --set platform.secretName=fixture-secret --set storage.className=local-path
```

예상 결과는 두 Service와 StatefulSet 하나이며 Secret/ConfigMap 값 객체는 없습니다. selector·Headless `serviceName`·명명된 `postgres` 포트가 연결되고, PVC는 `data-<release>-0`으로 만들어집니다. `PGDATA`는 PostgreSQL 17 데이터 마운트 아래의 `pgdata` 디렉터리입니다. [공식 이미지의 PGDATA 계약](https://hub.docker.com/_/postgres)을 따릅니다.

`pg_isready` startup/readiness가 실패하면 설정 참조 누락, 이미지 pull, PVC Pending, DB 로그를 확인합니다. 이 probe는 DB 인증 자체를 검증하는 SQL 테스트가 아니며 backend migration·CRUD 검증을 대신하지 않습니다. 필요한 값이 없으면 렌더링이 실패합니다. 같은 release·namespace로 재실행하며 PVC 데이터는 초기화하지 않습니다.

StatefulSet 삭제·축소 시 [PVC 보존 정책](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/#persistentvolumeclaim-retention)을 `Retain`으로 둡니다. 운영자가 PVC를 직접 삭제하거나 StorageClass/PV reclaim 정책에 따라 볼륨을 제거하면 데이터가 소실될 수 있습니다. 단일 Pod와 단일 디스크는 HA가 아니며 replica 증가를 HA로 취급하지 않습니다. 백업·복원 구성은 추가하지 않습니다.

기존 데이터 디렉터리에서는 환경변수 `POSTGRES_PASSWORD` 변경만으로 DB role 비밀번호가 바뀌지 않습니다. 운영자가 실제 DB role과 Secret을 같은 값으로 맞춘 뒤 관련 Pod를 재시작하고 연결을 확인해야 합니다. chart는 SQL 비밀번호 변경을 수행하지 않습니다.
