# prod 배포 계약

이 프로젝트는 PostgreSQL의 `test(id bigint, value text)` 행을 다루는 최소 Kotlin/Spring Boot API를 prod 하나에 배포합니다. dev는 비활성 문서 폴더이며 local 앱/테스트 DB와 구분합니다. 백업 설정과 복원 리허설은 이번 구축 범위에 포함하지 않습니다.

## 실행과 소유권

| 대상 | 실행 주체와 관리 방식 |
| --- | --- |
| 인프라 | 운영자 호스트의 Go terraform-exec SDK가 Terraform CLI를 실행합니다. Terragrunt는 HCL의 source·backend·inputs 준비와 버킷 bootstrap만 담당합니다. |
| RustFS | prod k3s 밖의 지속 관리 가능한 Docker 호스트에서 Terraform Docker provider로 구동합니다. 실제 관리 호스트는 운영자가 #39 적용 전에 확인합니다. |
| bootstrap state | 관리 호스트의 캐시·checkout 밖 절대 경로에 local backend로 보관합니다. RustFS 자체 state를 자신의 S3 backend로 이전하지 않습니다. |
| prod state | RustFS 버킷의 `more-naive/prod/<unit>/terraform.tfstate`와 native `.tflock`을 사용합니다. AWS S3/DynamoDB 자원은 만들지 않습니다. |
| Kubernetes | 최초 bootstrap이 k3s·Argo CD를 준비하고 이후 리소스는 선언 파일과 Helm values를 Argo CD가 관리합니다. |
| 앱/DB 설정 | 루트 `env.prod`에서 필요한 값만 외부 주입 도구가 Secret/ConfigMap으로 저장합니다. chart와 Argo CD가 같은 값 객체를 중복 생성하지 않습니다. |
| 이미지 | CI가 `GITHUB_TOKEN`으로 GHCR에 게시하고 익명 digest pull 확인 후 동일 digest의 prod 설정 PR을 만듭니다. 클러스터 pull Secret은 사용하지 않습니다. |
| 반복 배포 | 추적 브랜치에 설정 PR을 merge하면 Argo CD가 자동 sync합니다. 자동 prune은 비활성화합니다. |

최초 package가 private이면 저장소 관리자가 public으로 전환한 뒤 익명 pull을 다시 확인합니다. CI는 클러스터에 직접 접속하지 않습니다.

## 고정 버전

2026-11-14 공식 배포 정보와 호환 범위를 확인한 값입니다. 버전 고정과 실제 prod 설치 검증은 별개이며 아래 값으로 prod 검증을 수행했다고 주장하지 않습니다.

