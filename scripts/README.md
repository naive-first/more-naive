# 공통 실행 입력

Python 3.10 이상에서 `env.py`가 자신의 저장소 루트 `.env`를 읽고 지정한 목적의 키만 자식 명령에 전달합니다. 현재 디렉터리에서 `.env`를 검색하지 않으며 Spring과 Terragrunt의 자동 dotenv 로딩에 의존하지 않습니다. 외부 Python 패키지가 필요하지 않습니다.

```sh
cp .env.example .env
chmod 600 .env
```

운영자가 필요한 비밀번호·접속 정보만 로컬 파일에 채웁니다. 예시의 빈 값은 기본 인증으로 대체되지 않습니다. `.env` 전체나 렌더링한 Secret, Terraform state/plan, kubeconfig는 커밋하거나 출력하지 않습니다. 생성 인증 파일은 `*.credentials`, 민감 출력은 `*.secret` 이름으로 관리하며 권한을 `600`으로 제한합니다. RustFS state와 데이터 디렉터리는 관리 호스트에서 소유자만 접근하도록 준비합니다.

## 문법과 우선순위

- UTF-8의 한 줄 `KEY=value`를 지원합니다. 빈 줄과 `#`로 시작하는 줄은 무시합니다.
- key 앞뒤와 unquoted value 끝의 공백은 제거합니다. 작은따옴표·큰따옴표 안의 공백은 보존합니다.
- 따옴표 내부의 동일한 따옴표, escape, 여러 줄, `export`, 중복 key, trailing inline comment는 지원하지 않습니다. unquoted `#`는 값 자체입니다.
- `$NAME`, `${NAME}`, `$(command)`, backtick은 모두 문자 그대로입니다. shell에 source/eval하지 않으며 shell 보간도 수행하지 않습니다.
- 선택한 입력 이름의 프로세스 환경변수가 파일보다 우선합니다. 빈 환경변수도 우선하므로 필수값이면 실행 전에 실패합니다.
- 파일이 없더라도 선택한 모든 필수 입력을 프로세스 환경으로 제공할 수 있습니다. CI는 prod `.env` 없이 테스트 전용 `DB_*`를 직접 주입해 Gradle을 실행해도 됩니다.

형식 오류는 줄 번호, 누락은 키 이름만 출력합니다. 실패하면 자식 명령을 실행하지 않습니다. dev consumer는 없으며 지원하지 않는 목적도 실행 전에 거부합니다. 값의 실재·도달성·역할별 권한과 prod 대상 일치는 각 후속 실행 도구가 검증합니다.

## 실행 목적

```sh
python3 scripts/env.py <consumer> -- <command> [argument ...]
```

| consumer | 필수 입력과 전달 |
| --- | --- |
| `local-app` | `LOCAL_DB_URL/USERNAME/PASSWORD` → `DB_URL/USERNAME/PASSWORD` |
| `local-compose` | `LOCAL_DB_DATABASE/USERNAME/PASSWORD/PORT` 그대로 |
| `prod-config` | `PROD_DB_DATABASE/USERNAME/PASSWORD`, `PROD_KUBE_CONTEXT`, `PROD_KUBE_SERVER`, `PROD_NAMESPACE` 그대로 |
| `argocd` | `PROD_KUBE_CONTEXT/SERVER`, `PROD_NAMESPACE`; private repository의 `ARGO_REPO_USERNAME/TOKEN` 선택 |
| `rustfs-bootstrap` | `RUSTFS_ADMIN_ACCESS_KEY/SECRET_KEY` → `TF_VAR_admin_access_key/admin_secret_key`; `RUSTFS_DATA_DIR/STATE_PATH/ENDPOINT` 그대로; `RUSTFS_NAME` 선택 |
| `rustfs-state` | `RUSTFS_ENDPOINT/BUCKET/REGION/STATE_ACCESS_KEY/STATE_SECRET_KEY` 그대로 |
| `rustfs-admin` | `RUSTFS_ENDPOINT/BUCKET/REGION/ADMIN_ACCESS_KEY/ADMIN_SECRET_KEY` 그대로 |
| `k3s` | `PROD_SSH_HOST/USER/KEY_FILE`, `PROD_KUBE_CONTEXT`, `PROD_NAMESPACE`, `K3S_NODE_NAME/ROLE`; `K3S_SERVER_URL/TOKEN`은 agent일 때 필수 |
| `tailscale-node` | `PROD_SSH_HOST/USER/KEY_FILE`, `TAILSCALE_NODE_NAME`; `TAILSCALE_AUTH_KEY/TAGS` 선택 |
| `tailscale-proxy` | `PROXY_SSH_HOST/USER/KEY_FILE/HTTPS_HOSTNAME`, `ISTIO_UPSTREAM_URL`, `PROD_KUBE_CONTEXT` |

