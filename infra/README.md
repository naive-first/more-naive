# prod 플랫폼

배포는 prod 하나이며 Argo CD가 공식 chart와 저장소 values를 관리합니다. Terraform Helm provider나 수동 Helm release로 같은 Istio 리소스를 중복 소유하지 않습니다.

## Istio 기반과 제어 서버

`infra/argocd/applications/prod/istio-base.yaml`과 `istiod.yaml`은 공식 Istio1.32.0 tag의 chart 소스를 고정 commit으로 지정하고 `$values` ref의 main 브랜치 values와 연결합니다. k3s1.35와 호환 범위를 확인한 고정 버전입니다. base에는 server-side apply를 사용하고 자동 prune은 비활성화합니다.

공식 chart index와 OCI endpoint에서는 1.32.0이 조회되지 않았습니다. 공식 release 아카이브와 Git tag는 확인되어 Git의 chart 경로를 사용합니다. 원본 Chart 메타데이터는 build-time placeholder 1.0.0이므로 prod values에서 실제 이미지 hub/tag를 `docker.io/istio:1.32.0`으로 명시합니다. Argo와 로컬 검증은 같은 고정 Git 소스와 values를 사용합니다.


실제 bootstrap은 base Application Synced/Healthy와 CRD Established를 확인한 뒤 istiod를 등록하고 Deployment Available까지 대기합니다. CRD 실패나 timeout이면 후속 단계로 진행하지 않습니다. istiod의 Deployment 준비와 admission webhook/Service endpoint를 각각 확인해야 실제 제어 경로가 검증됩니다. 로컬 렌더링만으로 webhook Ready를 주장하지 않습니다.

bootstrap은 `more-naive-prod` namespace만 `istio-injection=enabled`로 표시합니다. backend는 이 namespace를 사용하고 PostgreSQL은 prod values의 pod annotation으로 injection을 비활성화합니다. argocd/dev namespace는 injection 대상으로 지정하지 않습니다.

권한과 설치·실패 진단은 [Argo CD 문서](argocd/README.md)를 따릅니다. 실제 prod CRD·istiod·webhook Ready는 접근 입력이 준비된 뒤 확인합니다. 기존 프록시나 공인 포트를 변경하지 않습니다.

업그레이드는 base CRD→istiod→gateway/data plane 순서와 공식 지원 범위를 확인합니다. 앱 이미지의 Git revert와 CRD downgrade는 다릅니다. CRD 삭제는 사용자 리소스에 영향을 주므로 롤백 수단으로 사용하지 않습니다. [공식 Helm 설치](https://istio.io/latest/docs/setup/install/helm/)와 [버전 지원 범위](https://istio.io/latest/docs/releases/supported-releases/)를 따릅니다.

## 내부 gateway와 Host 연결

공식 gateway chart는 동일 고정 Git 소스를 사용하고 `istio-ingressgateway.istio-system.svc.cluster.local:80`을 ClusterIP로만 제공합니다. HTTPS/공인 LoadBalancer·NodePort·Funnel·backend 직접 노출은 만들지 않습니다. 상태 포트15021은 준비 확인용입니다. gateway는 istiod의 gateway injection을 사용하며 bootstrap이 제어 서버 준비 후 등록합니다.

기존 proxy VM이 어디서 TLS를 종료하고 어떤 사설 경로로 gateway에 도달하는지는 아직 확인하지 못했습니다. 외부 VM에서 ClusterIP에 직접 연결된다고 가정하지 않습니다. 실제 VM에서 확인한 사설 upstream과 원래 Host 전달이 필요합니다. backend의 VirtualService는 `istio-system/more-naive-gateway`와 동일한 실제 tailnet HTTPS hostname을 사용하고 `/api/tests`만 backend:8080으로 전달합니다.

Host가 미확정이므로 `istio-route.yaml.example` values와 `ingress-route.yaml.example` Application은 비활성 상태입니다. `infra/charts/istio-route`는 Host 누락·일반 공인 hostname을 거부합니다. #38에서 TLS/실제 hostname을 확인한 뒤 입력을 채우고 두 `.example`을 실제 `.yaml`로 만드는 설정 PR을 준비해야 합니다. 임의의 host나 넓은 wildcard로 대신하지 않습니다. Gateway는 prod namespace의 해당 Host VirtualService만 연결합니다.

검증 순서는 CRD/istiod→gateway Deployment Ready·Service endpoints→Host 일치와 Istio 분석→proxy 사설 upstream→tailnet HTTPS→CRUD입니다. 앞 단계만 통과하면 gateway 준비까지만 기록합니다. 장애 시 먼저 endpoint와 포트·Host·VirtualService destination을 확인하고, 이전 호환 Git 설정을 재적용합니다. public 우회 경로나 기존 Serve 서비스 재설정으로 복구하지 않습니다.

## backend의 prod 반영

`backend.yaml`은 `spring-app` chart에 `platform.yaml` 다음으로 적용합니다. Secret/ConfigMap은 #16 외부 주입 결과만 참조합니다. PostgreSQL·설정·migration 성공 전에는 readiness가 성공하지 않아야 하며 DB 장애를 liveness 재시작으로 대체하지 않습니다.

검증한 public GHCR digest가 아직 없으므로 초기 `image.digest`는 비어 있고 Application은 `backend.yaml.example`로 비활성 상태입니다. chart는 빈 digest를 거부합니다. #19 CI가 PostgreSQL 테스트→이미지 게시→같은 digest 익명 pull을 확인한 뒤 실제 digest와 `backend.yaml` Application 활성화를 포함하는 설정 PR을 준비합니다. main에 merge하면 Argo CD가 자동 sync하며 CI는 클러스터에 접속하지 않습니다.

HTTPS hostname/route는 #38·#23에서 실제 값을 확인하기 전까지 비활성입니다. digest 확인이 Host/사설 upstream 검증을 대신하지 않습니다. 최초 배포는 Secret/ConfigMap→PostgreSQL Ready/PVC→migration/backend Ready·sidecar·Service endpoints→자동 Synced/Healthy→tailnet HTTPS CRUD 순서로 확인합니다.

prod 쓰기 검증과 Pod 재시작은 대상 context/API와 명시적 opt-in을 확인하고 직접 만든 행만 사용합니다. backend 재시작 후 같은 행을 다시 조회하고 마지막에 직접 만든 행만 삭제합니다. 실제 prod 접근이 준비되지 않아 이 검증과 이전 호환 digest/config Git revert는 아직 수행하지 않았습니다. 이미지 rollback이 DB schema나 데이터를 되돌린다고 가정하지 않으며 PVC 삭제·백업/복원은 이 검증에 포함하지 않습니다.

관련 문서: [Tailscale 노드](tailscale/prod/README.md), [기존 proxy 검사](tailscale/prod/proxy/README.md), [PostgreSQL chart](charts/postgres/README.md), [backend chart](charts/spring-app/README.md), [설정 외부 주입](secrets/prod/README.md).
