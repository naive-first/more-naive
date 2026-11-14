# 공통 실행 입력

Python 3.10 이상에서 `env.py`가 저장소 루트의 `env.dev` 또는 `env.prod`를 읽고 지정한 목적의 키만 자식 명령에 전달합니다. 환경은 파일 이름으로 구분하며 두 파일에서 같은 키를 사용합니다. 예를 들어 DB 사용자 이름은 두 파일 모두 `DB_USERNAME`이고 값만 다릅니다.

```sh
cp env.example env.dev
cp env.example env.prod
chmod 600 env.dev env.prod
```

`env.example`은 두 환경의 공통 템플릿입니다. 필요한 환경 파일만 만들어도 됩니다. 각 파일의 `DB_URL`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`와 필요한 접속 정보를 해당 환경에 맞게 채웁니다. 빈 필수값은 실행 전에 거부합니다. 실제 환경 파일은 Git과 Docker 빌드 컨텍스트에서 제외합니다.

```sh
python3 scripts/env.py --env dev app -- backend/gradlew -p backend bootRun
python3 scripts/env.py --env prod app -- backend/gradlew -p backend bootRun
```

`--env`는 필수이며 `dev`와 `prod`만 받습니다. 스크립트 자신의 저장소 루트에서 선택한 파일 하나만 읽으므로 실행 디렉터리에 영향을 받지 않습니다. 선택한 파일이 없어도 다른 환경 파일이나 기존 `.env`로 대체하지 않습니다. `LOCAL_*`, `PROD_*` 입력도 사용하지 않습니다. 외부 Python 패키지는 필요하지 않습니다.

## 문법과 우선순위

- UTF-8의 한 줄 `KEY=value`를 지원합니다. 빈 줄과 `#`로 시작하는 줄은 무시합니다.
- key 앞뒤와 unquoted value 끝의 공백은 제거합니다. 작은따옴표·큰따옴표 안의 공백은 보존합니다.
- 따옴표 내부의 동일한 따옴표, escape, 여러 줄, `export`, 중복 key, trailing inline comment는 지원하지 않습니다. unquoted `#`는 값 자체입니다.
- `$NAME`, `${NAME}`, `$(command)`, backtick은 모두 문자 그대로입니다. shell에 source/eval하지 않으며 shell 보간도 수행하지 않습니다.
- 선택한 입력 이름의 프로세스 환경변수가 파일보다 우선합니다. 빈 환경변수도 우선하므로 필수값이면 실행 전에 실패합니다. 환경을 전환할 때 셸에 남은 `DB_*` 등도 확인합니다.
- 선택한 파일이 없더라도 모든 필수 입력을 프로세스 환경으로 제공하면 실행할 수 있습니다. CI도 테스트 전용 `DB_*`를 직접 주입할 수 있습니다.

형식 오류는 줄 번호, 누락은 키 이름만 출력합니다. 실패하면 자식 명령을 실행하지 않습니다. 값의 실재·도달성·역할별 권한과 prod 대상 일치는 각 후속 실행 도구가 검증합니다.

## 실행 목적

```sh
python3 scripts/env.py --env <dev|prod> <consumer> -- <command> [argument ...]
```

| consumer | 필수 입력과 전달 | 환경 |
| --- | --- | --- |
| `app` | `DB_URL/USERNAME/PASSWORD` 그대로 | dev, prod |
| `compose` | `DB_DATABASE/USERNAME/PASSWORD/PORT` 그대로 | dev, prod |
| `cluster-config` | `DB_DATABASE/USERNAME/PASSWORD`, `KUBE_CONTEXT`, `KUBE_SERVER`, `NAMESPACE` 그대로 | prod |
| `argocd` | `KUBE_CONTEXT/SERVER`, `NAMESPACE`; private repository의 `ARGO_REPO_USERNAME/TOKEN` 선택 | prod |
| `rustfs-bootstrap` | `RUSTFS_ADMIN_ACCESS_KEY/SECRET_KEY` → `TF_VAR_admin_access_key/admin_secret_key`; `RUSTFS_DATA_DIR/STATE_PATH/ENDPOINT` 그대로; `RUSTFS_NAME` 선택 | prod |
| `rustfs-state` | `RUSTFS_ENDPOINT/BUCKET/REGION/STATE_ACCESS_KEY/STATE_SECRET_KEY` 그대로 | prod |
| `rustfs-admin` | `RUSTFS_ENDPOINT/BUCKET/REGION/ADMIN_ACCESS_KEY/ADMIN_SECRET_KEY` 그대로 | prod |
| `k3s-terraform` | `k3s` 입력과 `SSH_HOST_KEY`, server/agent 공통 `K3S_TOKEN`, RustFS state 인증; native prod k3s unit | prod |
| `k3s` | `SSH_HOST/USER/KEY_FILE`, `KUBE_CONTEXT`, `NAMESPACE`, `K3S_NODE_NAME/ROLE`; `K3S_SERVER_URL/TOKEN`은 agent일 때 필수 | prod |
| `tailscale-node` | `SSH_HOST/USER/KEY_FILE`, `TAILSCALE_NODE_NAME`; `TAILSCALE_AUTH_KEY/TAGS` 선택 | prod |
| `tailscale-proxy` | `PROXY_SSH_HOST/USER/KEY_FILE/HTTPS_HOSTNAME`, `ISTIO_UPSTREAM_URL`, `KUBE_CONTEXT` | prod |

