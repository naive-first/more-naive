package main

import (
	"bytes"
	"crypto/sha256"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"unicode/utf8"
)

var assignment = regexp.MustCompile(`^([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*(.*)$`)

func readEnvironment(file string) (map[string]string, error) {
	data, err := os.ReadFile(file)
	if errors.Is(err, os.ErrNotExist) {
		return map[string]string{}, nil
	}
	if err != nil {
		return nil, err
	}
	if !utf8.Valid(data) {
		return nil, errors.New("environment file must be UTF-8")
	}
	values := map[string]string{}
	for i, raw := range bytes.Split(data, []byte{'\n'}) {
		line := strings.TrimSpace(string(raw))
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		match := assignment.FindStringSubmatch(line)
		if match == nil {
			return nil, fmt.Errorf("invalid dotenv syntax at line %d", i+1)
		}
		key, value := match[1], match[2]
		if _, exists := values[key]; exists {
			return nil, fmt.Errorf("duplicate dotenv key at line %d", i+1)
		}
		if strings.HasPrefix(value, "'") || strings.HasPrefix(value, `"`) {
			quote := value[:1]
			if len(value) < 2 || !strings.HasSuffix(value, quote) || strings.Contains(value[1:len(value)-1], quote) {
				return nil, fmt.Errorf("invalid quoted value at line %d", i+1)
			}
			value = value[1 : len(value)-1]
		}
		if strings.ContainsRune(value, 0) {
			return nil, fmt.Errorf("invalid dotenv value at line %d", i+1)
		}
		values[key] = value
	}
	return values, nil
}

func prepareEnvironment(root, target, action, unit string) (map[string]string, error) {
	values, err := readEnvironment(filepath.Join(root, "env.prod"))
	if err != nil {
		return nil, err
	}
	prefix := "RUSTFS_ADMIN"
	keys := []string{"RUSTFS_ENDPOINT", "RUSTFS_DATA_DIR", "RUSTFS_STATE_PATH"}
	if target == "state" {
		if unit != "network" && unit != "compute" && unit != "verify" {
			return nil, errors.New("state requires --unit network|compute|verify")
		}
		keys = []string{"RUSTFS_ENDPOINT", "RUSTFS_BUCKET", "RUSTFS_REGION"}
		if action != "bootstrap" {
			prefix = "RUSTFS_STATE"
		}
	}
	keys = append(keys, prefix+"_ACCESS_KEY", prefix+"_SECRET_KEY")
	env := map[string]string{}
	for _, key := range keys {
		value := values[key]
		if process, found := os.LookupEnv(key); found {
			value = process
		}
		if strings.TrimSpace(value) == "" || strings.ContainsAny(value, "\r\n\x00") {
			return nil, fmt.Errorf("missing or invalid required input: %s", key)
		}
		env[key] = value
	}
	for _, key := range []string{"PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TMP", "TEMP", "XDG_STATE_HOME", "TG_DOWNLOAD_DIR"} {
		if value, exists := os.LookupEnv(key); exists {
			env[key] = value
		}
	}
	env["TG_NO_COLOR"], env["AWS_EC2_METADATA_DISABLED"] = "true", "true"
	endpoint, err := url.Parse(env["RUSTFS_ENDPOINT"])
	if err != nil || endpoint.Hostname() == "" || endpoint.User != nil || endpoint.RawQuery != "" || endpoint.Fragment != "" || (endpoint.Scheme != "http" && endpoint.Scheme != "https") {
		return nil, errors.New("RUSTFS_ENDPOINT must be an explicit http(s) URL without credentials, query or fragment")
	}
	if endpoint.Scheme == "http" && endpoint.Hostname() != "localhost" && endpoint.Hostname() != "127.0.0.1" && endpoint.Hostname() != "::1" {
		return nil, errors.New("HTTP backend is allowed only on loopback; use a private TLS endpoint/tunnel")
	}
	syscall.Umask(0o077)
	if target == "state" {
		return prepareStateCredentials(env, prefix, unit)
	}
	for _, key := range []string{"DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"} {
		if value, exists := os.LookupEnv(key); exists {
			env[key] = value
		}
	}
	name := values["RUSTFS_NAME"]
	if process, found := os.LookupEnv("RUSTFS_NAME"); found {
		name = process
	}
	if name != "" {
		env["RUSTFS_NAME"] = name
	}
	if err := prepareBootstrapPaths(root, env, endpoint); err != nil {
		return nil, err
	}
	// 검증한 환경만 자식에 전달하고 비밀값은 argv에 넣지 않는다.
	for _, pair := range [][2]string{{"RUSTFS_ADMIN_ACCESS_KEY", "TF_VAR_admin_access_key"}, {"RUSTFS_ADMIN_SECRET_KEY", "TF_VAR_admin_secret_key"}} {
		env[pair[1]] = env[pair[0]]
	}
	return env, nil
}

