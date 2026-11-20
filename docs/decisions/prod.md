# prod 배포 계약

이 프로젝트는 PostgreSQL의 `test(id bigint, value text)` 행을 다루는 최소 Kotlin/Spring Boot API를 prod 하나에 배포합니다. dev는 비활성 문서 폴더이며 local 앱/테스트 DB와 구분합니다. 백업 설정과 복원 리허설은 이번 구축 범위에 포함하지 않습니다.

## 실행과 소유권

| 대상 | 실행 주체와 관리 방식 |
| --- | --- |
| 인프라 | 운영자 호스트에서 Terraform CLI와 Terragrunt를 직접 실행합니다. provider로 자원을 관리하며 필요한 설치 명령만 provisioner로 실행합니다. |
| RustFS | prod k3s 밖의 지속 관리 가능한 Docker 호스트에서 Terraform Docker provider로 구동합니다. 2026-11-15 확인한 `system-design-study` VM의 Docker에서 유지하며 k3s 리소스로 옮기지 않습니다. |
| bootstrap state | 관리 호스트의 캐시·checkout 밖 절대 경로에 local backend로 보관합니다. RustFS 자체 state를 자신의 S3 backend로 이전하지 않습니다. |
| prod state | RustFS 버킷의 `more-naive/prod/<unit>/terraform.tfstate`와 native `.tflock`을 사용합니다. AWS S3/DynamoDB 자원은 만들지 않습니다. |
| Kubernetes | 최초 bootstrap이 k3s·Argo CD를 준비하고 이후 리소스는 선언 파일과 Helm values를 Argo CD가 관리합니다. |
| 앱/DB 설정 | 루트 `env.prod`에서 필요한 값만 외부 주입 도구가 Secret/ConfigMap으로 저장합니다. chart와 Argo CD가 같은 값 객체를 중복 생성하지 않습니다. |
| 이미지 | CI가 `GITHUB_TOKEN`으로 GHCR에 게시하고 익명 digest pull 확인 후 동일 digest의 prod 설정 PR을 만듭니다. 클러스터 pull Secret은 사용하지 않습니다. |
| 반복 배포 | 추적 브랜치에 설정 PR을 merge하면 Argo CD가 자동 sync합니다. 자동 prune은 비활성화합니다. |

최초 package가 private이면 저장소 관리자가 public으로 전환한 뒤 익명 pull을 다시 확인합니다. CI는 클러스터에 직접 접속하지 않습니다.

## 고정 버전

2026-11-14 공식 배포 정보와 호환 범위를 확인한 값입니다. 2026-11-15 k3s·Argo CD·PostgreSQL·기존 RustFS의 실제 버전을 확인했습니다. backend·Istio·외부 HTTPS 경로의 운영 배포는 아직 수행하지 않았습니다.