환경 선택과 실행 목적은 별개입니다. `dev`는 앱/Compose 입력에 사용할 수 있으며 기존 범위대로 dev 인프라 배포는 지원하지 않습니다. Python에서 직접 호출할 때도 `build_environment("cluster-config", "prod")`처럼 환경을 명시합니다.

목록은 prefix wildcard가 아닌 정확한 키 allowlist입니다. 예를 들어 `rustfs-state`는 관리자·DB·`AWS_*`를 전달하지 않습니다. 후속 state 실행 도구는 state 인증을 전용 `0600` credential file/profile로 Terraform backend에 전달해야 하며, cloud provider 인증으로 자동 재사용하면 안 됩니다. 아직 선택하지 않은 cloud provider의 임의 인증 키를 전달하는 generic terraform consumer는 만들지 않습니다.

명령 실행을 위한 `PATH`, `HOME`, 사용자·locale·임시 경로, `JAVA_HOME`, Windows 실행 경로만 상속합니다. 앱/Compose와 RustFS bootstrap은 Docker 접속 변수 4개(`DOCKER_HOST/CONTEXT/TLS_VERIFY/CERT_PATH`), 클러스터 목적은 `KUBECONFIG`도 받습니다. `GH_TOKEN`, `PYTHONPATH`, `LD_PRELOAD`, `BASH_ENV`와 선택되지 않은 입력은 상속하지 않습니다.

실행할 명령은 운영자가 지정한 신뢰할 수 있는 명령이어야 하며 loader는 그 명령의 stdout을 필터링하지 않습니다. 환경 파일 전체, 렌더링한 Secret, Terraform state/plan, kubeconfig를 커밋하거나 출력하지 않습니다. 생성 인증 파일은 `*.credentials`, 민감 출력은 `*.secret` 이름으로 관리하며 권한을 `600`으로 제한합니다. RustFS state와 데이터 디렉터리는 관리 호스트에서 소유자만 접근하도록 준비합니다.

## 후속 구현에서 사용할 호출

아래 backend/infra 대상 파일은 별도 PR에서 추가합니다. 저장소 루트에서 실행하는 호출 예시이며 배포 성공 기록이 아닙니다.

```sh
python3 scripts/env.py --env dev compose -- docker compose --env-file /dev/null -f backend/compose.yaml up -d
python3 scripts/env.py --env prod rustfs-bootstrap -- terragrunt --working-dir infra/terragrunt/bootstrap/rustfs plan
```

Compose 예시의 `/dev/null`은 Linux/macOS에서 자동 `.env` 로딩을 막고 loader가 선택한 `DB_*`만 보간에 사용하게 합니다. Compose 파일도 동일한 `DB_*`를 참조해야 합니다. Spring은 `app`의 `DB_*`를 읽습니다. prod 설정 도구는 `cluster-config`의 선택된 값만 Secret/ConfigMap에 주입합니다.

기존 호출을 연결하는 PR에서는 `.env` 경로와 `LOCAL_*`/`PROD_*`, `local-app`/`local-compose`/`prod-config`를 새 계약으로 함께 바꿔야 합니다. 특히 #54의 Compose와 #57의 설정 주입 도구는 해당 PR에서 연결을 갱신해야 합니다.

## 검증·재실행·삭제

```sh
python3 -m unittest discover -s scripts -p 'test_env.py' -v
python3 -m compileall -q scripts
```

단위 테스트는 임시 루트와 공개 fixture만 사용하여 환경 파일 선택, 같은 키의 서로 다른 값, 실행 위치, 문법, shell 비실행, 우선순위, consumer 분리와 실패 전 중단을 검증합니다. 실제 prod 자격 증명·VM·클러스터 검증을 대신하지 않습니다. 도구는 환경 파일을 변경하지 않으며 재실행해도 자식 명령의 효과만 반복됩니다. 환경 파일을 삭제하면 해당 파일 입력이 사라집니다. 인프라나 DB의 삭제·재시작 영향은 호출하는 명령의 README를 확인합니다.
