# prod 노드 구성

고정 k3s 버전은 `v1.35.10+k3s1`입니다. 실제 역할·hostname·SSH 개인키 경로가 확인되기 전에는 이 예시를 배포하지 않습니다. `server.yaml.example`은 #9 bootstrap이 생성하는 공통 server 설정의 예시이며 실행 가능한 실제 inventory가 아닙니다. node-name은 `--node`, server/agent는 `--role`로 전달합니다. agent는 외부 `K3S_SERVER_URL`, 양쪽은 root `.env` loader의 `K3S_TOKEN`을 사용합니다. 값은 파일에 복사하지 않습니다.

[공식 k3s server 옵션](https://docs.k3s.io/cli/server)에 따라 Traefik과 ServiceLB만 비활성화합니다. Istio 사설 gateway 경로를 따로 준비하며 CNI·CoreDNS·network policy는 유지합니다. 실제 `/etc/rancher/k3s/config.yaml`과 token-file은 #9 도구가 0600으로 생성하므로 예시 파일을 별도로 덮어쓰지 않습니다.

운영자가 #37의 허용 OS 사용자·Tailscale SSH·sudo를 확인한 뒤 #9 preflight와 `--apply`를 실행합니다. 이후 외부에 보관한 kubeconfig의 context 이름·API server 주소·노드 목록을 실제 cluster와 대조합니다. kubeconfig 전체나 토큰을 PR/로그로 출력하지 않습니다. 운영 context는 `more-naive-prod`를 명시하고 아래 검증 도구에 실제 API server URL과 각 실제 node 이름을 전달합니다.

```bash
python3 infra/k3s/scripts/verify.py --environment prod --context more-naive-prod \
  --expected-server 'https://<사설-api-server>:6443' --node '<실제-node>'
```

기본 명령은 context/server/정확한 노드 집합과 Ready만 확인합니다. 실제 DNS·노드 간 Pod 통신을 보려면 같은 명령에 `--write-smoke`를 추가합니다. 도구는 고유 임시 namespace에서 노드별 busybox Pod를 만들고 Kubernetes Service DNS와 모든 노드 쌍의 Pod IP HTTP를 검사한 뒤 자신이 만든 namespace만 제거합니다. 단일 노드면 cross-node 증거는 없으며 같은 노드의 Pod 통신만 확인합니다.

노드 Ready 실패는 `kubectl describe node`, DNS 실패는 CoreDNS Pod/Service, HTTP 실패는 CNI/network policy/방화벽을 확인합니다. context/server/노드 불일치에서는 Pod 생성 전 중단합니다. 단일 노드·local-path 저장소는 노드나 디스크 장애를 견디는 HA가 아닙니다. snapshot schedule·백업·복원 리허설은 추가하지 않습니다.

2026-11-14 이 작업 환경에는 제공된 study-k3s-access 개인키가 없어 실제 node Ready/DNS/통신은 미수행입니다. VM이 k3s 노드인지 proxy인지도 미확인입니다. 운영자가 역할·실제 hostname·개인키·known_hosts·허용 정책을 준비한 뒤 설치/검증을 수행해야 #10을 완료할 수 있습니다.
