# prod Tailscale 게이트웨이

Tailnet 접속 주소는 `more-naive-vm.tail373827.ts.net`입니다. Proxmox가 HTTPS 443을 종료해 VM 104의 [HTTP 릴레이](proxy/README.md)에 전달하고, TCP 6443과 관리 SSH를 같은 VM으로 전달합니다. Kubernetes API는 [k3s SAN과 기존 CA](../../k3s/config/prod/README.md)를 사용합니다.

## 기존 guest 설치의 상태 이전

`prod/tailscale`은 기존 RustFS state key `more-naive/prod/tailscale/terraform.tfstate`를 유지합니다. `terraform_data.installation`의 `removed` 블록은 Terraform 상태에서만 설치 marker를 제거합니다. VM의 파일·등록 정보·systemd 서비스에는 작업을 실행하지 않습니다.

```bash
umask 077
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale run -- init -input=false
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale run -- state list
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale run -- plan -input=false -out=/absolute/private/tailscale.tfplan
MORE_NAIVE_ENV=prod direnv exec config/env terragrunt --working-dir infra/terragrunt/live/prod/tailscale run -- apply -input=false /absolute/private/tailscale.tfplan
```

기존 state의 plan에는 `terraform_data.installation`의 관리 해제만 있어야 합니다. 빈 state에서는 변경이 없어야 합니다. 적용 전에 plan의 create/replace/destroy가 모두 0인지 확인합니다. 이 unit에는 SSH나 guest Tailscale 인증 입력이 필요하지 않습니다. [Terraform 상태 제거 문서](https://developer.hashicorp.com/terraform/language/state/remove)

기존 VM에서 `systemctl show more-naive-tailscaled.service -p ActiveState -p UnitFileState`가 `inactive`와 `disabled`를 반환하는지 확인합니다. 새 VM에는 이 서비스가 없습니다. 운영 검증이 끝난 뒤 관리 콘솔의 오프라인 `more-naive-vm-1` 기록은 Tailscale 관리자가 별도로 삭제할 수 있습니다. [Tailscale 기기 삭제 문서](https://tailscale.com/docs/features/access-control/device-management/how-to/remove)