| 도구 | 고정 버전 | 근거와 적용 범위 |
| --- | --- | --- |
| JDK | 21 | [Spring Boot 3.5 시스템 요구사항](https://docs.spring.io/spring-boot/3.5/system-requirements.html)을 따릅니다. |
| Spring Boot | 3.5.16 | 위 3.5 문서와 Maven 배포 아티팩트를 확인합니다. |
| Kotlin | 2.2.21 | [Kotlin Gradle 호환 범위](https://kotlinlang.org/docs/gradle-configure-project.html)를 따릅니다. |
| Gradle | 8.14.3 | 공식 Wrapper와 배포본 checksum은 backend README에 기록합니다. |
| PostgreSQL | 17.12-alpine | [PostgreSQL 버전 정책](https://www.postgresql.org/support/versioning/)과 게시된 이미지 태그를 확인합니다. |
| Terraform | 1.17.2 | [공식 릴리스](https://github.com/hashicorp/terraform/releases/tag/v1.17.2)를 사용합니다. |
| Terragrunt | 1.2.2 | [공식 릴리스](https://github.com/gruntwork-io/terragrunt/releases/tag/v1.2.2)를 사용합니다. |
| RustFS | 1.0.5 | [공식 릴리스](https://github.com/rustfs/rustfs/releases/tag/1.0.5)의 이미지 digest를 bootstrap에서 검증합니다. |
| Docker provider | 4.7.0 | [공식 릴리스](https://github.com/kreuzwerker/terraform-provider-docker/releases/tag/v4.7.0)를 사용합니다. |
| k3s | v1.35.10+k3s1 | [k3s 1.35 릴리스](https://docs.k3s.io/release-notes/v1.35.X)의 고정 패치를 사용합니다. |
| Istio | 1.32.0 | [지원 범위](https://istio.io/latest/docs/releases/supported-releases/)에 Kubernetes 1.35가 포함됩니다. |
| Argo CD chart / 앱 | 10.18.0 / v3.6.1 | [고정 chart 메타데이터](https://github.com/argoproj/argo-helm/blob/argo-cd-10.18.0/charts/argo-cd/Chart.yaml)를 사용합니다. |
| Helm | 4.3.2 | [공식 릴리스](https://github.com/helm/helm/releases/tag/v4.3.2)의 Linux 바이너리 checksum을 검증합니다. |
| Tailscale | 1.104.7 | [공식 릴리스](https://github.com/tailscale/tailscale/releases/tag/v1.104.7)를 신규 노드 설치 기준으로 사용합니다. 기존 proxy는 관측 후 변경 필요 여부를 판단합니다. |

## 실제 연결 정보와 확인할 입력

사용자가 제공한 `study@study-k3s-access.tail373827.ts.net`에 기존에 확인한 SSH host key와 개인키 파일로 접속하고 hostname·sudo를 확인했습니다. Tailnet peer `100.90.91.104`는 gateway이며 실제 VM의 hostname은 `system-design-study`, 내부 주소는 `172.30.104.10`입니다. 운영자 호스트의 Tailscale Running·peer ping을 검사하며 VM 안의 Tailscale daemon을 요구하지 않습니다. 키·토큰·비밀번호·kubeconfig 내용은 문서나 로그에 저장하지 않습니다.

| 항목 | 2026-11-15 실제 상태 | 근거·남은 범위 |
| --- | --- | --- |
| prod 호스트/노드 | 제공된 Ubuntu 24.04 VM 재사용, 단일 k3s server `system-design-study`, 12 vCPU·약 12GiB RAM | 새 VM 조달 없음, [설치·Ready·DNS raw](https://github.com/naive-first/more-naive/pull/49#issuecomment-6894253308) |
| prod namespace | `more-naive-prod` 생성, 외부 Secret/ConfigMap 주입 후 PostgreSQL 배포 | dev 비활성 유지 |
| StorageClass | 기본 `local-path` 확인, DB PVC 5Gi Bound | 설치 전 root 여유 약 89GiB, 단일 노드·디스크는 HA 아님 |
| RustFS 호스트/영속 경로 | 같은 VM의 k3s 밖 Docker, `/var/lib/more-naive/rustfs-data` UID 10001 | 기존 컨테이너 healthy 유지 |
| bootstrap state | `/var/lib/more-naive/rustfs-state/bootstrap.tfstate` local backend 유지 | 자신의 RustFS S3로 이전하지 않음 |
| prod state | `more-naive-tfstate` 버킷, 별도 `more-naive-state` 인증, k3s/argocd key 생성 | 실제 두 state 읽기 성공·prod 밖 읽기 403, 잠금 충돌·장애 리허설은 별도 |
| 운영자 API/state 접근 | SSH loopback tunnel: API `https://127.0.0.1:16443`, RustFS `http://127.0.0.1:19000` | Kubernetes CA/클라이언트 인증 유지, 관리 포트 공인 개방 없음 |
| PostgreSQL | Service DNS 인증 SQL 성공, 17.12, Pod 1/1·PVC Bound | [배포·SQL raw](https://github.com/naive-first/more-naive/pull/48#issuecomment-6894361467), Pod 재시작 데이터 보존·backend 연동은 미검증 |
| HTTPS hostname/TLS 종료/upstream | 미배포·미확정 | VM/tailnet 운영자, #38·#23 실행 전 확인 |
| 허용 사용자/접근 정책 | 제공된 `study` SSH·sudo 및 현재 operator Tailnet 연결 확인 | tailnet 전체 ACL 검토·변경은 수행하지 않음 |

터널·kubeconfig·env·state 인증 파일은 운영자 전용으로 보관합니다. SSH 터널은 클라이언트 연결에 의존하므로 종료 후에는 같은 검증된 목적지와 포워딩으로 다시 연결해야 합니다. 실제 Argo 설치와 공개 저장소 sync는 [Argo raw](https://github.com/naive-first/more-naive/pull/52#issuecomment-6894360960)에 기록했습니다.

## 입력과 접근 경계

루트 `env.dev`와 `env.prod`로 환경을 구분하며 두 파일은 동일한 `DB_*`, `KUBE_*`, `SSH_*` 키를 사용합니다. 공통 템플릿은 `env.example`입니다. `MORE_NAIVE_ENV=dev|prod direnv exec config/env <command>`로 환경을 명시합니다. 검토한 `config/env/.envrc`를 한 번 허용하고 표준 dotenv 문법을 사용하며, 선택한 파일이 없으면 중단합니다. dev 선택은 로컬 앱/Compose에만 허용하고 인프라는 prod만 실행합니다. Spring과 Terragrunt가 dotenv를 자동으로 읽는다고 가정하지 않습니다. RustFS 관리자, state 전용 인증, 실제 인프라 provider 인증은 별개입니다.

비밀값·Terraform state/plan·kubeconfig는 Git·이미지·원본 실행 로그에 포함하지 않습니다. `env.dev`·`env.prod`와 bootstrap local state는 운영자 전용 권한으로 보관합니다. Secret controller·외부 비밀 저장소와 GHCR pull Secret은 도입하지 않습니다.

## 확인과 재실행

설치 도구의 `--version`, Helm lint/template, Terraform fmt/validate, 격리된 PostgreSQL/RustFS 검증을 각 구현 PR에서 수행합니다. prod 접근 정보가 필요한 실행은 실제 명령·종료 코드와 미수행 이유를 PR에 기록합니다. preview와 문서의 명령 예시는 설치 완료 증거가 아닙니다.

RustFS health·버킷 권한·잠금 충돌·장애 중단을 확인한 뒤 prod plan/apply를 진행합니다. 잘못된 환경/context·계정·endpoint 또는 필수 입력 누락은 쓰기 전에 중단하며 dev나 local 값으로 대체하지 않습니다. prod 쓰기 smoke는 명시적 opt-in 후 도구가 직접 만든 행만 변경·정리합니다.

재실행은 같은 backend 경로와 state lineage를 먼저 확인합니다. RustFS state·데이터와 PostgreSQL PVC의 삭제는 컨테이너/Pod 재시작과 다릅니다. 일반 prod destroy가 RustFS bootstrap 데이터를 포함하지 않게 하고, PVC 삭제나 백업/복원 실험을 smoke에 넣지 않습니다.
