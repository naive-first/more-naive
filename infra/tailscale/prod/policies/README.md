# 기존 tailnet 정책의 추가 변경

현재 tailnet 정책과 허용 운영자 그룹·노드 태그 소유자가 제공되지 않았습니다. 이 경로는 전체 정책을 생성하거나 자동 업로드하지 않습니다. tailnet 관리자가 기존 파일을 읽고 아래 두 종류를 별도로 검토한 뒤 필요한 항목만 추가합니다.

| 경계 | 확인할 입력·완료 기준 |
| --- | --- |
| 네트워크 접근 | 실제 운영자 identity/group → Proxmox의 prod tailnet 주소에서 필요한 SSH·API 6443 허용. 사용자 그룹에는 필요한 HTTPS 443 허용 |
| Tailscale SSH | 실제 source identity/group, 실제 node destination, 허용 OS 사용자 `study` 등, check/accept 방식과 필요한 재인증 정책을 관리자가 결정 |
| 태그 소유권 | Proxmox 게이트웨이의 기존 태그와 태그 소유자를 확인 |
| 거부 검증 | 비허용 테스트 주체/OS 사용자로 접속 거부를 실제 확인. 테스트 identity를 임의로 만들거나 현재 사용자 권한을 바꾸지 않음 |

[Tailscale SSH 문서](https://tailscale.com/docs/features/tailscale-ssh)의 네트워크 허용과 SSH 권한 요구를 함께 확인합니다. SSH를 켠 것만으로 허용 정책 검증을 대신하지 않습니다. 실제 원본 정책과 관리 승인이 없으므로 적용된 ACL·SSH 규칙을 이 저장소가 소유한다고 주장하지 않습니다.
