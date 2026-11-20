# RustFS prod backend

prod unit이 `state.hcl`을 선택적으로 포함하면 state는 `more-naive/prod/<unit>/terraform.tfstate`, 잠금은 같은 key의 `.tflock`에 저장됩니다. Terraform 1.17.2의 native `use_lockfile`을 사용하며 AWS S3/DynamoDB 자원을 만들지 않습니다. RustFS 자체 bootstrap은 이 파일을 포함하지 않고 별도 local backend를 유지합니다.

## 준비와 인증 경계

#39 RustFS health가 정상이어야 합니다. 운영자가 #41 루트 `env.prod`에 `RUSTFS_ENDPOINT`, `RUSTFS_BUCKET`, `RUSTFS_REGION`, 관리자용 `RUSTFS_ADMIN_*`, 별도 state용 state profile를 준비합니다. endpoint 누락·비정상 인증·dev 선택은 중단하며 AWS 기본 endpoint/local state로 전환하지 않습니다. HTTP는 loopback만 허용합니다. 원격 관리자는 인증서가 검증되는 사설 HTTPS나 loopback TLS 터널을 준비합니다.

운영자가 준비한 checkout 밖의 0600 profile을 `RUSTFS_CREDENTIALS_FILE`로 지정합니다. 관리자용·일상 state용 파일을 분리하며 런타임에서 생성하거나 덮어쓰지 않습니다. 기존 AWS 환경의 default endpoint/profile로 대체하지 않습니다. 실제 provider 인증은 별도로 준비합니다.

Terragrunt 1.2.2는 `shared_credentials_file`을 shared config로 읽습니다. 같은 파일에 `[profile more-naive-state]`와 Terraform용 `[more-naive-state]`를 기록합니다. Terraform 1.17.2의 단수 필드 deprecation 경고는 알려진 호환성 사항입니다. [고정 Terragrunt 소스](https://github.com/gruntwork-io/terragrunt/blob/v1.2.2/internal/awshelper/config.go)와 [Terraform S3 backend 문서](https://developer.hashicorp.com/terraform/language/backend/s3)의 인증 입력 계약에 맞춘 구성입니다.

## 버킷 bootstrap과 최소 권한

실제 prod unit은 #8에서 추가합니다. unit의 `terragrunt.hcl`에는 다음 include를 둡니다.

```hcl
include "state" {
  path = find_in_parent_folders("state.hcl")
}
```

운영자가 해당 unit에서 공통 loader를 통해 native Terragrunt를 실행합니다. unit 디렉터리명(network/compute 등)을 state key로 사용합니다. 아래 `$REPO_ROOT`는 이 저장소의 절대 경로이며 값에 비밀을 넣지 않습니다.

```bash
MORE_NAIVE_ENV=prod direnv exec "$REPO_ROOT/config/env" env RUSTFS_CREDENTIALS_FILE=/absolute/admin.credentials terragrunt backend bootstrap
MORE_NAIVE_ENV=prod direnv exec "$REPO_ROOT/config/env" jq -n -f "$REPO_ROOT/infra/terragrunt/bootstrap/rustfs/state-policy.jq" > state-policy.json
```

첫 명령은 Terragrunt `backend bootstrap`으로 버킷이 없을 때 생성하며 기존 버킷은 재생성하지 않습니다. 관리자 인증으로 RustFS의 고정 이미지에 들어 있는 `rc 0.1.37`의 `admin user add`, `admin policy create`, `admin policy attach --user`를 사용해 별도 state 사용자와 위 정책을 연결합니다. 기존 사용자/정책이 있으면 먼저 확인하고 다른 프로젝트의 정책을 덮어쓰지 않습니다. 인증 응답은 비밀을 담을 수 있으므로 공유 로그로 출력하지 않습니다. [RustFS IAM 문서](https://docs.rustfs.com/en/security-compliance/iam)의 사용자·정책 연결 방식을 사용합니다.

정책은 prod prefix의 목록과 state 읽기/쓰기, `.tflock` 읽기/쓰기/삭제만 허용합니다. state 객체 삭제 권한은 주지 않습니다. 다른 prefix·버킷은 기본 거부입니다. policy JSON에는 비밀이 없지만 실제 인증 파일은 Git/이미지/PR에 넣지 않습니다.

## init·실행과 기존 state

```bash
MORE_NAIVE_ENV=prod direnv exec "$REPO_ROOT/config/env" terragrunt run -- init -input=false
MORE_NAIVE_ENV=prod direnv exec "$REPO_ROOT/config/env" terragrunt run -- plan -input=false
```

새 state면 migration 없이 init합니다. 기존 local/remote state가 발견되면 작업을 멈추고 기존 backend·lineage·unit key를 운영자가 확인한 뒤 migration 여부를 결정합니다. native init에서 migration/reconfigure 옵션을 임의로 추가하지 않습니다. plan은 검토 결과이며 실제 prod apply는 #8의 대상/계정/선행 검증 뒤 별도 승인으로 수행합니다.

## 저장·전송 보호와 검증

버킷 versioning은 백업/이력 범위 제외 결정에 따라 생성하지 않습니다. 고정 RustFS 1.0.5의 키 관리 미구성 로컬 시험에서 SSE-S3 AES256 요청은 `InvalidRequest`를 반환했습니다. 따라서 버킷 SSE를 자동 설정하지 않으며 host data 0700·제한된 관리자·보호된 저장 디스크를 사용합니다. loopback HTTP에서만 TLS 강제 버킷 정책을 생략하고 외부 HTTP는 state 사전 검증이 거부합니다. 나머지 bucket 접근 보호는 Terragrunt 기본 bootstrap을 유지합니다. 보호 설정을 일괄 해제한 예제를 복사하지 않습니다.

```bash
terragrunt hcl fmt --check --working-dir infra/terragrunt
MORE_NAIVE_ENV=prod direnv exec "$REPO_ROOT/config/env" terragrunt run -- state list
```

`state list`는 앞 절에서 init한 실제 prod unit 디렉터리에서 실행하고 기존 resource 주소와 대조합니다. state 본문이나 인증 정보를 공유 로그로 출력하지 않습니다. 같은 backend와 unit key로 init·plan·state 조회를 수행한 실제 명령·종료 코드·결과를 PR에 기록합니다. native 잠금 충돌·저장소 장애·컨테이너 재생성 후 동일 state 재조회는 #40의 수동 절차와 실제 수행 기록으로 확인하며, 별도 검증 실행기를 두지 않습니다.

머지 후 인프라 관리자가 #2 관리 호스트의 저장 보호·사설 TLS 경계와 버킷 관리자/state 전용 인증을 준비하고 정책을 연결한 뒤 init/격리 검증 결과를 확인합니다. state/lock key를 임의 삭제하거나 bootstrap local state를 원격 이전하지 않습니다. 백업 설정과 복원 리허설은 추가하지 않습니다.
