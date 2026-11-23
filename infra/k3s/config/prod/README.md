# prod 노드 구성

고정 k3s 버전은 `v1.35.10+k3s1`입니다. 실제 역할·hostname·SSH 개인키 경로가 확인되기 전에는 이 예시를 배포하지 않습니다. `server.yaml.example`은 #9 bootstrap이 생성하는 공통 server 설정의 예시이며 실행 가능한 실제 inventory가 아닙니다. node-name은 `K3S_NODE_NAME`, server/agent는 `K3S_ROLE`로 전달합니다. agent는 외부 `K3S_SERVER_URL`, 양쪽은 direnv가 선택한 `env.prod`의 `K3S_TOKEN`을 사용합니다. 실제 token을 예시 YAML에 복사하지 않습니다.

[공식 k3s server 옵션](https://docs.k3s.io/cli/server)에 따라 Traefik과 ServiceLB만 비활성화합니다. Istio 사설 gateway 경로를 따로 준비하며 CNI·CoreDNS·network policy는 유지합니다. 실제 `/etc/rancher/k3s/config.yaml`과 token-file은 #9 도구가 0600으로 생성하므로 예시 파일을 별도로 덮어쓰지 않습니다.

운영자가 허용 OS 사용자·SSH host key·sudo를 확인한 뒤 native Terraform init → plan 검토 → 저장 plan apply 절차를 실행합니다. prod 서버의 `/etc/rancher/k3s/config.yaml.d/60-tailnet-tls.yaml`은 Istio prod values의 Host를 `tls-san+`으로 추가합니다. 신규 설치는 기동 전에 이 파일을 준비합니다. 기존 설치는 기본 config와 token이 일치하는 경우에만 진행하며 SAN 파일이 달라졌을 때만 k3s를 재시작합니다. 프로비저닝이 k3s 서버 CA로 설정된 이름의 인증서를 확인합니다. [k3s drop-in 문서](https://docs.k3s.io/installation/configuration)

운영 context는 `more-naive-prod`를 사용합니다. 외부에 보관한 kubeconfig의 기존 k3s CA와 클라이언트 자격 증명은 유지하고 서버를 `https://more-naive-vm.tail373827.ts.net:6443`으로 설정합니다. `env.prod`의 `KUBE_SERVER`에도 같은 주소를 사용합니다. kubeconfig 전체나 토큰을 PR이나 로그에 출력하지 않습니다.

```bash
MORE_NAIVE_ENV=prod direnv exec config/env bash infra/k3s/scripts/verify.sh \
  --node '<실제-node-1>' --node '<실제-node-2>'
```

기본 명령은 context/server/정확한 노드 집합과 Ready만 확인합니다. 실제 DNS·노드 간 Pod 통신을 보려면 같은 명령에 `--write-smoke`를 추가합니다. 도구는 고유 임시 namespace에서 노드별 busybox Pod를 만들고 Kubernetes Service DNS와 모든 노드 쌍의 Pod IP HTTP를 검사한 뒤 자신이 만든 namespace만 제거합니다. 단일 노드면 cross-node 증거는 없으며 같은 노드의 Pod 통신만 확인합니다.

노드 Ready 실패는 `kubectl describe node`, DNS 실패는 CoreDNS Pod/Service, HTTP 실패는 CNI/network policy/방화벽을 확인합니다. context/server/노드 불일치에서는 Pod 생성 전 중단합니다. 단일 노드·local-path 저장소는 노드나 디스크 장애를 견디는 HA가 아닙니다. snapshot schedule·백업·복원 리허설은 추가하지 않습니다.

2026-11-15 제공된 VM `system-design-study`를 prod 단일 server 노드로 지정하고 Terraform remote-exec로 설치했습니다. `v1.35.10+k3s1`의 Ready, 기본 `local-path`, Kubernetes Service DNS와 같은 노드의 Pod HTTP 통신을 확인하고 검증용 namespace를 제거했습니다. 노드 간 통신은 단일 노드라 검증하지 않았습니다. [실제 설치·확인 명령과 raw 결과](https://github.com/naive-first/more-naive/pull/49#issuecomment-6894253308)를 참조합니다. 기존 RustFS Docker와 bootstrap local state는 같은 VM의 k3s 밖에서 유지합니다.
