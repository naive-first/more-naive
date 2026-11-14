package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"syscall"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	code, err := run(ctx, os.Args[1:])
	if err != nil {
		fmt.Fprintln(os.Stderr, "infraexec:", err)
		var exit *exec.ExitError
		if errors.As(err, &exit) && exit.ExitCode() > 0 {
			code = exit.ExitCode()
		} else if code == 0 {
			code = 1
		}
	}
	os.Exit(code)
}

func run(ctx context.Context, args []string) (int, error) {
	if len(args) > 0 && args[0] == "_terraform" {
		return runTerraform(ctx, args[1:])
	}
	flags := flag.NewFlagSet("infraexec", flag.ContinueOnError)
	environment := flags.String("env", "", "required: prod")
	target := flags.String("target", "", "required: bootstrap or state")
	unit := flags.String("unit", "", "state unit: network, compute or verify")
	repo := flags.String("repo-root", "", "repository root; default: nearest ancestor")
	allowDestroy := flags.Bool("allow-destroy", false, "allow bootstrap container removal; retain data")
	if err := flags.Parse(args); err != nil {
		return 2, err
	}
	if *environment != "prod" || (*target != "bootstrap" && *target != "state") {
		return 2, errors.New("--env prod and --target bootstrap|state are required")
	}
	if len(flags.Args()) == 0 {
		return 2, errors.New("an action is required")
	}
	action := flags.Args()[0]
	if action == "destroy" && (*target != "bootstrap" || !*allowDestroy) {
		return 2, errors.New("destroy requires bootstrap --allow-destroy; persistent data is retained")
	}
	if action == "bootstrap" && *target != "state" {
		return 2, errors.New("bucket bootstrap requires --target state")
	}
	if action != "bootstrap" {
		if _, err := parseAction(flags.Args()); err != nil {
			return 2, err
		}
	}
	root, err := repositoryRoot(*repo)
	if err != nil {
		return 1, err
	}
	env, err := prepareEnvironment(root, *target, action, *unit)
	if err != nil {
		return 2, err
	}
	terraform, err := exec.LookPath("terraform")
	if err != nil {
		return 1, err
	}
	terraform, err = filepath.Abs(terraform)
	if err != nil {
		return 1, err
	}
	env["TG_TF_PATH"] = terraform
	workdir, err := os.Getwd()
	if err != nil {
		return 1, err
	}
	if *target == "bootstrap" {
		workdir = filepath.Join(root, "infra/terragrunt/bootstrap/rustfs")
	}
	argv := []string{"exec", "--tf-path", terraform, "--in-download-dir", "--no-auto-init", "--"}
	if action == "bootstrap" {
		if len(flags.Args()) != 1 {
			return 2, errors.New("bucket bootstrap accepts no extra options")
		}
		argv = []string{"backend", "bootstrap"}
		env["TG_NON_INTERACTIVE"] = "true"
	} else {
		self, err := os.Executable()
		if err != nil {
			return 1, err
		}
		argv = append(argv, self, "_terraform")
		argv = append(argv, flags.Args()...)
	}
	// HCL 준비만 Terragrunt에 맡기고 실제 Terraform 명령은 자식의 SDK가 실행한다.
	cmd := exec.CommandContext(ctx, "terragrunt", argv...)
	cmd.Dir = workdir
	cmd.Env = environmentList(env)
	cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
	return 0, cmd.Run()
}

func repositoryRoot(explicit string) (string, error) {
	if explicit != "" {
		return filepath.Abs(explicit)
	}
	dir, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "infra/terraform/modules/rustfs/main.tf")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", errors.New("repository not found; specify --repo-root")
		}
		dir = parent
	}
}
