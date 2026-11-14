# RustFS bootstrap

관리 Docker 호스트에서 Terraform 1.17.2와 Terragrunt 1.2.2로 RustFS 1.0.5를 구동합니다. Docker provider는 4.7.0이며 이미지는 multi-platform digest로 고정합니다. 관리 대상 k3s 안에는 설치하지 않습니다.

[공식 Docker 문서](https://docs.rustfs.com/en/installation/container/docker)의 영속 마운트와 UID 10001, `/health` 경로를 사용합니다. 호스트 API/Console 포트는 loopback에만 게시합니다. 다른 호스트의 클라이언트는 운영자가 준비한 사설 TLS 터널을 사용해야 합니다. Console 공개와 공인 포트는 만들지 않습니다.

## 입력과 실행

Docker 소켓 접근 권한, 고정 버전의 `terraform`/`terragrunt`, Python 3가 필요합니다. Docker 소켓 권한은 호스트 관리자 권한과 동등하게 취급합니다. 루트 `.env`의 아래 값을 준비합니다. #41의 공통 loader를 사용하며 `.env`를 shell로 실행하지 않습니다.

| 키 | 계약 |
| --- | --- |
| `RUSTFS_DATA_DIR` | checkout·cache 밖의 고정 절대 디렉터리, UID 10001 소유, 0700 권장 |
| `RUSTFS_STATE_PATH` | checkout·cache 밖의 고정 절대 local state 파일, 상위 디렉터리 0700 |
| `RUSTFS_ENDPOINT` | 같은 Docker 호스트의 `http://127.0.0.1:9000`; 다음 포트는 Console |
| `RUSTFS_NAME` | 컨테이너 이름, 생략하면 `more-naive-rustfs` |
| `RUSTFS_ADMIN_ACCESS_KEY`, `RUSTFS_ADMIN_SECRET_KEY` | 고유 관리자 인증, loader가 `TF_VAR_admin_*`로 전달 |

운영자가 data/state 디렉터리를 준비합니다. 실제 경로는 #2에서 확정합니다. state는 Docker 컨테이너 환경에 담긴 비밀값을 포함하므로 저장 디스크 보호·호스트 접근 제한·0700/0600 권한이 필요합니다. state, plan, `.terraform`, `.terragrunt-cache`, 실제 `.env`를 Git이나 PR 로그에 첨부하지 않습니다.

저장소 루트에서 실행합니다. loader가 다른 작업 디렉터리에서도 같은 루트 `.env`를 읽습니다.

```bash
python3 scripts/env.py rustfs-bootstrap -- python3 infra/terragrunt/bootstrap/rustfs/run.py --env prod init -input=false
python3 scripts/env.py rustfs-bootstrap -- python3 infra/terragrunt/bootstrap/rustfs/run.py --env prod plan -input=false
python3 scripts/env.py rustfs-bootstrap -- python3 infra/terragrunt/bootstrap/rustfs/run.py --env prod apply -input=false
curl --fail http://127.0.0.1:9000/health
```

plan을 검토한 운영자가 apply의 대화형 승인을 합니다. bootstrap에는 `state.hcl`을 포함하지 않으며 local backend 경로는 캐시나 실행 디렉터리에 따라 바뀌지 않습니다. RustFS가 아직 없어도 init/plan은 local backend로 실행됩니다. 자신의 state를 RustFS로 migration하지 않습니다.

## 확인과 재실행

```bash
terraform -chdir=infra/terraform/modules/rustfs fmt -check
terraform -chdir=infra/terraform/modules/rustfs init -backend=false -input=false
terraform -chdir=infra/terraform/modules/rustfs validate
terragrunt hcl fmt --check --working-dir infra/terragrunt/bootstrap/rustfs
uv run --with boto3==1.42.65 python infra/terragrunt/bootstrap/rustfs/verify_bootstrap.py
```

검증 스크립트는 이름·포트·data/state 경로와 임시 인증을 새로 만들어 자신의 컨테이너만 변경합니다. 2026-11-14 로컬 Docker 29.9.3에서 S3 객체 재시작 보존·컨테이너 재생성 보존·별도 cache의 동일 local state·dev 거부 4건을 확인했습니다. 실제 prod 검증은 별도입니다. 버킷 최소 권한과 native state lock 검증은 #4/#40이 추가합니다.

health 실패 시 data 디렉터리 UID/권한, loopback 포트 충돌, Docker 상태를 확인합니다. 인증을 출력하는 `docker inspect` 전체 출력이나 `terraform show`를 공유하지 않습니다. 같은 입력으로 apply하면 현재 컨테이너를 확인하며, 이미지나 환경 변경 시 컨테이너를 교체할 수 있습니다. bind mount 데이터는 교체 후 유지됩니다.

## 중지와 삭제

일반 prod network/compute 실행에는 이 bootstrap을 포함하지 않습니다. RustFS 중지는 remote backend를 사용하는 작업의 중단을 뜻하므로 작업이 없는지 먼저 확인합니다. bootstrap 삭제는 `--allow-destroy`를 명시해야 하며 컨테이너만 제거하고 host data 디렉터리는 제거하지 않습니다. 데이터의 영구 삭제는 관리자가 영향과 사용 중인 state를 별도로 확인한 후 수동 수행합니다. 백업 설정·복원 리허설은 이번 범위에 포함하지 않습니다.

머지 후 인프라 관리자가 #2의 관리 호스트에서 경로·인증·Docker 권한을 준비하고 위 init/plan/apply/health를 확인합니다. 로컬 격리 시험은 실제 운영 호스트의 완료 증거를 대신하지 않습니다.
