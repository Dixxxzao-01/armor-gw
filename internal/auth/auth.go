// Package auth: 下游 key 鉴权 + admin 分级（平移 Python 修复版语义）
package auth

import (
	"net/http"
	"strings"

	"armor-gw/internal/config"
)

func Extract(r *http.Request) string {
	if h := r.Header.Get("Authorization"); h != "" {
		if strings.HasPrefix(strings.ToLower(h), "bearer ") {
			return strings.TrimSpace(h[7:])
		}
	}
	return strings.TrimSpace(r.Header.Get("x-api-key"))
}

func IsValid(key string, s *config.Settings) bool {
	if key == "" {
		return false
	}
	for _, k := range s.GWKeys {
		if k == key {
			return true
		}
	}
	return false
}

func IsAdmin(key string, s *config.Settings) bool {
	if key == "" {
		return false
	}
	if len(s.AdminKeys) > 0 {
		for _, k := range s.AdminKeys {
			if k == key {
				return true
			}
		}
		return false
	}
	return IsValid(key, s)
}

func RequireAuth(w http.ResponseWriter, r *http.Request, s *config.Settings) string {
	key := Extract(r)
	if !IsValid(key, s) {
		http.Error(w, `{"error":"invalid_api_key"}`, http.StatusUnauthorized)
		return ""
	}
	return key
}

func RequireAdmin(w http.ResponseWriter, r *http.Request, s *config.Settings) string {
	key := Extract(r)
	if !IsValid(key, s) {
		http.Error(w, `{"error":"invalid_api_key"}`, http.StatusUnauthorized)
		return ""
	}
	if s.WriteGuard && !IsAdmin(key, s) {
		http.Error(w, `{"error":"admin_key_required"}`, http.StatusForbidden)
		return ""
	}
	return key
}
