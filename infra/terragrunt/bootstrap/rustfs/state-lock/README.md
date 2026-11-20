# RustFS state 수동 확인 (#40)

Terraform 1.17.2, Terragrunt 1.2.2, RustFS 1.0.5의 native S3 `use_lockfile`을 확인합니다. Python·uv·boto3·별도 검증 실행기를 추가하지 않습니다. 이전 #58은 닫고 이 수동 절차와 실제 결과로 대체합니다.

## 격리 준비

운영 state·RustFS를 중지하지 않습니다. 별도 컨테이너 `more-naive-state40-20261120`, loopback `127.0.0.1:19090`, 버킷 `state40-native-20261120`, key `manual/terraform.tfstate`를 사용했습니다. 데이터 디렉터리는 UID 10001이며 checkout 밖에 둡니다. `CHECK` 디렉터리는 0700, credential/env/plan은 0600으로 준비합니다. 자격 증명 값은 출력하거나 Git에 넣지 않습니다.

`$CHECK/rustfs.env`에는 고유한 `RUSTFS_ACCESS_KEY`·`RUSTFS_SECRET_KEY`, `RUSTFS_ADDRESS=127.0.0.1:19090`, `RUSTFS_CONSOLE_ENABLE=false`를 둡니다. `$CHECK/credentials`에는 같은 격리 인증의 `[more-naive-state]`·`[profile more-naive-state]`를 준비합니다. 운영 인증을 복사하지 않습니다. `$CHECK/data`를 유지한 채 컨테이너를 생성하고, image에 포함된 native `rc`로 버킷을 준비합니다.

```bash
umask 077
CHECK="$HOME/.local/state/more-naive/qa/20261120/state40"
IMAGE=rustfs/rustfs:1.0.5@sha256:b81d16a90ee25bd9511280127ca1471788c6e874cf0f0da759645f46b2dc1d74
docker run --detach --name more-naive-state40-20261120 --network host \
  --env-file "$CHECK/rustfs.env" --volume "$CHECK/data:/data" "$IMAGE" /data
curl --fail http://127.0.0.1:19090/health
docker exec more-naive-state40-20261120 sh -ec \
  'rc alias set state40 http://127.0.0.1:19090 "$RUSTFS_ACCESS_KEY" "$RUSTFS_SECRET_KEY" >/dev/null 2>&1; rc mb state40/state40-native-20261120'
```

Linux host network는 격리 시험의 Docker 포트 전달 경로를 피하기 위해 사용했습니다. RustFS 자체는 loopback에만 bind합니다. 운영 Docker 배치나 공개 포트 설정을 변경하는 명령이 아닙니다.

`$CHECK/module/main.tf`에는 `terraform_data.proof` 하나만 둡니다. 실제 인프라는 만들지 않습니다.

```hcl
terraform { required_version = "= 1.17.2" }
resource "terraform_data" "proof" { input = "state40-native-20261120" }
```

터미널 두 개가 같은 local cache를 쓰지 않도록 `$CHECK/a`·`$CHECK/b`에 각각 다음 `terragrunt.hcl`을 둡니다. `/absolute/private/state40`은 위 `CHECK`의 절대 경로로 바꿉니다. 두 unit의 **bucket/key/profile은 동일**해야 합니다.

```hcl
terraform { source = "/absolute/private/state40/module" }
remote_state {
  backend = "s3"
  generate = { path = "backend.tf", if_exists = "overwrite_terragrunt" }
  config = {
    bucket = "state40-native-20261120"
    key = "manual/terraform.tfstate"
    region = "us-east-1"
    endpoints = { s3 = "http://127.0.0.1:19090" }
    profile = "more-naive-state"
    shared_credentials_file = "/absolute/private/state40/credentials"
    use_path_style = true
    use_lockfile = true
    skip_credentials_validation = true
    skip_region_validation = true
    skip_metadata_api_check = true
    skip_requesting_account_id = true
    disable_bucket_update = true
    skip_bucket_versioning = true
    skip_bucket_ssencryption = true
    skip_bucket_enforced_tls = true
  }
}
```

두 unit을 init한 뒤 plan을 검토하고 저장 plan을 한 번 apply합니다. 생성되는 것은 격리 proof state뿐입니다.