목록은 prefix wildcard가 아닌 정확한 키 allowlist입니다. 예를 들어 `rustfs-state`는 관리자·DB·`AWS_*`를 전달하지 않습니다. 후속 state 실행 도구는 state 인증을 전용 `0600` credential file/profile로 Terraform backend에 전달해야 하며, cloud provider 인증으로 자동 재사용하면 안 됩니다. 아직 선택하지 않은 cloud provider의 임의 인증 키를 전달하는 generic terraform consumer는 만들지 않습니다.

명령 실행을 위한 `PATH`, `HOME`, 사용자·locale·임시 경로, `JAVA_HOME`, Windows 실행 경로만 상속합니다. local 앱/Compose와 RustFS bootstrap은 Docker 접속 변수 4개(`DOCKER_HOST/CONTEXT/TLS_VERIFY/CERT_PATH`), 클러스터 목적은 `KUBECONFIG`도 받습니다. `GH_TOKEN`, `PYTHONPATH`, `LD_PRELOAD`, `BASH_ENV`와 선택되지 않은 입력은 상속하지 않습니다. 실행할 명령은 운영자가 지정한 신뢰할 수 있는 명령이어야 하며 loader는 그 명령의 stdout을 필터링하지 않습니다. `env`, `printenv`, shell tracing, Secret 렌더링 출력으로 값을 노출하지 마세요.

## 후속 구현에서 사용할 호출

아래 backend/infra 대상 파일은 후속 이슈에서 추가합니다. 이 예시는 배포 성공 기록이 아닙니다. 저장소 루트에서 실행합니다.

```sh
python3 scripts/env.py local-app -- backend/gradlew -p backend bootRun
python3 scripts/env.py local-compose -- docker compose -f backend/compose.yaml --env-file .env up -d
python3 scripts/env.py rustfs-bootstrap -- terragrunt --working-dir infra/terragrunt/bootstrap/rustfs plan
```

Compose에는 명시적인 `--env-file .env`를 계속 지정합니다. Spring은 `local-app`의 `DB_*`를 읽습니다. prod 설정 도구는 `prod-config`의 선택된 값만 Secret/ConfigMap에 주입하며 이슈 #16에서 연결합니다. prod 값 누락 시 local 키로 대체하지 않습니다.

## 검증·재실행·삭제

```sh
python3 -m unittest discover -s scripts -p 'test_env.py' -v
python3 -m compileall -q scripts
```

단위 테스트는 임시 루트와 공개 fixture만 사용하여 실행 위치, 문법, shell 비실행, 우선순위, consumer 분리와 실패 전 중단을 검증합니다. 실제 prod 자격 증명·VM·클러스터 검증을 대신하지 않습니다. 도구는 `.env`를 변경하지 않으며 재실행해도 자식 명령의 효과만 반복됩니다. `.env`를 삭제하면 파일 입력이 사라집니다. 인프라나 DB의 삭제·재시작 영향은 호출하는 명령의 README를 확인합니다.
