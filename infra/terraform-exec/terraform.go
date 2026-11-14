package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/hashicorp/terraform-exec/tfexec"
)

type actionOptions struct {
	name, out, replace, plan string
	lockTimeout              time.Duration
	detailed                 bool
}

func parseAction(args []string) (actionOptions, error) {
	options := actionOptions{name: args[0]}
	switch options.name {
	case "init", "validate", "plan", "apply", "destroy", "output":
	default:
		return options, errors.New("unsupported Terraform action")
	}
	flags := flag.NewFlagSet(options.name, flag.ContinueOnError)
	input := flags.Bool("input", false, "interactive input is disabled")
	noColor := flags.Bool("no-color", true, "SDK output is always plain text")
	approve := flags.Bool("auto-approve", false, "explicitly approve apply/destroy")
	flags.StringVar(&options.out, "out", "", "saved plan path")
	flags.StringVar(&options.replace, "replace", "", "replace one resource")
	flags.DurationVar(&options.lockTimeout, "lock-timeout", 0, "state lock timeout")
	flags.BoolVar(&options.detailed, "detailed-exitcode", false, "plan returns 2 when changes exist")
	if err := flags.Parse(args[1:]); err != nil {
		return options, err
	}
	if *input || !*noColor {
		return options, errors.New("SDK execution requires noninteractive input and plain output")
	}
	if len(flags.Args()) > 1 || (len(flags.Args()) > 0 && options.name != "apply") {
		return options, errors.New("only apply accepts a saved plan argument")
	}
	if len(flags.Args()) == 1 {
		options.plan = flags.Args()[0]
	}
	if (options.name == "apply" && options.plan == "" || options.name == "destroy") && !*approve {
		return options, errors.New("SDK apply/destroy requires explicit -auto-approve or an apply saved plan")
	}
	if options.lockTimeout < 0 {
		return options, errors.New("lock-timeout must not be negative")
	}
	return options, nil
}

func runTerraform(ctx context.Context, args []string) (int, error) {
	if len(args) == 0 {
		return 2, errors.New("a Terraform action is required")
	}
	options, err := parseAction(args)
	if err != nil {
		return 2, err
	}
	workdir, err := os.Getwd()
	if err != nil {
		return 1, err
	}
	binary, err := exec.LookPath("terraform")
	if err != nil {
		return 1, err
	}
	tf, err := tfexec.NewTerraform(workdir, binary)
	if err != nil {
		return 1, err
	}
	env := map[string]string{}
	for _, item := range os.Environ() {
		key, value, _ := strings.Cut(item, "=")
		env[key] = value
	}
	// SDK의 기본 환경 상속으로 Terragrunt TF_VAR의 문자열/구조화 값 의미를 보존한다.
	// CLI 인자 주입 변수는 제거하고, 공개 진입점은 그 전에 목적별 환경을 제한한다.
	for _, key := range tfexec.ProhibitedEnv(env) {
		if !strings.HasPrefix(key, "TF_VAR_") {
			os.Unsetenv(key)
		}
	}
	version, _, err := tf.Version(ctx, true)
	if err != nil {
		return 1, err
	}
	if version.String() != "1.17.2" {
		return 1, errors.New("Terraform 1.17.2 is required")
	}
	tf.SetStderr(os.Stderr)
	if options.name != "output" {
		tf.SetStdout(os.Stdout)
	}
	// 새 Terragrunt 캐시만 SDK로 초기화한다. 기존 backend 변경은 자동 재구성하지 않는다.
	if options.name != "init" {
		_, backendErr := os.Stat("backend.tf")
		_, metadataErr := os.Stat(".terraform/terraform.tfstate")
		if backendErr == nil && errors.Is(metadataErr, os.ErrNotExist) {
			if err := tf.Init(ctx); err != nil {
				return 1, err
			}
		}
	}
	switch options.name {
	case "init":
		err = tf.Init(ctx)
	case "validate":
		result, validateErr := tf.Validate(ctx)
		err = validateErr
		if err == nil && !result.Valid {
			err = errors.New("Terraform validation failed")
		}
	case "plan":
		opts := []tfexec.PlanOption{tfexec.LockTimeout(options.lockTimeout.String())}
		if options.out != "" {
			opts = append(opts, tfexec.Out(options.out))
		}
		if options.replace != "" {
			opts = append(opts, tfexec.Replace(options.replace))
		}
		changed, planErr := tf.Plan(ctx, opts...)
		if planErr == nil && changed && options.detailed {
			return 2, nil
		}
		err = planErr
	case "apply":
		opts := []tfexec.ApplyOption{tfexec.LockTimeout(options.lockTimeout.String())}
		if options.plan != "" {
			opts = append(opts, tfexec.DirOrPlan(options.plan))
		} else {
			if options.replace != "" {
				opts = append(opts, tfexec.Replace(options.replace))
			}
		}
		err = tf.Apply(ctx, opts...)
	case "destroy":
		err = tf.Destroy(ctx, tfexec.LockTimeout(options.lockTimeout.String()))
	case "output":
		outputs, outputErr := tf.Output(ctx)
		if outputErr != nil {
			return 1, outputErr
		}
		for name, output := range outputs {
			value := string(output.Value)
			if output.Sensitive {
				value = "(sensitive value)"
			}
			fmt.Fprintf(os.Stdout, "%s = %s\n", name, value)
		}
	}
	return 0, err
}
