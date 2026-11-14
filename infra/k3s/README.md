# prod k3s bootstrap

`scripts/bootstrap.py`는 명시한 prod tailnet 노드에서 고정 k3s `v1.35.10+k3s1`을 설치합니다. 실제 prod 접속·설치는 아직 검증하지 않았습니다. Python3, SSH, 노드의 Tailscale 등록과 `sudo -n` 권한이 필요합니다.

```bash
python3 infra/k3s/scripts/bootstrap.py --environment prod \
  --host study-k3s-access.tail373827.ts.net --user study \
  --node '<실제 hostname>' --key-file ~/.ssh/study-k3s-access --role server
```

기본은 사전 확인만 수행합니다. SSH known_hosts와 owner-only 개인키를 먼저 준비하고, 루트 `.env` 도구의 k3s 소비자로 `K3S_TOKEN`을 전달합니다. 토큰을 명령 인자·Git·로그에 적지 않습니다. agent는 외부 `K3S_SERVER_URL=https://<사설 server>:6443`도 필요합니다. 위 `<실제 hostname>`은 입력 설명이며 문자 그대로 실행하지 않습니다.

대상의 모든 DNS 주소가 tailnet 범위인지 확인한 후 SSH에서 OS 사용자·hostname·Tailscale Running과 sudo를 대조합니다. 성공 뒤 `--apply`를 추가해야 설치합니다. 환경 생략/dev·다른 hostname·필수 입력 누락은 설치 전에 중단합니다.

[공식 구성 방식](https://docs.k3s.io/installation/configuration)에 맞춰 `/etc/rancher/k3s/config.yaml`과 별도 token-file을 root 전용으로 저장합니다. server는 Traefik과 ServiceLB를 비활성화해 기존 포트 공개와 Istio 충돌을 피합니다. installer는 고정 release 경로와 SHA256을 확인한 뒤 실행합니다. server의 kubeconfig는 0600이며 자동으로 복사하거나 출력하지 않습니다.

재실행은 버전·구성·토큰과 서비스 상태가 모두 같으면 변경하지 않습니다. 이미 존재하는 다른 구성이나 버전은 자동 덮어쓰기/업그레이드하지 않고 중단합니다. 설치 도중 실패한 경우 남은 구성과 서비스 상태를 운영자가 확인한 뒤 재시도 여부를 판단합니다.

진단은 DNS/known_hosts·키 권한, OS 사용자와 hostname, `sudo -n true`, `tailscale status`, 노드의 `systemctl status k3s` 순으로 합니다. 명령 출력에 토큰·kubeconfig를 포함하지 않습니다. uninstall은 노드/워크로드에 영향을 주므로 이 도구가 자동 실행하지 않습니다. 데이터/PVC 삭제와 백업·복원은 bootstrap 검증에 포함하지 않습니다.
