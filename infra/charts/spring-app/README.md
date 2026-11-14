# Spring Boot chart

public GHCR의 `repository@sha256:...` 이미지와 기존 ConfigMap/Secret을 받아 backend Deployment·ClusterIP Service를 만듭니다. namespace는 Helm/Argo CD destination에서 명시합니다. chart 렌더링은 실제 rollout·CRUD 성공을 뜻하지 않습니다.

Helm 4.3.2, Kubernetes 1.35, Istio 1.32의 `networking.istio.io/v1` 기준입니다. 입력 values는 `platform.yaml` → `backend.yaml` 순서로 적용합니다. 실제 이미지의 public/익명 pull과 동일 digest 확인은 게시 CI와 배포 단계에서 수행합니다. imagePullSecrets는 요구하지 않습니다.

| 입력 | 의미 |
| --- | --- |
| `image.repository/digest` | public 저장소와 `sha256:` + 64자리 소문자 hex, tag 배포 불가 |
| `platform.configMapName/secretName` | 주입 도구가 관리하는 기존 객체 |
| `platform.keys.url/username/password` | 기본 `DB_URL/DB_USERNAME/DB_PASSWORD`, key 단위 참조 |
| `replicaCount`, `resources` | app replica와 CPU·메모리 요청/상한 |
| `routing.enabled/host` | API 경로 활성화, proxy HTTPS와 동일한 Host |
| `routing.gateway` | 이미 존재하는 Gateway의 `namespace/name` |
| `routing.createGateway/gatewaySelector` | 선택적으로 release namespace에 `<release>-gateway` 생성 |

가짜 digest를 사용하는 아래 명령은 구조 확인용이며 이미지 pull 성공 증거가 아닙니다.

```sh
helm lint infra/charts/spring-app --strict --set platform.configMapName=fixture-config --set platform.secretName=fixture-secret --set image.repository=ghcr.io/naive-first/more-naive --set image.digest=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
helm template backend infra/charts/spring-app --namespace fixture --set platform.configMapName=fixture-config --set platform.secretName=fixture-secret --set image.repository=ghcr.io/naive-first/more-naive --set image.digest=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa --set routing.enabled=true --set routing.host=fixture.tailnet.ts.net --set routing.gateway=istio-system/more-naive-gateway
```

Service는 app의 `http` 8080 포트로 전달합니다. [Actuator health group](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)에 맞춰 startup/readiness는 `/actuator/health/readiness`, liveness는 `/actuator/health/liveness`를 봅니다. DB/migration 실패 시 시작/Ready가 되지 않으며, 일시 DB 장애를 liveness에 포함하지 않는 backend 설정을 전제로 합니다. probe·앱 설정 계약은 backend #29에서 검증합니다.

route는 `/api/tests`와 하위 경로만 backend로 전달하며 actuator는 외부 route에 포함하지 않습니다. [VirtualService의 Gateway 참조](https://istio.io/latest/docs/reference/config/networking/virtual-service/)를 사용합니다. TLS는 기존 Tailscale proxy에서 종료하고 proxy→Istio의 실제 사설 경로·Host 전달은 #15/#23/#38에서 확인합니다. chart가 공인 포트나 HTTPS 인증서를 준비하지 않습니다. 외부 Gateway를 사용하면 `createGateway`는 false로 두어 소유권을 중복하지 않습니다.

필수 참조·digest·활성 route의 host/gateway가 없으면 렌더링을 중단합니다. rollout 시 Ready 실패는 Secret/ConfigMap key, DB URL·migration·Pod 로그부터, route 실패는 동일 Host와 Gateway selector부터 확인합니다. `.env`를 변경하면 설정 주입 도구를 다시 실행하고 필요한 Pod를 재시작합니다. 동일 release·namespace로 재실행하며 이전 호환 digest를 재적용할 수 있습니다. release 삭제는 app/route/Service를 제거하지만 외부 DB·Secret/ConfigMap의 수명을 관리하지 않습니다.
