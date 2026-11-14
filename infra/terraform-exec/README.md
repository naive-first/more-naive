# Terraform 실행기

Go 1.27.4와 [hashicorp/terraform-exec v0.26.0](https://github.com/hashicorp/terraform-exec/tree/v0.26.0)을 사용합니다. Terraform CLI는 1.17.2, Terragrunt는 1.2.2로 고정합니다. Terraform init/validate/plan/apply/destroy/output은 Go SDK가 실제 Terraform 바이너리를 호출합니다. Python Terraform 실행 wrapper는 사용하지 않습니다.

Terragrunt는 `exec --in-download-dir --no-auto-init`으로 기존 HCL의 source·backend 생성·inputs만 준비합니다. [공식 exec 계약](https://docs.terragrunt.com/reference/cli/commands/exec/)을 사용해 HCL을 Go 코드로 재구현하지 않습니다. 새 캐시에 backend 연결 메타데이터가 없으면 SDK Init을 먼저 실행합니다. 기존 backend 변경을 자동 재구성하거나 migration하지 않습니다. 버킷 생성은 Terraform CLI 명령이 아니므로 Go 실행기에서 Terragrunt `backend bootstrap`을 호출합니다.

저장소 루트에서 빌드합니다. binary는 Git·이미지에 포함하지 않습니다.

```sh
cd infra/terraform-exec
go build -o bin/infraexec .
go vet ./...
go test -v ./...
```

`env.prod`는 루트 `env.example`과 동일한 키를 사용하는 literal KEY=value 파일입니다. Go 실행기가 목적별 키만 선택하며 process 값이 우선합니다. 누락·빈 값·중복 키·잘못된 따옴표는 중단하고 다른 환경 파일이나 `.env`로 대체하지 않습니다. `--env prod`와 `--target bootstrap|state`를 명시합니다. `--repo-root`를 생략하면 현재 디렉터리의 상위에서 저장소를 찾습니다. 저장소 밖 unit에서는 절대 경로를 전달합니다.

```sh
# 저장소 루트: RustFS 자체는 별도 local state를 유지합니다.
infra/terraform-exec/bin/infraexec --env prod --target bootstrap init
infra/terraform-exec/bin/infraexec --env prod --target bootstrap plan -out=/absolute/private/bootstrap.tfplan
# plan을 검토한 뒤 저장된 plan만 적용합니다.
infra/terraform-exec/bin/infraexec --env prod --target bootstrap apply /absolute/private/bootstrap.tfplan
```

SDK Apply/Destroy는 대화형 확인을 제공하지 않습니다. 따라서 apply는 저장 plan 또는 명시적 `-auto-approve`가 필요합니다. destroy는 bootstrap에서 `--allow-destroy`와 `-auto-approve`를 함께 요구하며 host data는 유지합니다. 자동 승인 옵션은 격리 시험이나 검토된 운영 절차에서만 사용합니다. migrate-state·force-copy·lock=false 같은 임의 CLI 옵션은 전달하지 않습니다.

```sh
# prod unit 디렉터리에서 실행합니다.
"$REPO_ROOT/infra/terraform-exec/bin/infraexec" --repo-root "$REPO_ROOT" --env prod --target state --unit network bootstrap
"$REPO_ROOT/infra/terraform-exec/bin/infraexec" --repo-root "$REPO_ROOT" --env prod --target state --unit network init
"$REPO_ROOT/infra/terraform-exec/bin/infraexec" --repo-root "$REPO_ROOT" --env prod --target state --unit network plan
```

bootstrap은 관리자 인증만, state 실행은 state 전용 인증만 받습니다. `state bootstrap`만 관리자를 사용하며 해당 action은 설정한 버킷의 비대화형 생성을 명시적으로 요청합니다. 환경의 AWS 기본 인증·GH_TOKEN·실행 주입 변수는 전달하지 않습니다. provider의 자격 증명은 별도 HCL/공급자 계약에서 준비합니다.

공개 진입점이 목적별 환경을 제한한 뒤 Terragrunt inputs와 관리자 변수를 SDK의 기본 환경 상속으로 전달합니다. TF_VAR의 literal 문자열과 구조화 값 의미를 유지하며 비밀값을 argv나 임시 변수 파일에 넣지 않습니다. 임의 TF_CLI_ARGS·logging·workspace 주입 변수는 SDK 실행 전에 제거합니다. local state와 credential profile은 캐시 밖에 유지하며 profile은 원자적으로 갱신합니다. 로그에는 state/plan·인증 파일 내용을 출력하지 않습니다. `output`도 sensitive 값은 숨깁니다.

실제 검증은 [bootstrap](../terragrunt/bootstrap/rustfs/README.md)과 [state](../terragrunt/state-README.md)의 격리 Docker 시험을 사용합니다. Go 테스트에는 실제 Terraform의 init→plan→저장 plan apply→변경 없음과 민감 output 비공개를 확인하는 시험이 있습니다. Terraform이 없는 환경에서는 해당 runtime 시험이 skip되므로 운영 검증으로 간주하지 않습니다.
