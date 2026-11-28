# Redis Cluster chart

Redis 8.12 Cluster 6노드(master 3 + replica 3)를 StatefulSet 하나로 렌더링합니다. master 하나가 죽으면 그 replica가 자동으로 master를 이어받습니다. 앱용 ClusterIP Service, 파드별 주소용 Headless Service, 클러스터 버스를 막는 NetworkPolicy, 최초에 6노드를 묶는 Job이 함께 렌더링됩니다. 이미지는 `redis:8.12.0-alpine`입니다.

운영자는 해당 namespace에 Redis 비밀번호가 든 Secret을 먼저 주입하고 PVC를 만들 권한이 있어야 합니다. chart는 Secret 값 객체를 생성하지 않습니다.

| 입력 | 의미 |
| --- | --- |
| `platform.secretName` | Redis 비밀번호가 있는 기존 Secret |
| `platform.keys.redisPassword` | 기본 `REDIS_PASSWORD`, Secret 안의 key |
| `image.repository/tag` | 버전 고정한 Redis 이미지 |
| `storage.className/size` | 노드마다 만들 PVC의 StorageClass와 요청 용량 |
| `maxMemory` | 노드당 데이터 메모리 상한. 차면 가장 오래 안 쓴 key부터 지웁니다(`allkeys-lru`) |
| `resources` | Redis 컨테이너 CPU·메모리 요청/상한. fork(AOF rewrite) 여유를 위해 상한을 `maxMemory`의 2배로 둡니다 |
| `clusterRejoin.resources` | 재시작 후 다른 노드를 다시 만나는 보조 컨테이너의 CPU·메모리 |
| `clusterCreateJob.resources` | 클러스터 묶기 Job의 CPU·메모리 |
| `podAnnotations` | Redis·Job Pod annotation. sidecar 주입 namespace에서는 `sidecar.istio.io/inject: "false"`로 제외합니다. sidecar가 붙으면 클러스터 버스 연결이 깨집니다 |

```sh
helm lint infra/charts/redis --strict --set platform.secretName=fixture-secret --set storage.className=local-path
helm template redis infra/charts/redis --namespace fixture --set platform.secretName=fixture-secret --set storage.className=local-path
```

예상 결과는 Service 두 개, StatefulSet 하나(replicas 6), NetworkPolicy 하나, Job 하나이며 Secret/ConfigMap 값 객체는 없습니다. PVC는 `data-<release>-0`부터 `data-<release>-5`까지 만들어집니다.

## 파드 동작

비밀번호는 시작 스크립트가 Secret 환경변수로 설정 파일을 만들어 전달합니다. 명령줄 인자로 넘기지 않으므로 프로세스 목록에 보이지 않습니다. Secret의 비밀번호를 바꾸면 Redis 파드를 재시작해야 적용됩니다.

Redis 8.12는 클러스터 버스(16379)를 TLS로 보호하지 않으면 `cluster-bus-port-protected-mode no`를 명시해야 기동합니다. 클러스터 버스는 비밀번호로 보호되지 않으므로 NetworkPolicy가 16379를 이 release의 Redis 파드끼리만 허용합니다. 6379는 같은 namespace의 파드에 열려 있고 비밀번호를 요구합니다.

파드가 다시 뜨면 IP가 바뀝니다. 6개가 동시에 재시작하면 서로 옛 IP만 알고 있어 클러스터가 `fail`에 머뭅니다. 그래서 각 파드의 보조 컨테이너 `cluster-rejoin`이 시작할 때 Headless DNS로 다른 노드의 새 IP를 찾아 `CLUSTER MEET`하고 대기합니다. 이 처리를 postStart 훅에 두면 훅이 끝날 때까지 파드가 DNS에 공개되지 않아 6개가 서로를 찾지 못합니다. 처음 뜬 빈 노드는 이 단계를 건너뜁니다. 먼저 서로 만나면 묶기 명령이 비어 있지 않은 노드로 보고 거부하기 때문입니다.

## 클러스터 묶기 Job

Argo CD는 sync가 끝날 때마다 `<release>-cluster-create` Job을 다시 실행합니다(PostSync hook). Job은 6개 노드가 응답할 때까지 기다린 뒤 각 노드가 아는 노드 수와 slot 수로 상태를 판단합니다.

| 상태 | 각 노드의 `cluster info` | Job 동작 |
| --- | --- | --- |
| 최초 배포 | 6개 모두 `cluster_known_nodes:1`, `cluster_slots_assigned:0` | 3 master + 3 replica로 묶고 성공 |
| 정상 운영 | 6개 모두 `cluster_known_nodes:6`, `cluster_slots_assigned:16384` | 아무것도 하지 않고 성공 |
| 그 외 | 일부만 클러스터에 속함. 예: PVC가 지워진 노드가 빈 상태로 다시 뜸 | 아무것도 바꾸지 않고 실패 |

전체 재시작 직후에는 노드끼리 다시 만나는 중이라 잠시 상태가 어긋날 수 있어 5초 간격으로 12번까지 다시 확인한 뒤 실패로 판정합니다. 실패하면 Argo CD의 sync 결과가 실패로 표시됩니다.

### 노드 하나의 데이터가 사라졌을 때 수동 복구

빈 노드는 새 ID로 뜨고, 나머지 노드는 옛 ID를 `fail`로 기억합니다. 옛 ID를 지우고 빈 노드를 replica로 다시 붙입니다. 명령은 Redis 파드 안에서 실행하며 비밀번호는 `REDISCLI_AUTH`로 전달합니다.

```sh
kubectl -n <namespace> exec redis-0 -- sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli cluster nodes'
```

1. 출력에서 `fail` 표시된 옛 노드 ID를 확인합니다.
2. 옛 노드를 아는 모든 노드에서 각각 `redis-cli cluster forget <옛 노드 ID>`를 실행합니다. 60초 안에 모두 실행해야 다시 퍼지지 않습니다.
3. 빈 노드의 `cluster info`로 경우를 나눕니다.
   - `cluster_known_nodes:1`이면 아직 클러스터 밖에 있습니다. 정상 노드 하나에서 `redis-cli --cluster add-node <빈 노드 IP>:6379 <정상 노드 IP>:6379 --cluster-slave`로 replica를 붙입니다.
   - 그보다 크면, 정상 노드가 재시작하면서 빈 노드를 slot 없는 master로 이미 끌어들인 상태입니다. replica가 없는 master의 ID를 `cluster nodes`에서 찾아 빈 노드에서 `redis-cli cluster replicate <그 master ID>`를 실행합니다.
4. 모든 노드의 `cluster_known_nodes:6`, master 3·replica 3을 확인한 뒤 Argo CD에서 다시 sync하면 Job이 성공합니다.

## 경계

StatefulSet 삭제·축소에 [PVC 보존 정책](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/#persistentvolumeclaim-retention)을 `Retain`으로 둡니다. 6개 파드가 같은 서버에 뜨면 replica는 파드·프로세스 장애만 막고 서버나 디스크 장애는 막지 못합니다. 노드 추가·리샤딩, 백업·복원은 구성하지 않습니다.
