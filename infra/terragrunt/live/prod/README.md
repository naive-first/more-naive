# prod 실행 경로

실제 network/compute unit은 이 경로에 추가합니다. 각 unit에서 root.hcl의 Terraform CLI 버전을 상속하고 state.hcl의 RustFS backend를 선택적으로 포함합니다. bootstrap/rustfs는 별도의 고정 절대 local state를 사용하며 prod backend에 포함하지 않습니다.

현재 이 PR은 경계만 준비합니다. 실제 unit·plan/apply는 #8에서 연결하고, 공급자·계정·region·endpoint를 확인하기 전에 전체 live 재귀 실행을 하지 않습니다.