| 도구 | 고정 버전 | 근거와 적용 범위 |
| --- | --- | --- |
| JDK | 21 | [Spring Boot 3.5 시스템 요구사항](https://docs.spring.io/spring-boot/3.5/system-requirements.html)을 따릅니다. |
| Spring Boot | 3.5.16 | 위 3.5 문서와 Maven 배포 아티팩트를 확인합니다. |
| Kotlin | 2.2.21 | [Kotlin Gradle 호환 범위](https://kotlinlang.org/docs/gradle-configure-project.html)를 따릅니다. |
| Gradle | 8.14.3 | 공식 Wrapper와 배포본 checksum은 backend README에 기록합니다. |
| PostgreSQL | 17.12-alpine | [PostgreSQL 버전 정책](https://www.postgresql.org/support/versioning/)과 게시된 이미지 태그를 확인합니다. |
| Go / terraform-exec | 1.27.4 / v0.26.0 | [공식 SDK](https://github.com/hashicorp/terraform-exec/tree/v0.26.0)를 실행 계층으로 사용합니다. |
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

사용자가 제공한 SSH 대상은 `study@study-k3s-access.tail373827.ts.net`입니다. 공개키와 macOS의 `~/.ssh/study-k3s-access` 경로가 제공됐지만 현재 Linux 작업 호스트에는 해당 개인키와 SSH 별칭이 없습니다. tailnet 주소 `100.90.91.104`는 조회됐으며 SSH 인증·sudo·기존 HTTPS 설정은 아직 확인하지 못했습니다. 키의 내용은 문서나 로그에 저장하지 않습니다.

| 항목 | 현재 상태 | 확인 주체·시점 |
| --- | --- | --- |
| prod 공급자/계정/region | 미제공. 기존 VM 재사용과 새 VM 생성 중 결정 필요 | 운영자, network/compute 구현 전 |
| 노드 수/역할/사양 | 미제공. 제공된 SSH VM의 prod 노드 역할도 미확인 | 운영자, #8·#37 실행 전 |
| prod namespace | `more-naive-prod`를 프로젝트 기본값으로 사용 | bootstrap이 실제 context와 함께 검증 |
| StorageClass | k3s `local-path`를 후보로 사용하되 실제 존재·디스크 용량은 미확인 | 운영자, #36 배포 전 |
| RustFS 호스트/영속 경로 | prod k3s 밖 Docker 호스트, 절대 경로는 외부 입력 | 운영자, #39 적용 전 |
| state endpoint/버킷/최소 권한 인증 | 루트 `env.prod`의 RustFS 전용 입력 | 운영자, #4 실행 전 |
| SSH 개인키 | 현재 작업 호스트의 파일 경로 필요 | 사용자, 원격 검사 전 |
| HTTPS hostname/TLS 종료/upstream | 기존 VM 설정을 읽은 뒤 확정. VM에서 ClusterIP 직접 접근을 가정하지 않음 | VM/tailnet 운영자, #38·#23 실행 전 |
| 허용 사용자/접근 정책 | 기존 tailnet 정책을 먼저 확인. 공인 SSH·Funnel을 기본 개방하지 않음 | tailnet 운영자, #37·#38 실행 전 |

## 입력과 접근 경계

루트 `env.dev`와 `env.prod`로 환경을 구분하며 두 파일은 동일한 `DB_*`, `KUBE_*`, `SSH_*` 키를 사용합니다. 공통 템플릿은 `env.example`입니다. `python3 scripts/env.py --env dev|prod <consumer> -- <command>`로 환경과 소비자를 명시하고 필요한 키만 전달합니다. 환경 파일은 shell 코드로 실행하지 않으며 다른 환경 파일로 대체하지 않습니다. dev 선택은 로컬 앱/Compose에만 허용하고 인프라는 prod만 실행합니다. Spring과 Terragrunt가 dotenv를 자동으로 읽는다고 가정하지 않습니다. RustFS 관리자, state 전용 인증, 실제 인프라 provider 인증은 별개입니다.

비밀값·Terraform state/plan·kubeconfig는 Git·이미지·원본 실행 로그에 포함하지 않습니다. `env.dev`·`env.prod`와 bootstrap local state는 운영자 전용 권한으로 보관합니다. Secret controller·외부 비밀 저장소와 GHCR pull Secret은 도입하지 않습니다.

## 확인과 재실행

설치 도구의 `--version`, Helm lint/template, Terraform fmt/validate, 격리된 PostgreSQL/RustFS 검증을 각 구현 PR에서 수행합니다. prod 접근 정보가 필요한 실행은 실제 명령·종료 코드와 미수행 이유를 PR에 기록합니다. preview와 문서의 명령 예시는 설치 완료 증거가 아닙니다.

RustFS health·버킷 권한·잠금 충돌·장애 중단을 확인한 뒤 prod plan/apply를 진행합니다. 잘못된 환경/context·계정·endpoint 또는 필수 입력 누락은 쓰기 전에 중단하며 dev나 local 값으로 대체하지 않습니다. prod 쓰기 smoke는 명시적 opt-in 후 도구가 직접 만든 행만 변경·정리합니다.

재실행은 같은 backend 경로와 state lineage를 먼저 확인합니다. RustFS state·데이터와 PostgreSQL PVC의 삭제는 컨테이너/Pod 재시작과 다릅니다. 일반 prod destroy가 RustFS bootstrap 데이터를 포함하지 않게 하고, PVC 삭제나 백업/복원 실험을 smoke에 넣지 않습니다.
