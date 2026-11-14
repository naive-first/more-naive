package main

import (
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestUnsafeRequestsStopBeforeExecution(t *testing.T) {
	for _, args := range [][]string{
		{"--env", "dev", "--target", "bootstrap", "apply", "-auto-approve"},
		{"--target", "bootstrap", "init"},
		{"--env", "prod", "--target", "bootstrap", "apply"},
		{"--env", "prod", "--target", "bootstrap", "destroy", "-auto-approve"},
		{"--env", "prod", "--target", "state", "plan", "-lock=false"},
		{"--env", "prod", "--target", "state", "init", "-migrate-state"},
	} {
		code, err := run(context.Background(), args)
		if code != 2 || err == nil {
			t.Fatalf("unsafe request was not refused: %v code=%d err=%v", args, code, err)
		}
	}
}

func TestLiteralEnvironmentParsingAndSecretFreeErrors(t *testing.T) {
	file := filepath.Join(t.TempDir(), "env.prod")
	for _, content := range []string{"SECRET=hidden\nSECRET=hidden\n", "SECRET='hidden\n", "SECRET=hidden\x00\n", "export SECRET=hidden\n"} {
		if err := os.WriteFile(file, []byte(content), 0o600); err != nil {
			t.Fatal(err)
		}
		_, err := readEnvironment(file)
		if err == nil || strings.Contains(err.Error(), "hidden") {
			t.Fatalf("bad syntax was accepted or error disclosed a value: %v", err)
		}
	}
	content := "A='$(touch /tmp/never) ${HOME} # literal'\nB=공백 유지\n"
	os.WriteFile(file, []byte(content), 0o600)
	values, err := readEnvironment(file)
	if err != nil || values["A"] != "$(touch /tmp/never) ${HOME} # literal" || values["B"] != "공백 유지" {
		t.Fatalf("environment values were expanded or changed: %v", err)
	}
}

func TestStateCredentialsAreIsolatedAndPrivate(t *testing.T) {
	root := t.TempDir()
	t.Setenv("XDG_STATE_HOME", t.TempDir())
	t.Setenv("GH_TOKEN", "unrelated-token")
	t.Setenv("AWS_ACCESS_KEY_ID", "unrelated-aws")
	t.Setenv("PYTHONPATH", "unrelated-python")
	file := "RUSTFS_ENDPOINT=http://127.0.0.1:9000\nRUSTFS_BUCKET=proof\nRUSTFS_REGION=us-east-1\nRUSTFS_STATE_ACCESS_KEY=state-access\nRUSTFS_STATE_SECRET_KEY=state-secret\nRUSTFS_ADMIN_ACCESS_KEY=admin-access\nRUSTFS_ADMIN_SECRET_KEY=admin-secret\n"
	os.WriteFile(filepath.Join(root, "env.prod"), []byte(file), 0o600)
	os.WriteFile(filepath.Join(root, "env.dev"), []byte("broken dev file"), 0o600)
	env, err := prepareEnvironment(root, "state", "init", "verify")
	if err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"GH_TOKEN", "AWS_ACCESS_KEY_ID", "PYTHONPATH", "RUSTFS_ADMIN_ACCESS_KEY", "RUSTFS_ADMIN_SECRET_KEY"} {
		if _, found := env[key]; found {
			t.Fatalf("unexpected credential crossed execution boundary: %s", key)
		}
	}
	credentials := env["RUSTFS_CREDENTIALS_FILE"]
	info, err := os.Stat(credentials)
	if err != nil || info.Mode().Perm() != 0o600 {
		t.Fatal("credential file is not 0600")
	}
	content, _ := os.ReadFile(credentials)
	if strings.Contains(string(content), "admin-secret") || !strings.Contains(string(content), "state-secret") {
		t.Fatal("credential profile used the wrong identity")
	}
	second, err := prepareEnvironment(root, "state", "init", "verify")
	if err != nil || second["RUSTFS_CREDENTIALS_FILE"] != credentials {
		t.Fatal("credential path changed between executions")
	}
	t.Setenv("RUSTFS_STATE_SECRET_KEY", "")
	if _, err = prepareEnvironment(root, "state", "plan", "verify"); err == nil {
		t.Fatal("blank process override fell back to the environment file")
	}
}

func TestMissingProdDoesNotReadLegacyOrDev(t *testing.T) {
	root := t.TempDir()
	for _, name := range []string{"env.dev", ".env"} {
		os.WriteFile(filepath.Join(root, name), []byte("RUSTFS_ENDPOINT=http://127.0.0.1:9000\n"), 0o600)
	}
	if _, err := prepareEnvironment(root, "state", "plan", "verify"); err == nil {
		t.Fatal("missing prod input accepted")
	}
}

func TestRealTerraformSDKLifecycle(t *testing.T) {
	if _, err := exec.LookPath("terraform"); err != nil {
		t.Skip("Terraform 1.17.2 is required for the runtime integration test")
	}
	workdir := t.TempDir()
	t.Chdir(workdir)
	t.Setenv("TMPDIR", t.TempDir())
	t.Setenv("TF_VAR_value", "proof-literal")
	config := `terraform { required_version = "= 1.17.2" }
variable "value" { type = string }
resource "terraform_data" "proof" { input = var.value }
output "private" {
  value = var.value
  sensitive = true
}
`
	if err := os.WriteFile("main.tf", []byte(config), 0o600); err != nil {
		t.Fatal(err)
	}
	backend := fmt.Sprintf("terraform {\n backend \"local\" {\n  path = %q\n }\n}\n", filepath.Join(t.TempDir(), "persisted.tfstate"))
	if err := os.WriteFile("backend.tf", []byte(backend), 0o600); err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	plan := filepath.Join(workdir, "reviewed.tfplan")
	for _, step := range []struct {
		args []string
		code int
	}{
		{[]string{"init"}, 0},
		{[]string{"validate"}, 0},
		{[]string{"plan", "-out=" + plan, "-detailed-exitcode"}, 2},
		{[]string{"apply", plan}, 0},
		{[]string{"plan", "-detailed-exitcode"}, 0},
	} {
		code, err := runTerraform(ctx, step.args)
		if err != nil || code != step.code {
			t.Fatalf("real SDK action %s: code=%d err=%v", step.args[0], code, err)
		}
	}
	second := t.TempDir()
	os.WriteFile(filepath.Join(second, "main.tf"), []byte(config), 0o600)
	os.WriteFile(filepath.Join(second, "backend.tf"), []byte(backend), 0o600)
	t.Chdir(second)
	if code, err := runTerraform(ctx, []string{"plan", "-detailed-exitcode"}); err != nil || code != 0 {
		t.Fatalf("new cache did not reload the same state: code=%d err=%v", code, err)
	}
	original := os.Stdout
	reader, writer, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	os.Stdout = writer
	_, outputErr := runTerraform(ctx, []string{"output"})
	os.Stdout = original
	writer.Close()
	output, _ := io.ReadAll(reader)
	reader.Close()
	if outputErr != nil || strings.Contains(string(output), "proof-literal") || !strings.Contains(string(output), "sensitive value") {
		t.Fatalf("output disclosed a sensitive value or failed: %v", outputErr)
	}
}
