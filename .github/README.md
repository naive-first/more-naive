# Backend CI와 public 이미지 승격

`Backend` workflow는 PR에서 PostgreSQL 17.12 테스트·JAR·컨테이너 빌드를 실행합니다. fork PR은 읽기 권한의 test job만 실행하며 게시·배포 설정 쓰기는 `main` push 또는 `main`의 수동 실행에서 테스트가 통과한 뒤 진행합니다. JDK 21과 고정 Wrapper를 사용하고 실제 `env.prod`를 읽지 않습니다.

test job에서 만든 JAR의 checksum을 artifact와 함께 전달하고 publish job이 재확인합니다. `GITHUB_TOKEN`의 `packages: write`로 `ghcr.io/naive-first/more-naive-backend:sha-<commit>`을 게시하며 OCI source/revision label과 build-push action의 전체 digest를 기록합니다. 게시용 PAT와 클러스터 인증은 사용하지 않습니다. [GHCR 공식 인증·공개 범위 계약](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)을 따릅니다.

## 최초 준비와 재개

| 담당자·시점 | 작업 | 완료 확인 |
| --- | --- | --- |
| 저장소 관리자, workflow 최초 실행 전 | Settings → Actions → General에서 Actions의 PR 생성 허용을 준비 | 실제 GITHUB_TOKEN 설정 PR 생성 성공 |
| package 관리자, 최초 게시 후 | Package settings → Change visibility → Public | 인증 없는 새 Docker config에서 게시한 같은 digest pull 성공 |
| 인프라 담당자, 최초 승격 전 | `infra/environments/prod/backend.yaml`과 `infra/argocd/applications/prod/backend.yaml.example` 준비 | 승인한 repository와 비활성 Application이 기본 브랜치에 존재 |
| 리뷰어, 설정 PR 생성 후 | digest·원본 pull 출력·source commit을 확인하고 정상 PR 절차로 병합 | Argo CD 자동 sync와 실제 prod 확인은 배포 이슈에서 수행 |

2026-11-14 조회에서 `can_approve_pull_request_reviews=false`였습니다. 권한 설정은 자동 변경하지 않았으며 실제 CI 게시·공개 pull·설정 PR 성공으로 기록하지 않습니다. job의 `pull-requests: write` 선언만으로 저장소의 PR 허용 설정을 대체할 수 없습니다. [저장소 Actions 설정](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#preventing-github-actions-from-creating-or-approving-pull-requests)을 확인합니다.

첫 package는 private일 수 있습니다. push 성공 후 익명 pull이 거부되면 job은 실패하고 설정 브랜치·PR을 만들지 않습니다. 관리자가 public으로 바꾼 뒤 Actions → Backend → Run workflow에서 `main`을 선택해 재개합니다. 같은 소스를 다시 테스트·게시하고 그 실행에서 확인된 digest만 승격합니다. 이미 해당 digest와 활성 Application이 main에 있으면 설정 변경을 반복하지 않습니다. 자동 visibility API·push flag·pull Secret은 추가하지 않습니다.

## 승격 경계

승격 도구는 임시 빈 `{"auths":{}}` Docker config로 정확한 `repository@sha256`를 pull하고 `RepoDigests`를 대조합니다. 성공한 원본 명령·출력·종료 코드를 설정 PR 본문에 첨부합니다. 인증 실패·잘못된 digest·준비 파일 누락은 쓰기 전에 중단합니다.

`bash .github/scripts/promote-image.sh`는 기본 git·gh·yq·jq·Docker CLI를 사용합니다. yq 4.54.3은 공식 binary SHA256을 검증해 설치합니다. 최신 main을 임시 git 저장소로 가져와 `image.digest`만 수정합니다. 최초에는 `.yaml.example`을 `.yaml`로 옮기는 변경을 같은 Git tree/커밋에 넣으며, 이미 활성 Application은 다시 만들지 않습니다. 설정 PR은 자동 병합하지 않고 이슈 닫기 키워드도 넣지 않습니다. gh/git 실패 시 PR 설정·GITHUB_TOKEN 권한을 확인하고 재실행하며 다른 브랜치를 강제로 덮지 않습니다. CI는 kubeconfig·kubectl·Argo CD 자격 증명을 사용하지 않습니다.

## 로컬 검사와 미수행 범위

```sh
bash -n config/env/.envrc scripts/check-cluster.sh scripts/check-ssh.sh
bash -n .github/scripts/promote-image.sh
actionlint .github/workflows/backend.yaml
```

Bash 문법과 workflow 문법을 먼저 확인합니다. 신뢰하지 않는 repository/ref 입력으로 `bash .github/scripts/promote-image.sh`를 실행하면 exit 2로 중단하고 Docker·Git 쓰기에 진입하지 않아야 합니다. 실제 승격 검증은 main workflow의 게시·익명 digest pull 명령과 결과로 확인합니다. 실패한 익명 pull에서는 설정 브랜치/PR이 없어야 하며, 동일 digest 재실행에서는 `Already promoted`와 변경 부재를 확인합니다. 최초 활성화 시에는 digest와 Application이 같은 커밋에 있는지 PR diff를 확인합니다. 기존 승격 브랜치의 전체 tree가 기대 결과와 다르면 덮어쓰지 않습니다. actionlint는 workflow 문법 검사이며 실제 GitHub Actions 실행, GHCR public 전환, 익명 pull 성공, prod 배포를 증명하지 않습니다. 현재 Draft PR에서는 후자의 실제 검증이 남아 있습니다.
