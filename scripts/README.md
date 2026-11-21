# 환경 입력과 운영 도구

`env.dev`와 `env.prod`는 같은 키를 사용합니다. 템플릿 `env.example`을 필요한 파일로 복사하고 권한을 600으로 제한합니다. 환경 선택과 파일 로딩은 direnv의 표준 dotenv 기능을 사용합니다. 프로젝트 전용 Python parser/consumer 실행기는 없습니다.

저장소 루트에서 한 번 `direnv allow config/env`로 이 저장소의 작은 환경 구성을 검토·허용합니다. root나 상위 GitHub 인증 설정을 변경할 필요는 없습니다. 이후 각 명령에서 환경을 명시합니다.

```bash
MORE_NAIVE_ENV=dev direnv exec config/env docker compose --env-file /dev/null -f backend/compose.yaml config --quiet
MORE_NAIVE_ENV=dev direnv exec config/env backend/gradlew -p backend bootRun
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/bootstrap/rustfs run -- plan -input=false
```

파일 누락·선택 누락·dev/prod 이외의 값·잘못된 dotenv 문법은 명령 실행 전에 중단합니다. 파일은 shell source하지 않습니다. 표준 dotenv 규칙에 따라 literal 비밀번호와 `$`·공백·`#` 등이 있는 값은 single quote로 감쌉니다. double quote/unquoted 값의 변수 확장은 direnv 규칙을 따르며 같은 키가 반복되면 뒤의 값을 사용합니다. `MORE_NAIVE_ENV`는 명령에서만 선택하고 파일에 넣지 않습니다.

표준 도구가 선택 파일의 환경을 전달합니다. 실제 앱 컨테이너·Kubernetes 리소스·Terraform 변수는 각 native 설정에서 필요한 키를 명시합니다. 필수값·prod 대상·hostname/API 주소·SSH trust는 해당 도구의 사전 검증과 HCL validation으로 확인합니다. `env`, credential 파일, Secret payload, plan/state 전체를 공유 로그에 출력하지 않습니다.

Argo CD 관리자 비밀번호는 선택 키 `ARGOCD_ADMIN_PASSWORD_HASH`로 전달합니다. 두 env 파일의 키 이름은 같고 bcrypt 해시를 single quote로 감쌉니다. 실제 prod 반영·비밀번호 변경과 private state 취급은 [Argo CD 운영 문서](../infra/argocd/README.md#env에서-admin-비밀번호-설정)를 따릅니다.

## RustFS 인증과 state

bootstrap은 `RUSTFS_ADMIN_ACCESS_KEY`/`RUSTFS_ADMIN_SECRET_KEY`를 native Terraform 환경변수로 전달합니다. Terraform의 Docker 자원 state에는 관리 인증이 들어가므로 기존 고정 local state와 상위 0700·파일 0600을 유지합니다. 자신의 state를 RustFS로 이전하지 않습니다.

state 작업에는 외부에 준비한 `RUSTFS_CREDENTIALS_FILE`을 사용합니다. 파일은 현재 사용자 소유 0600이며 checkout 밖의 절대 경로여야 합니다. 같은 파일에 Terraform용 `[more-naive-state]`와 Terragrunt 1.2.2용 `[profile more-naive-state]`를 준비합니다. 기존에 만든 profile 파일도 그대로 사용할 수 있습니다. 이 도구는 인증 파일을 생성·변경하지 않습니다. bucket bootstrap 관리자 profile과 일상 state profile은 별도 파일로 보관합니다.

`RUSTFS_ENDPOINT`/`RUSTFS_BUCKET`/`RUSTFS_REGION`을 명시하며 HTTPS 또는 loopback HTTP만 허용합니다. backend key는 실제 unit 디렉터리명으로 `more-naive/prod/<unit>/terraform.tfstate`를 사용합니다. credential 경로·state 경로가 달라진 경우 자동 migration/reconfigure하지 않고 기존 backend와 lineage를 먼저 확인합니다.

```bash
umask 077
MORE_NAIVE_ENV=prod direnv exec "$REPO_ROOT/config/env" terragrunt run -- init -input=false
MORE_NAIVE_ENV=prod direnv exec "$REPO_ROOT/config/env" terragrunt run -- plan -input=false
```

위 명령은 검토한 prod unit 디렉터리에서 실행합니다. 사전 검증·Secret 주입·등록·smoke는 각 정본 문서의 native CLI를 따릅니다. 이 저장소에는 QA를 포함해 Python 스크립트와 uv·boto3 실행 의존성을 추가하지 않습니다. 필요한 확인은 Terraform/Terragrunt·kubectl/Helm 명령과 README의 수동 절차로 수행하고, 실제 수행 결과만 해당 PR 코멘트에 남깁니다.
