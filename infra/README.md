# prod 플랫폼

배포는 prod 하나이며 Argo CD가 공식 chart와 저장소 values를 관리합니다. Terraform Helm provider나 수동 Helm release로 같은 Istio 리소스를 중복 소유하지 않습니다.

## Istio 기반과 제어 서버

`infra/argocd/applications/prod/istio-base.yaml`과 `istiod.yaml`은 공식 Istio1.32.0 tag의 chart 소스를 고정 commit으로 지정하고 `$values` ref의 main 브랜치 values와 연결합니다. k3s1.35와 호환 범위를 확인한 고정 버전입니다. base에는 server-side apply를 사용하고 자동 prune은 비활성화합니다.

공식 chart index와 OCI endpoint에서는 1.32.0이 조회되지 않았습니다. 공식 release 아카이브와 Git tag는 확인되어 Git의 chart 경로를 사용합니다. 원본 Chart 메타데이터는 build-time placeholder 1.0.0이므로 prod values에서 실제 이미지 hub/tag를 `docker.io/istio:1.32.0`으로 명시합니다. Argo와 로컬 검증은 같은 고정 Git 소스와 values를 사용합니다.


실제 bootstrap은 base Application Synced/Healthy와 CRD Established를 확인한 뒤 istiod를 등록하고 Deployment Available까지 대기합니다. CRD 실패나 timeout이면 후속 단계로 진행하지 않습니다. istiod의 Deployment 준비와 admission webhook/Service endpoint를 각각 확인해야 실제 제어 경로가 검증됩니다. 로컬 렌더링만으로 webhook Ready를 주장하지 않습니다.

bootstrap은 `more-naive-prod` namespace만 `istio-injection=enabled`로 표시합니다. backend는 이 namespace를 사용하고 PostgreSQL은 prod values의 pod annotation으로 injection을 비활성화합니다. argocd/dev namespace는 injection 대상으로 지정하지 않습니다.

권한과 설치·실패 진단은 [Argo CD 문서](argocd/README.md)를 따릅니다. 실제 prod CRD·istiod·webhook Ready는 접근 입력이 준비된 뒤 확인합니다. 기존 프록시나 공인 포트를 변경하지 않습니다.

업그레이드는 base CRD→istiod→gateway/data plane 순서와 공식 지원 범위를 확인합니다. 앱 이미지의 Git revert와 CRD downgrade는 다릅니다. CRD 삭제는 사용자 리소스에 영향을 주므로 롤백 수단으로 사용하지 않습니다. [공식 Helm 설치](https://istio.io/latest/docs/setup/install/helm/)와 [버전 지원 범위](https://istio.io/latest/docs/releases/supported-releases/)를 따릅니다.
