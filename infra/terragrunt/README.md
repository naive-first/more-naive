# prod 인프라 실행

Terragrunt 1.2.2가 Terraform CLI 1.17.2를 실행합니다. `root.hcl`은 실행 바이너리와 버전을 고정하고, 실제 unit이 이를 명시적으로 상속합니다. [prod 경로](live/prod/README.md)만 실제 실행 대상으로 사용합니다.

`live/dev`는 README 또는 실행되지 않는 `.example`만 허용합니다. local PostgreSQL/앱 테스트는 dev 배포와 다릅니다. `live` 전체를 대상으로 재귀 apply를 실행하지 않습니다. 환경 생략·dev 선택은 후속 실행 도구에서 쓰기 전에 거부해야 합니다. 이 골격 자체는 자원을 생성하거나 backend를 초기화하지 않습니다.

버전 확인은 `terraform version`과 `terragrunt --version`, 형식 확인은 `terragrunt hcl fmt --check`로 합니다. 실제 unit이 생긴 후 루트 `.env` 도구로 필요한 값만 전달하고 prod unit에서 plan을 확인합니다. 필수값 누락과 계정 불일치는 local 값으로 대체하지 않습니다.

RustFS health·버킷/최소 권한·native 잠금/장애 중단을 확인한 뒤 #8에서 prod unit을 연결합니다. backend 인증과 provider 인증을 구분하며 state·plan을 Git에 넣지 않습니다. 초기화 실패 시 endpoint와 인증·버전부터 확인하고 기존 state 경로/lineage를 점검합니다. bootstrap local state를 RustFS로 이전하지 않습니다.

권한은 해당 공급자 API·RustFS state용 권한으로 분리합니다. 재실행은 같은 unit/backend에서 수행합니다. 삭제는 plan의 대상 자원을 먼저 검토하며 RustFS bootstrap/데이터는 일반 prod destroy에 포함하지 않습니다. 백업/복원 설정은 범위 밖입니다.
