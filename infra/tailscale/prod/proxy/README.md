# 기존 proxy VM 확인

현재 제공된 주소는 `study@study-k3s-access.tail373827.ts.net`(100.90.91.104)입니다. VM의 proxy/node 역할·실제 hostname·HTTPS hostname·TLS 종료·Istio 사설 upstream이 미확인이고 이 Linux 작업 호스트에는 제공된 개인키가 없습니다. 연결 성공이나 proxy 제품을 확정하지 않습니다.

## 읽기 전용 검사

VM 운영자가 실제 hostname과 SSH 개인키/known_hosts를 준비한 뒤 아래 예시를 실제 입력으로 바꿔 실행합니다. owner-only 개인키·tailnet 전용 주소·명시 prod·원격 user/hostname을 확인하며 host key 검증을 끄지 않습니다.

```bash
python3 infra/tailscale/prod/proxy/inspect_proxy.py --environment prod \
  --host study-k3s-access.tail373827.ts.net --user study \
  --key-file ~/.ssh/study-k3s-access --expected-host '<실제-proxy-hostname>'
```

스크립트는 자기 VM의 Tailscale state·DNS 이름/IP·Serve 포트/host 목록과 비대화 sudo 가능 여부만 요약합니다. peer 목록, 전체 Serve 설정, 인증값, kubeconfig를 출력하지 않습니다. nginx/caddy 등 별도 proxy의 전체 설정도 출력하지 않으므로 그 제품을 쓰면 VM 운영자가 비밀을 제외한 TLS/Host/upstream 계약을 별도로 확인합니다. 설정 변경·Serve reset·Funnel·노드 재가입·서비스 재시작은 실행하지 않습니다.

## 사설 upstream 확인

#15의 실제 gateway Service/Host/포트와 VM에서 도달 가능한 사설 경로가 확인되면 `--upstream-url`과 `--gateway-host`를 함께 전달합니다. VM에서 DNS를 해석해 공인 주소가 없는지 확인한 뒤 주어진 URL에 GET을 한 번 보내 HTTP 상태만 요약합니다. redirect는 따라가지 않고 TLS 인증서를 기본 검증합니다. URL의 인증값/query/fragment는 허용하지 않습니다. 404/503도 도달 상태일 뿐 실제 gateway/API 성공으로 세지 않습니다.

외부 VM에서 ClusterIP에 직접 도달한다고 가정하지 않습니다. 실제 사설 네트워크/터널/로컬 relay 중 확인한 최소 경로를 사용해야 합니다. [Tailscale Serve 문서](https://tailscale.com/docs/reference/tailscale-cli/serve)의 로컬 proxy 대상과 Istio까지의 전달 경로는 각각 확인합니다. 아직 구성이 없으므로 `tailscale serve` 변경 명령을 생성하거나 기존 설정을 덮어쓰지 않습니다.

```bash
python3 -m unittest discover -s infra/tailscale/prod/proxy -p 'test*.py' -v
```

guard unit tests는 실제 VM 연결을 대신하지 않습니다. 2026-11-14 VM 검사·upstream 도달·TLS/HTTPS Host·재시작 유지 확인은 NOT_RUN입니다. VM/tailnet 운영자가 접속 권한·기존 설정·허용 사용자 정책을 제공하면 읽기 검사를 수행해 현재 제품/포트/TLS 종료/사설 경로를 기록하고 필요한 최소 변경을 검토합니다. 이후 #23에서 허용 클라이언트 HTTPS→Istio와 재시작 후 유지를 확인해야 합니다. Operator/OAuth Secret이나 공인 gateway/Funnel을 필수로 추가하지 않습니다.
