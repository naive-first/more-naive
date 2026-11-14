# prod Argo CD

고정 chart `10.18.0`/Argo CD `v3.6.1`과 `infra/environments/prod/argocd.yaml`은 bootstrap이 소유합니다. Argo CD 자체를 관리하는 별도 Application은 만들지 않습니다. root는 prod child `*.yaml`만 자동 추적하고 자동 prune은 비활성화합니다.

```bash
python3 scripts/env.py argocd -- python3 infra/argocd/bootstrap/bootstrap.py \
  --environment prod --context '<prod-context>' --expected-server 'https://<실제 API 주소>:6443'
```

루트 `.env` 도구 #41과 k3s Ready가 선행 조건입니다. Python3·kubectl·Helm4.3.2, 지정 context의 namespace/CRD/RBAC 설치 권한이 필요합니다. 기본 실행은 context API 주소 일치와 chart 렌더링만 검사합니다. 연결 정보를 확인한 뒤 `--apply`를 추가하면 namespace·필요한 저장소 인증→Helm 설치/갱신→Ready→root 등록·Synced 대기 순서로 진행합니다. UI에서 복사해 등록하지 않습니다.

공개 저장소는 인증 없이 사용합니다. private인 경우 필요한 read-only `ARGO_REPO_TOKEN`과 선택적 `ARGO_REPO_USERNAME`만 외부로 전달합니다. 코드가 repository Secret을 stdin으로 주입하며 values/Git/로그에 자격 증명을 남기지 않습니다. 전체 `.env`를 올리지 않습니다. admin 초기 비밀번호도 이 도구가 출력하지 않습니다.

server Service는 ClusterIP이며 ingress/공인 포트를 생성하지 않습니다. 필요할 때 허용된 운영자가 별도 인증 절차로 접근합니다. default RBAC 정책은 권한을 부여하지 않고 exec·미사용 Dex/알림/ApplicationSet은 비활성화합니다.

반복 배포는 설정 PR을 main에 merge하면 root/child의 자동 sync가 담당합니다. bootstrap 재실행은 같은 values로 Helm을 갱신하고 선언을 apply합니다. 실패하면 context/API 주소→노드 Ready→Helm 리소스→repo-server의 저장소 읽기와 Application 상태를 확인합니다. `kubectl get secret -o yaml`과 전체 kubeconfig 출력은 사용하지 않습니다.

설치 제거는 Argo CD 제어를 중단하며 자동 prune 비활성화가 모든 수동 삭제를 막는 것은 아닙니다. 삭제 전에 Application·PVC 영향을 검토합니다. 실제 prod 설치·repo 읽기·자동 sync는 SSH/kubeconfig 미준비로 아직 확인하지 못했습니다. 로컬 chart 렌더링 검증과 구분합니다. [선언형 구성](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/)과 [자동 sync 정책](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)을 따릅니다.

## 프로젝트별 허용 범위

| 프로젝트 | source/destination | 허용 리소스 |
| --- | --- | --- |
| bootstrap | 이 저장소/main, argocd | Application·AppProject만 |
| platform | 이 저장소·공식 Istio charts, istio-system | 명시한 Istio 기반·RBAC·CRD·webhook·gateway |
| backend | 이 저장소/main, more-naive-prod | Deployment·Service·VirtualService |
| DB | 이 저장소/main, more-naive-prod | StatefulSet·Service·PVC |

default project와 wildcard destination/resource에 의존하지 않습니다. backend/DB 프로젝트는 외부 주입 Secret/ConfigMap을 생성하거나 selfHeal로 덮어쓸 권한이 없습니다. namespace는 bootstrap이 argocd·istio-system·more-naive-prod만 준비합니다.

최초 bootstrap은 프로젝트를 준비한 뒤 존재하는 child를 Istio base→control plane→gateway→PostgreSQL→backend 순으로 선언합니다. 각 Application의 Synced/Healthy와 CRD Established·Deployment Available·StatefulSet rollout을 실제 대기한 뒤 다음 단계로 진행합니다. sync-wave 숫자를 다른 Application의 준비 완료로 취급하지 않습니다. Secret/ConfigMap은 #16 주입이 먼저 성공해야 DB/앱이 준비됩니다. 오류나 timeout은 다음 단계와 root 등록을 중단합니다.

이후 main 변경은 automated enabled/selfHeal로 재조정하며 prune/allowEmpty는 false입니다. 호환되는 이전 digest/config를 Git revert하는 방식으로 되돌리고 DB 데이터 복원과 구분합니다. 선언 제거만으로 자원을 자동 삭제하지 않습니다. 명시적 삭제는 운영자가 리소스와 PVC 의존관계를 확인한 뒤 별도 수행하며 root/child에 자동 cascade 삭제 finalizer를 설정하지 않습니다.
