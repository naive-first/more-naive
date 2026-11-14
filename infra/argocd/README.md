# prod Argo CD

Terraform Helm provider 3.3.0이 고정 chart `10.18.0`/Argo CD `v3.6.1`과 `infra/environments/prod/argocd.yaml`을 bootstrap 소유로 관리합니다. Argo CD 자체를 관리하는 Application은 만들지 않습니다. workload는 GitOps가 소유하며 root는 prod child `*.yaml`만 추적하고 자동 prune은 비활성화합니다.

운영자가 k3s Ready, 실제 kubeconfig/context/API server, RustFS 버킷과 별도 state 인증을 준비한 뒤 `env.prod`의 공통 키로 실행합니다. Helm provider는 KUBECONFIG를 자동으로 읽지 않으므로 명시한 파일 목록을 전달합니다. 미설정 시 kubectl과 같은 `~/.kube/config`를 명시합니다. Terraform CLI 1.17.2, Terragrunt 1.2.2, kubectl, Helm 4.3.2가 필요합니다.

```bash
python3 scripts/env.py --env prod argocd-terraform -- terragrunt --working-dir infra/terragrunt/live/prod/argocd run -- init -input=false
python3 scripts/env.py --env prod argocd-terraform -- terragrunt --working-dir infra/terragrunt/live/prod/argocd run -- plan -input=false -out=/absolute/private/argocd.tfplan
python3 scripts/env.py --env prod argocd-terraform -- terragrunt --working-dir infra/terragrunt/live/prod/argocd run -- apply -input=false /absolute/private/argocd.tfplan
```

각 실행은 context/API 주소 일치와 chart 렌더링을 먼저 확인합니다. state key는 `more-naive/prod/argocd/terraform.tfstate`입니다. Helm provider가 namespace·CRD·release를 설치하고 wait를 완료한 뒤 `terraform_data`의 local-exec가 기존 등록 스크립트로 Ready→project/root 등록·Synced를 확인합니다. 매 apply는 등록 실행 기록을 교체해 state 밖의 repository 인증도 갱신합니다. Python이 Terraform이나 Helm upgrade를 대신 실행하지 않습니다.

기존 Helm release가 Terraform state에 없으면 provider의 새 release 생성이 실패합니다(`replace=false`). 운영자가 context·release·state lineage를 확인한 뒤 필요할 때만 별도 import를 검토합니다. 자동 takeover·state migration·release 교체는 하지 않습니다.

공개 저장소는 인증 없이 사용합니다. private 저장소의 read-only `ARGO_REPO_TOKEN`은 `ARGO_REPO_USERNAME`과 함께 기존 repository Secret stdin 주입 경로로만 사용합니다. values·plan·state·argv·로그에는 넣지 않고 kubectl/Helm 자식 환경에서도 제거합니다. `env.prod` 전체나 admin 초기 비밀번호는 출력하지 않습니다.

server Service는 ClusterIP이며 ingress/공인 포트를 생성하지 않습니다. default RBAC는 권한을 부여하지 않고 exec·Dex·알림·ApplicationSet은 비활성화합니다. 반복 workload 배포는 main의 root/child 자동 sync가 담당합니다. 실패하면 context/API→노드 Ready→Helm release→repo-server 읽기→Application 상태를 확인합니다. Secret/kubeconfig 전체 출력은 공유하지 않습니다.

실제 prod 설치·repo 읽기·자동 sync는 이 로컬 검증에서 수행하지 않습니다. 삭제는 제어 중단과 Application/PVC 영향을 먼저 검토하며 자동 uninstall·PVC 삭제·백업/복원은 범위 밖입니다. [선언형 구성](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/)과 [자동 sync 정책](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)을 따릅니다.
