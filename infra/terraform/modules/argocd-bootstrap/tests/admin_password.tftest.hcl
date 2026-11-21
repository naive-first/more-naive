mock_provider "helm" {}

variables {
  context          = "test-only"
  expected_server  = "https://127.0.0.1:6443"
  kubeconfig       = "/tmp/not-used-by-mock"
  values_file      = "../../../environments/prod/argocd.yaml"
  bootstrap_script = "/tmp/not-executed-by-plan"
}

run "omitted_password_keeps_chart_default" {
  command = plan

  assert {
    condition     = length(helm_release.argocd.set_sensitive) == 0
    error_message = "해시를 지정하지 않으면 Helm 인증 설정을 덮어쓰면 안 됩니다."
  }
}

run "configured_password_reaches_helm_sensitive_setting" {
  command = plan

  variables {
    # 형식 검증 전용 더미 값이며 로그인에 사용하지 않습니다.
    admin_password_hash = "$2a$10$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
  }

  assert {
    condition = length(helm_release.argocd.set_sensitive) == 1 && (
      helm_release.argocd.set_sensitive[0].name == "configs.secret.argocdServerAdminPassword" &&
      helm_release.argocd.set_sensitive[0].value == var.admin_password_hash &&
      helm_release.argocd.set_sensitive[0].type == "string"
    )
    error_message = "비밀번호 해시는 Helm의 sensitive 설정으로 전달해야 합니다."
  }
}

run "plaintext_password_is_rejected" {
  command = plan

  variables {
    admin_password_hash = "not-a-bcrypt-hash"
  }

  expect_failures = [var.admin_password_hash]
}

run "invalid_bcrypt_cost_is_rejected" {
  command = plan

  variables {
    admin_password_hash = "$2a$32$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
  }

  expect_failures = [var.admin_password_hash]
}