```bash
terragrunt --working-dir "$CHECK/a" run -- init -input=false
terragrunt --working-dir "$CHECK/b" run -- init -input=false
terragrunt --working-dir "$CHECK/a" run -- plan -input=false -out="$CHECK/proof.tfplan"
terragrunt --working-dir "$CHECK/a" run -- apply -input=false "$CHECK/proof.tfplan"
```

## 터미널 두 개의 잠금 경합

각 터미널에서 같은 `CHECK`를 지정하고 다음 두 명령을 동시에 실행합니다. 두 번째 명령은 **첫 번째가 잠금을 가진 동안** 실행해야 합니다. 먼저 끝난 뒤 실행하면 두 명령 모두 성공할 수 있으며 경합을 확인한 것이 아닙니다.

```bash
# 터미널 1
terragrunt --working-dir "$CHECK/a" run -- plan -input=false -lock-timeout=0s
# 터미널 2
terragrunt --working-dir "$CHECK/b" run -- plan -input=false -lock-timeout=0s
# 첫 명령 종료 후 다시 실행: 정상 해제 확인
terragrunt --working-dir "$CHECK/b" run -- plan -input=false -lock-timeout=0s
```

두 번째에서 `Error acquiring the state lock`·HTTP 412와 첫 실행의 Lock Info를 확인합니다. 정상 실행 중인 잠금은 삭제하지 않습니다. 남은 잠금의 소유 실행이 실제 종료됐는지 확인한 뒤에만 별도 수동 해제를 검토합니다.

## 중지와 컨테이너 재생성

`state pull` 전체를 공유하지 않고 lineage/serial/resource type만 기록합니다. 쉘은 `set -o pipefail`을 사용해 앞선 명령의 실패를 놓치지 않습니다.

```bash
set -o pipefail
terragrunt --working-dir "$CHECK/a" run -- state pull | jq '{lineage,serial,resources:[.resources[].type]}'
docker stop more-naive-state40-20261120
terragrunt --working-dir "$CHECK/a" run -- plan -input=false -lock-timeout=0s
find "$CHECK/a" "$CHECK/b" -type f -name '*.tfstate*' ! -path '*/.terraform/*' -print
docker rm more-naive-state40-20261120
# 위 docker run 명령을 동일 env-file·data mount로 다시 실행하고 health를 확인합니다.
terragrunt --working-dir "$CHECK/b" run -- state pull | jq '{lineage,serial,resources:[.resources[].type]}'
terragrunt --working-dir "$CHECK/a" run -- plan -input=false -lock-timeout=0s
```

중지 중 plan은 실패해야 하며 `errored.tfstate`를 포함한 local application state가 생기면 안 됩니다. `.terraform/terraform.tfstate`는 기존 S3 backend **설정 메타데이터**라 검사에서 제외합니다. 재생성 후 lineage·serial이 같고 plan이 `No changes`인지 확인합니다. 마지막에는 자신이 만든 fixture 컨테이너만 제거하며 data 디렉터리를 지우지 않습니다.

## 2026-11-20 실제 수행 결과

| 확인 | 실제 결과 |
| --- | --- |
| 두 native plan 경합 | 터미널 1 exit 0, 터미널 2 exit 1·`Error acquiring the state lock`·HTTP 412 |
| 정상 해제 후 재실행 | exit 0, No changes |
| 격리 RustFS 중지 중 plan | exit 1, S3 ListObjectsV2 connection refused |
| local application state/errored.tfstate | 생성되지 않음, 검사 exit 0 |
| 같은 data/env로 컨테이너 재생성 | 새 container ID, health 정상 |
| 재조회 lineage | 전후 동일 `075b54a5-dc74-ef8d-6879-29cbdba4329d` |
| 재조회 serial/resource | 전후 동일 serial 1·terraform_data 1개, 비교 exit 0 |
| 재생성 후 plan | exit 0, No changes |
| 정리 | fixture 컨테이너 제거, 증거·격리 data는 private 경로에 보존 |

이 표는 운영 state에 대한 장애 실험이나 Python 테스트 결과가 아닙니다. 운영 RustFS·고정 local bootstrap state·k3s·DB/PVC는 변경하지 않았으며, 자신의 state migration·백업·복원은 수행하지 않았습니다. 명령별 실제 stdout/stderr·종료 코드는 이 문서 PR의 코멘트에 기록합니다.
