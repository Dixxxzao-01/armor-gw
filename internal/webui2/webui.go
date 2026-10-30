// Package webui: 嵌入式面板（embed 进二进制——Go 版零文件依赖部署）
package webui

import (
	_ "embed"
	"net/http"
)

//go:embed index.html
var panelHTML []byte

// Register: 挂 /panel（HTML 永不缓存）
func Register(mux *http.ServeMux) {
	mux.HandleFunc("GET /panel", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Header().Set("Cache-Control", "no-store")
		_, _ = w.Write(panelHTML)
	})
}