func prepareBootstrapPaths(root string, env map[string]string, endpoint *url.URL) error {
	if endpoint.Scheme != "http" || endpoint.Hostname() != "127.0.0.1" || (endpoint.Path != "" && endpoint.Path != "/") {
		return errors.New("bootstrap requires http://127.0.0.1:PORT on the local Docker host")
	}
	port := 9000
	if endpoint.Port() != "" {
		parsed, err := strconv.Atoi(endpoint.Port())
		if err != nil {
			return errors.New("invalid RustFS port")
		}
		port = parsed
	}
	if port < 1024 || port >= 65535 {
		return errors.New("RustFS port must leave room for the adjacent console port")
	}
	env["RUSTFS_API_PORT"] = strconv.Itoa(port)
	for _, key := range []string{"RUSTFS_STATE_PATH", "RUSTFS_DATA_DIR"} {
		if !outsideCheckout(root, env[key]) {
			return fmt.Errorf("%s must be absolute and outside checkout/cache", key)
		}
	}
	data, err := filepath.EvalSymlinks(env["RUSTFS_DATA_DIR"])
	if err != nil || !outsideCheckout(root, data) {
		return errors.New("RUSTFS_DATA_DIR must resolve outside checkout/cache")
	}
	info, err := os.Stat(data)
	if err != nil || !info.IsDir() || info.Sys().(*syscall.Stat_t).Uid != 10001 {
		return errors.New("RUSTFS_DATA_DIR must exist and be owned by UID 10001")
	}
	parent := filepath.Dir(env["RUSTFS_STATE_PATH"])
	if err := privateDirectory(parent); err != nil {
		return err
	}
	realParent, err := filepath.EvalSymlinks(parent)
	if err != nil || !outsideCheckout(root, realParent) {
		return errors.New("state parent must resolve outside checkout/cache")
	}
	env["RUSTFS_DATA_DIR"] = data
	env["RUSTFS_STATE_PATH"] = filepath.Join(realParent, filepath.Base(env["RUSTFS_STATE_PATH"]))
	syscall.Umask(0o077)
	return nil
}

func outsideCheckout(root, target string) bool {
	if !filepath.IsAbs(target) {
		return false
	}
	relative, err := filepath.Rel(root, filepath.Clean(target))
	return err == nil && (relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator))) && !strings.Contains(string(filepath.Separator)+filepath.Clean(target)+string(filepath.Separator), "/.terragrunt-cache/")
}

func privateDirectory(dir string) error {
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	info, err := os.Stat(dir)
	if err != nil {
		return err
	}
	if !info.IsDir() || info.Mode().Perm()&0o077 != 0 {
		return errors.New("state/credential directory permissions must be 0700")
	}
	return nil
}

func prepareStateCredentials(env map[string]string, prefix, unit string) (map[string]string, error) {
	base := env["XDG_STATE_HOME"]
	if base == "" {
		base = filepath.Join(env["HOME"], ".local/state")
	}
	if !filepath.IsAbs(base) {
		return nil, errors.New("credential state directory must be absolute")
	}
	directory := filepath.Join(base, "more-naive/rustfs")
	if err := privateDirectory(directory); err != nil {
		return nil, err
	}
	identity := fmt.Sprintf("%x", sha256.Sum256([]byte(env["RUSTFS_ENDPOINT"]+env["RUSTFS_BUCKET"])))[:16]
	file, err := os.CreateTemp(directory, ".credentials-*")
	if err != nil {
		return nil, err
	}
	defer os.Remove(file.Name())
	for _, section := range []string{"more-naive-state", "profile more-naive-state"} {
		if _, err = fmt.Fprintf(file, "[%s]\naws_access_key_id = %s\naws_secret_access_key = %s\n\n", section, env[prefix+"_ACCESS_KEY"], env[prefix+"_SECRET_KEY"]); err != nil {
			file.Close()
			return nil, err
		}
	}
	if err := file.Close(); err != nil {
		return nil, err
	}
	credentials := filepath.Join(directory, identity+".credentials")
	if err := os.Rename(file.Name(), credentials); err != nil {
		return nil, err
	}
	env["RUSTFS_CREDENTIALS_FILE"], env["RUSTFS_STATE_UNIT"] = credentials, unit
	return env, nil
}

func environmentList(values map[string]string) []string {
	result := make([]string, 0, len(values))
	for key, value := range values {
		result = append(result, key+"="+value)
	}
	return result
}
