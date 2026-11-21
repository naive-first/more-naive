# RustFS bootstrap

관리 Docker 호스트에서 Terraform 1.17.2와 Terragrunt 1.2.2로 RustFS 1.0.5를 구동합니다. Docker provider는 4.7.0이며 이미지는 multi-platform digest로 고정합니다. 관리 대상 k3s 안에는 설치하지 않습니다.

[공식 Docker 문서](https://docs.rustfs.com/en/installation/container/docker)의 영속 마운트와 UID 10001, `/health` 경로를 사용합니다. 호스트 API/Console 포트는 loopback에만 게시합니다. 다른 호스트의 클라이언트는 운영자가 준비한 사설 TLS 터널을 사용해야 합니다. Console 공개와 공인 포트는 만들지 않습니다.

## 입력과 실행

Docker 소켓 접근 권한, 고정 버전의 `terraform`/`terragrunt`가 필요합니다. Docker 소켓 권한은 호스트 관리자 권한과 동등하게 취급합니다. 루트 `env.example`을 참고해 `env.prod`에 아래 값을 준비합니다. `MORE_NAIVE_ENV=prod direnv exec config/env`로 선택하며 환경 파일을 shell로 실행하지 않습니다.

| 키 | 계약 |
| --- | --- |
| `RUSTFS_DATA_DIR` | checkout·cache 밖의 고정 절대 디렉터리, UID 10001 소유, 0700 권장 |
| `RUSTFS_STATE_PATH` | checkout·cache 밖의 고정 절대 local state 파일, 상위 디렉터리 0700 |
| `RUSTFS_ENDPOINT` | 같은 Docker 호스트의 `http://127.0.0.1:9000`; 다음 포트는 Console |
| `RUSTFS_NAME` | 컨테이너 이름, 생략하면 `more-naive-rustfs` |
| `RUSTFS_ADMIN_ACCESS_KEY`, `RUSTFS_ADMIN_SECRET_KEY` | 고유 관리자 인증, native Terragrunt가 TF_VAR 환경변수로 전달 |

운영자가 data/state 디렉터리를 준비합니다. 실제 관리 호스트와 경로는 #2의 계약에 따라 적용 전에 확정합니다. state는 Docker 컨테이너 환경에 담긴 비밀값을 포함하므로 저장 디스크 보호·호스트 접근 제한·0700/0600 권한이 필요합니다. state, plan, `.terraform`, `.terragrunt-cache`, 실제 `env.prod`를 Git이나 PR 로그에 첨부하지 않습니다.

저장소 루트에서 실행합니다. direnv는 루트 `env.prod`를 표준 dotenv로 읽습니다. `direnv allow config/env`를 먼저 검토·허용합니다. native before_hook는 Terraform 실행 전에 경로·UID·권한을 검증합니다.

```bash
umask 077
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/bootstrap/rustfs run -- init -input=false
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/bootstrap/rustfs run -- plan -input=false -out=/absolute/private/bootstrap.tfplan
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/bootstrap/rustfs run -- apply -input=false /absolute/private/bootstrap.tfplan
curl --fail http://127.0.0.1:9000/health
```

plan을 검토한 운영자가 저장된 plan을 apply에 전달합니다. Terraform native 승인 동작을 사용하며, 위 절차에서는 검토한 저장 plan만 적용합니다. bootstrap에는 `state.hcl`을 포함하지 않으며 local backend 경로는 캐시나 실행 디렉터리에 따라 바뀌지 않습니다. RustFS가 아직 없어도 init/plan은 local backend로 실행됩니다. 자신의 state를 RustFS로 migration하지 않습니다.

## 확인과 재실행

```bash
terraform -chdir=infra/terraform/modules/rustfs fmt -check
terraform -chdir=infra/terraform/modules/rustfs init -backend=false -input=false
terraform -chdir=infra/terraform/modules/rustfs validate
terragrunt hcl fmt --check --working-dir infra/terragrunt/bootstrap/rustfs
curl --fail --silent --show-error http://127.0.0.1:9000/health
```

위 명령은 Terraform 모듈·Terragrunt 구성과 실제 관리 호스트의 health를 확인합니다. 재실행할 때는 같은 `env.prod`와 고정 local state 경로를 사용해 앞 절의 init·plan을 실행하고, 변경 계획과 data 디렉터리 UID·권한을 확인합니다. 명령 예시만으로 실제 prod 적용이나 영속성 확인을 완료했다고 기록하지 않습니다. 버킷 최소 권한은 #4, 잠금·저장소 장애·컨테이너 재생성 후 동일 state 재조회는 #40의 수동 절차와 실제 수행 기록으로 확인합니다.

health 실패 시 data 디렉터리 UID/권한, loopback 포트 충돌, Docker 상태를 확인합니다. 인증을 출력하는 `docker inspect` 전체 출력이나 `terraform show`를 공유하지 않습니다. 같은 입력으로 apply하면 현재 컨테이너를 확인하며, 이미지나 환경 변경 시 컨테이너를 교체할 수 있습니다. bind mount 데이터는 교체 후 유지됩니다.

## 중지와 삭제

일반 prod network/compute 실행에는 이 bootstrap을 포함하지 않습니다. RustFS 중지는 remote backend를 사용하는 작업의 중단을 뜻하므로 작업이 없는지 먼저 확인합니다. bootstrap 삭제는 `RUSTFS_ALLOW_DESTROY=true`를 명시하고 Terraform 삭제 plan을 확인해야 하며 컨테이너만 제거하고 host data 디렉터리는 제거하지 않습니다. 데이터의 영구 삭제는 관리자가 영향과 사용 중인 state를 별도로 확인한 후 수동 수행합니다. 백업 설정·복원 리허설은 이번 범위에 포함하지 않습니다.

머지 후 인프라 관리자가 #2의 관리 호스트에서 경로·인증·Docker 권한을 준비하고 위 init/plan/apply/health를 확인합니다. 로컬 격리 시험은 실제 운영 호스트의 완료 증거를 대신하지 않습니다.
