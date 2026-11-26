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

server Service는 ClusterIP이며 Kubernetes Ingress/공인 포트를 생성하지 않습니다. tailnet UI는 기존 Istio gateway를 통한 `/argocd/` 경로로 연결합니다. default RBAC는 권한을 부여하지 않고 exec·Dex·알림은 비활성화합니다. ApplicationSet 리소스는 사용하지 않지만 chart 10.18.0에서 ApplicationSet controller도 실행 중입니다. 반복 workload 배포는 main의 root/child 자동 sync가 담당합니다. 실패하면 context/API→노드 Ready→Helm release→repo-server 읽기→Application 상태를 확인합니다. Secret/kubeconfig 전체 출력은 공유하지 않습니다.

2026-11-15 실제 prod에 native Terraform Helm provider로 설치했습니다. 고정 chart/app 버전, controller Ready와 공개 저장소 읽기를 확인했고 `more-naive-prod`, `more-naive-projects`, `postgres`가 Synced/Healthy입니다. [실제 init·plan·apply와 확인 raw](https://github.com/naive-first/more-naive/pull/52#issuecomment-6894360960)를 참조합니다. 운영 API는 검증한 SSH 연결의 loopback 터널 `https://127.0.0.1:16443`으로 접근하며 kubeconfig의 CA·클라이언트 인증을 유지합니다. 삭제는 제어 중단과 Application/PVC 영향을 먼저 검토하며 자동 uninstall·PVC 삭제·백업/복원은 범위 밖입니다. [선언형 구성](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/)과 [자동 sync 정책](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)을 따릅니다.

## tailnet의 Argo CD 경로 적용

운영 URL은 `https://more-naive-vm.tail373827.ts.net/argocd/`입니다. 사용자는 관리자에게 tailnet 초대·기기 승인·HTTPS 서비스 접근 허용과 별도의 Argo CD 계정·역할을 받은 뒤 브라우저로 접속합니다. SSH 터널은 UI 사용에 필요하지 않습니다. GitOps 라우트와 Helm URL을 함께 동기화합니다.

| 설정 | 소유자 | 적용 값 |
| --- | --- | --- |
| TLS 종료 | Proxmox Tailscale 게이트웨이 | HTTPS 443 → VM 172.30.104.10:18080, 원래 Host 유지 |
| Gateway·Argo VirtualService | `ingress-route` GitOps Application | 동일 Host의 `/argocd/` → `argocd-server.argocd.svc.cluster.local:80` |
| Argo 서버 subpath | native Terraform의 `helm_release.argocd` | `configs.params.server.rootpath=/argocd`, `server.basehref=/argocd` |
| 내부 upstream 프로토콜 | 같은 Helm values | `configs.params.server.insecure=true`로 HTTP 사용, 외부 TLS는 유지 |
| 외부 URL | 같은 Helm values | `configs.cm.url=https://more-naive-vm.tail373827.ts.net/argocd` |

VirtualService는 prefix를 제거하지 않습니다. 정확히 `/argocd`인 요청만 HTTPS `/argocd/`로 308 redirect하고, `/argocd/` 하위를 UI·정적 파일·Argo API에 그대로 전달합니다. Gateway는 `more-naive-prod`와 `istio-system` namespace의 명시한 Host만 허용합니다. platform 프로젝트도 기존 `istio-system` destination에서 VirtualService만 추가 허용합니다. Argo Service 자체나 Helm release를 GitOps Application으로 옮기지 않습니다. [공식 Istio/subpath 안내](https://argo-cd.readthedocs.io/en/stable/operator-manual/ingress/#istio)를 따릅니다.

1. 변경을 main에 반영한 뒤 `more-naive-projects`와 `ingress-route` Application의 Synced/Healthy를 확인합니다. main의 GitOps 선언을 임시 kubectl patch로 대체하지 않습니다.
2. 운영 kubeconfig·승인된 환경 loader·RustFS state 접근을 준비하고 이 문서 앞의 native Terragrunt `init` → 저장 `plan` → 검토 후 `apply`를 실행합니다. kubeconfig는 `https://more-naive-vm.tail373827.ts.net:6443`과 기존 k3s CA를 사용합니다.
3. plan에서 기존 `helm_release.argocd`의 values 갱신과 bootstrap 등록만 예상합니다. destroy/recreate, DB/PVC/state 변경이 있으면 적용을 중단합니다. private plan/state 내용과 자격 증명은 로그로 출력하지 않습니다.
4. Helm wait와 bootstrap 완료 뒤 아래 상태·접속 검증을 수행합니다. values 파일의 Git merge만으로 Helm release가 자동 갱신되지는 않습니다.

게이트웨이 전환 중에 임시 override를 적용한 클러스터에서는 Git main의 두 prod values와 실제 `argocd-cm` URL이 모두 새 주소인지 확인합니다. 두 자식 Application의 `status.sync.revisions`에서 새 values가 포함된 Git 리비전을 확인한 뒤 정리합니다. `more-naive-prod` 부모 Application에서 `ingress-route`의 `host`와 `backend`의 `routing.host` 파라미터를 대상으로 하는 두 `ignoreDifferences` 항목만 제거합니다. 다른 무시 규칙이 `RespectIgnoreDifferences=true`를 사용하면 해당 옵션을 유지합니다. 그 다음 자식 Application의 해당 Helm 파라미터만 제거하고 세 Application이 다시 Synced·Healthy인지 확인합니다. `istio-base`와 `istiod`의 webhook 무시 규칙은 각 Application이 관리합니다.

```bash
kubectl --context "$KUBE_CONTEXT" -n argocd rollout status deployment/argocd-server --timeout=300s
kubectl --context "$KUBE_CONTEXT" -n argocd get applications \
  more-naive-projects ingress-route -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status
```

CLI 명령은 저장소 루트에서 실행하며 `KUBE_CONTEXT` 등은 승인된 prod 환경 loader로 주입합니다. 이미 승인된 외부 loader를 사용하는 경우 `MORE_NAIVE_ENV=prod direnv exec <승인된-loader-절대경로> <명령>`으로 실행합니다. dotenv 파일 전체를 source/출력하거나 다른 worktree의 환경을 덮어쓰지 않습니다.

### UI·정적 파일·로그인·API 확인

Tailscale에 연결한 클라이언트에서 TLS 검증을 켠 채 실행합니다. 두 curl 요청은 각각 최종 HTTP 200과 `/argocd/` URL, API HTTP 200이어야 합니다. 요청 실패·redirect 반복은 성공으로 처리하지 않습니다.

```bash
curl --fail --silent --show-error --location --max-redirs 3 \
  --output /dev/null --write-out '%{http_code} %{url_effective}\n' \
  https://more-naive-vm.tail373827.ts.net/argocd
curl --fail --silent --show-error --output /dev/null --write-out '%{http_code}\n' \
  https://more-naive-vm.tail373827.ts.net/argocd/api/v1/settings
curl --fail --silent --show-error --output /dev/null --write-out '%{http_code}\n' \
  https://more-naive-vm.tail373827.ts.net/backend/api/tests
```

브라우저에서 `/argocd/`를 열고 개발자 도구 Network에서 JavaScript·CSS가 `/argocd/` 아래의 URL로 200을 받는지 확인합니다. 승인된 계정으로 로그인한 뒤 Application 목록·상세를 열고 새로고침합니다. 로그인 화면 재등장, `/api/v1/...` 루트로 빠지는 요청, 정적 파일 404, 콘솔 오류가 없어야 합니다. 로그아웃 후 인증 없는 Application 조회가 401/403으로 거부되는지도 확인합니다. 계정 역할상 허용되지 않은 Application이 보이는지 별도로 확인하며, UI 확인만으로 권한 검증을 대체하지 않습니다.

`/argocd-other`, `/`, 잘못된 Host는 gateway에서 404여야 합니다. VM의 기존 relay 경유 읽기 전용 검사 예시는 다음과 같습니다. 출력은 상태 코드만 남깁니다.

```bash
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' \
  --header 'Host: more-naive-vm.tail373827.ts.net' http://172.30.104.10:18080/argocd-other
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' \
  --header 'Host: wrong.invalid' http://172.30.104.10:18080/argocd/
```

404는 Gateway namespace/Host 허용과 VirtualService 상태를, redirect 반복은 Helm `server.insecure` 적용과 내부 HTTP 포트를, 정적 파일·API 경로 오류는 rootpath/basehref·prefix 유지를 확인합니다. 로그인 거부는 Argo 계정·RBAC부터 확인합니다. 검증 결과에는 실제 명령별 stdout/stderr/exit와 수행하지 못한 항목을 남기되 비밀번호·JWT·인증 URL·Secret/kubeconfig/state 본문을 포함하지 않습니다.

Argo CD를 이전 버전으로 복구할 때는 GitOps 라우트와 Helm subpath 값의 호환성을 함께 확인합니다. 현재 게이트웨이 주소와 `/argocd/`를 사용하도록 렌더링한 뒤 native plan/apply와 API를 재검증합니다. 자동 prune이 꺼져 있어 Git에서 VirtualService 선언을 제거해도 클러스터에서는 자동 삭제되지 않습니다.

## env에서 admin 비밀번호 설정

기본 관리자 아이디는 `admin`입니다. `env.dev`와 `env.prod`는 같은 선택 키 `ARGOCD_ADMIN_PASSWORD_HASH`를 사용하며 실제 배포는 prod만 지원합니다. 처음부터 비워 두면 Argo의 기존/초기 비밀번호를 유지합니다. 운영 비밀번호를 지정하려면 평문 대신 bcrypt 해시를 `env.prod`에 넣습니다. [고정 Helm chart의 공식 설정](https://github.com/argoproj/argo-helm/blob/argo-cd-10.18.0/charts/argo-cd/values.yaml#L673-L679)을 사용하며 별도 비밀번호 설정 스크립트를 추가하지 않습니다.

`argocd` CLI가 있는 관리 터미널에서 아래 명령을 실행하고 비밀번호를 프롬프트에 입력합니다. 평문을 명령 인자나 shell history에 넣지 않습니다. 출력된 해시도 공유 로그에 남기지 않고 로컬 env 파일로 옮깁니다.

```bash
argocd account bcrypt
```

```dotenv
# 실제 해시는 로컬 env.prod에만 입력합니다. $ 확장을 막기 위해 single quote를 사용합니다.
ARGOCD_ADMIN_PASSWORD_HASH='<bcrypt 해시>'
```

공통 direnv loader가 이 값을 Terragrunt의 `admin_password_hash`로 전달하고 Terraform은 Helm의 `configs.secret.argocdServerAdminPassword`에 `set_sensitive`로 지정합니다. 빈 값 이외에는 bcrypt 형식을 검증하므로 평문이나 잘못된 해시는 plan 단계에서 거부됩니다. env 파일을 수정하는 것만으로 실행 중인 Argo 비밀번호가 바뀌지는 않습니다.

앞의 native Terragrunt `init` → 저장 `plan` → 검토 → `apply` 절차를 사용합니다. 기존 Helm release의 비밀번호 설정 갱신과 등록 marker만 예상하고 release 재생성·다른 자원 변경이 있으면 중단합니다. 새 비밀번호로 `/argocd/`에 로그인하고 Application 목록·새로고침을 확인합니다. 변경 시 이전 비밀번호의 로그인이 거부되는지도 확인하되 비밀번호·JWT·Secret 본문은 기록하지 않습니다.

한 번 지정한 뒤 값을 비우는 것은 비밀번호 초기화 방법이 아닙니다. 비밀번호를 다시 바꾸거나 되돌리려면 원하는 새 비밀번호의 해시 또는 이전에 보관한 해시를 명시하고 plan/apply합니다. 해시는 Terraform state·저장 plan·Helm release Secret에 보관되므로 기존 state 접근 제한과 private plan 권한을 유지합니다. `sensitive`는 출력 마스킹이며 저장 암호화를 대신하지 않습니다. 실제 env 파일과 해시를 Git·PR·QA raw에 포함하지 않습니다.

클러스터나 실제 비밀번호 변경 없이 모듈 입력과 Helm 전달을 검증하려면 고정 Terraform 버전으로 실행합니다. 테스트는 mock Helm provider와 더미 해시로 plan만 수행합니다.

```bash
terraform -chdir=infra/terraform/modules/argocd-bootstrap init -backend=false -input=false
terraform -chdir=infra/terraform/modules/argocd-bootstrap test
```

## 프로젝트별 허용 범위

| 프로젝트 | source/destination | 허용 리소스 |
| --- | --- | --- |
| bootstrap | 이 저장소/main, argocd | Application·AppProject만 |
| platform | 이 저장소·공식 Istio charts, istio-system | 명시한 Istio 기반·RBAC·CRD·webhook·gateway·Argo VirtualService |
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
