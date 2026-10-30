// Package config: 环境驱动配置（对齐 Python 版语义）
package config

import (
	"os"
	"strconv"
	"strings"
)

type Upstream struct {
	Name       string
	BaseURL    string
	APIKey     string
	Model      string
	TimeoutSec int
	Weight     int
}

type Settings struct {
	Host         string
	Port         int
	GWKeys       []string
	AdminKeys    []string
	WriteGuard   bool
	RPM          int
	LogDir       string
	DefaultRoute string
	Upstreams    []Upstream
}

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func envInt(k string, def int) int {
	if v := os.Getenv(k); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func envList(k string) []string {
	raw := os.Getenv(k)
	if raw == "" {
		return nil
	}
	var out []string
	for _, s := range strings.Split(raw, ",") {
		if s = strings.TrimSpace(s); s != "" {
			out = append(out, s)
		}
	}
	return out
}

func Load() *Settings {
	s := &Settings{
		Host:         env("GW_HOST", "0.0.0.0"),
		Port:         envInt("GW_PORT", 8788),
		GWKeys:       envList("GW_KEYS"),
		AdminKeys:    envList("GW_ADMIN_KEYS"),
		WriteGuard:   env("GW_ADMIN_WRITE_GUARD", "0") == "1",
		RPM:          envInt("GW_RPM", 120),
		LogDir:       env("GW_LOG_DIR", "logs"),
		DefaultRoute: env("GW_DEFAULT_ROUTE", ""),
	}
	if k := env("DEEPSEEK_API_KEY", ""); k != "" {
		s.Upstreams = append(s.Upstreams, Upstream{Name: "deepseek",
			BaseURL: env("DEEPSEEK_BASE", "https://api.deepseek.com/v1"), APIKey: k,
			Model: env("DEEPSEEK_MODEL", "deepseek-chat"), TimeoutSec: 180, Weight: 100})
	}
	if k := env("OPENAI_API_KEY", ""); k != "" {
		s.Upstreams = append(s.Upstreams, Upstream{Name: "openai",
			BaseURL: "https://api.openai.com/v1", APIKey: k,
			Model: env("OPENAI_MODEL", "gpt-4o"), TimeoutSec: 180, Weight: 100})
	}
	if k := env("RELAY_API_KEY", ""); k != "" && env("RELAY_BASE", "") != "" {
		s.Upstreams = append(s.Upstreams, Upstream{Name: "relay",
			BaseURL: env("RELAY_BASE", ""), APIKey: k,
			Model: env("RELAY_MODEL", "gpt-4o"), TimeoutSec: 180, Weight: 100})
	}
	if len(s.Upstreams) == 0 {
		s.Upstreams = append(s.Upstreams, Upstream{Name: "primary",
			BaseURL: env("PRIMARY_BASE", "https://api.openai.com/v1"),
			APIKey: env("PRIMARY_API_KEY", "sk-placeholder"),
			Model:  env("PRIMARY_MODEL", "gpt-4o-mini"), TimeoutSec: 180, Weight: 100})
	}
	if s.DefaultRoute == "" {
		s.DefaultRoute = s.Upstreams[0].Name
	}
	return s
}
