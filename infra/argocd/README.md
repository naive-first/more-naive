# prod Argo CD

Terraform Helm provider 3.3.0이 고정 chart `10.18.0`/Argo CD `v3.6.1`과 `infra/environments/prod/argocd.yaml`을 bootstrap 소유로 관리합니다. Argo CD 자체를 관리하는 Application은 만들지 않습니다. workload는 GitOps가 소유하며 root는 prod child `*.yaml`만 추적하고 자동 prune은 비활성화합니다.

운영자가 k3s Ready, 실제 kubeconfig/context/API server, RustFS 버킷과 별도 state 인증을 준비한 뒤 `env.prod`의 공통 키로 실행합니다. 먼저 `direnv allow config/env`를 검토·허용합니다. Helm provider는 KUBECONFIG를 자동으로 읽지 않으므로 명시한 파일 목록을 전달합니다. 미설정 시 kubectl과 같은 `~/.kube/config`를 명시합니다. Terraform CLI 1.17.2, Terragrunt 1.2.2, kubectl, Helm 4.3.2가 필요합니다.

```bash
umask 077
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/argocd run -- init -input=false
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/argocd run -- plan -input=false -out=/absolute/private/argocd.tfplan
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/argocd run -- apply -input=false /absolute/private/argocd.tfplan
```

각 실행은 context/API 주소 일치와 chart 렌더링을 먼저 확인합니다. state key는 `more-naive/prod/argocd/terraform.tfstate`입니다. Helm provider가 namespace·CRD·release를 설치하고 wait를 완료한 뒤 `terraform_data`의 local-exec가 Bash·kubectl 등록 단계로 Ready→project/root 등록·Synced를 확인합니다. 매 apply는 등록 실행 기록을 교체해 state 밖의 repository 인증도 갱신합니다. 운영 단계에 Python이 필요하지 않습니다.

기존 Helm release가 Terraform state에 없으면 provider의 새 release 생성이 실패합니다(`replace=false`). 운영자가 context·release·state lineage를 확인한 뒤 필요할 때만 별도 import를 검토합니다. 자동 takeover·state migration·release 교체는 하지 않습니다.

공개 저장소는 인증 없이 사용합니다. private 저장소의 read-only `ARGO_REPO_TOKEN`은 `ARGO_REPO_USERNAME`과 함께 기존 repository Secret stdin 주입 경로로만 사용합니다. values·plan·state·argv·로그에는 넣지 않고 kubectl/Helm 자식 환경에서도 제거합니다. `env.prod` 전체나 admin 초기 비밀번호는 출력하지 않습니다.

server Service는 ClusterIP이며 ingress/공인 포트를 생성하지 않습니다. default RBAC는 권한을 부여하지 않고 exec·Dex·알림은 비활성화합니다. ApplicationSet 리소스는 사용하지 않지만 chart 10.18.0에서 ApplicationSet controller도 실행 중입니다. 반복 workload 배포는 main의 root/child 자동 sync가 담당합니다. 실패하면 context/API→노드 Ready→Helm release→repo-server 읽기→Application 상태를 확인합니다. Secret/kubeconfig 전체 출력은 공유하지 않습니다.

2026-11-15 실제 prod에 native Terraform Helm provider로 설치했습니다. 고정 chart/app 버전, controller Ready와 공개 저장소 읽기를 확인했고 `more-naive-prod`, `more-naive-projects`, `postgres`가 Synced/Healthy입니다. [실제 init·plan·apply와 확인 raw](https://github.com/naive-first/more-naive/pull/52#issuecomment-6894360960)를 참조합니다. 운영 API는 검증한 SSH 연결의 loopback 터널 `https://127.0.0.1:16443`으로 접근하며 kubeconfig의 CA·클라이언트 인증을 유지합니다. 삭제는 제어 중단과 Application/PVC 영향을 먼저 검토하며 자동 uninstall·PVC 삭제·백업/복원은 범위 밖입니다. [선언형 구성](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/)과 [자동 sync 정책](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)을 따릅니다.

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

## native 검증

등록 스크립트의 Bash 문법을 확인하고, Application이 지정한 Istio commit `38ee3e789233243dfadb0eddbcbaafac87bc7141` 소스를 저장소 밖에 받아 같은 prod values로 렌더링합니다. 아래 `ISTIO_SOURCE`는 그 고정 소스를 압축 해제한 절대 경로입니다.

```bash
bash -n infra/argocd/bootstrap/bootstrap.sh
helm template istio-base "$ISTIO_SOURCE/manifests/charts/base" --namespace istio-system --values infra/environments/prod/istio-base.yaml
helm template istiod "$ISTIO_SOURCE/manifests/charts/istio-control/istio-discovery" --namespace istio-system --values infra/environments/prod/istiod.yaml
```

실제 prod 반영 시에는 위 bootstrap의 `--apply`가 base Synced/Healthy와 CRD Established 뒤에 istiod를 등록하고 Available을 기다리는지 실행 결과로 확인합니다. `kubectl --context "$KUBE_CONTEXT" -n argocd get applications`와 `kubectl --context "$KUBE_CONTEXT" -n istio-system rollout status deployment/istiod --timeout=300s`를 기록합니다. 잘못된 context/API나 CRD 대기 실패에서는 후속 등록을 중단해야 합니다. 로컬 렌더링으로 CRD·webhook·운영 설치 완료를 주장하지 않습니다.
