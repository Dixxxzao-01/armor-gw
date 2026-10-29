#!/bin/bash
# armor-gw 一键部署脚本（Linux 服务器版）
# 用法: bash deploy.sh
# 可选环境变量: GW_DIR（项目根目录，默认脚本上级目录）
set -e
GW_DIR="${GW_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$GW_DIR"

echo "═══ armor-gw 部署开始 ═══"
echo "项目目录: $GW_DIR"
echo "[1/6] 系统探测"
if [ -f /etc/os-release ]; then . /etc/os-release; fi
echo "    系统: ${PRETTY_NAME:-unknown}"
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
    echo "    安装 python3 ..."
    if command -v yum >/dev/null 2>&1; then yum install -y python3 python3-pip
    elif command -v apt >/dev/null 2>&1; then apt update && apt install -y python3 python3-pip
    elif command -v dnf >/dev/null 2>&1; then dnf install -y python3 python3-pip
    fi
    PY=$(command -v python3)
fi
echo "    Python: $($PY --version 2>&1)"

echo "[2/6] 安装依赖"
$PY -m pip install --upgrade pip -q 2>/dev/null || true
$PY -m pip install -q fastapi "uvicorn[standard]" httpx pydantic 2>&1 | tail -1 || \
$PY -m pip install fastapi "uvicorn[standard]" httpx pydantic

echo "[3/6] 防火墙放行 8787"
if command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --add-port=8787/tcp --permanent >/dev/null 2>&1 && firewall-cmd --reload >/dev/null 2>&1 && echo "    firewalld 已放行" || true
elif command -v ufw >/dev/null 2>&1; then
    ufw allow 8787/tcp >/dev/null 2>&1 && echo "    ufw 已放行" || true
elif command -v iptables >/dev/null 2>&1; then
    iptables -I INPUT -p tcp --dport 8787 -j ACCEPT 2>/dev/null && echo "    iptables 已放行" || true
fi
# SELinux 宽松处理（centos）
setenforce 0 >/dev/null 2>&1 || true

echo "[4/6] 停旧进程"
systemctl stop armor-gw >/dev/null 2>&1 || true
pkill -f "uvicorn app.main" >/dev/null 2>&1 || true
sleep 1

echo "[5/6] 注册 systemd 服务（自启动+崩溃自动拉起）"
cat > /etc/systemd/system/armor-gw.service <<'EOF'
[Unit]
Description=armor-gw LLM gateway
After=network.target

[Service]
Type=simple
WorkingDirectory=$GW_DIR
EnvironmentFile="$GW_DIR"/.env
ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8787
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
# uvicorn 路径兜底（venv/自定义 python）
UVPATH=$($PY -c "import uvicorn, os; print(os.path.dirname(uvicorn.__file__))" 2>/dev/null || true)
if [ -n "$UVPATH" ]; then
    PYBIN=$(dirname "$PY")
    sed -i "s|ExecStart=.*|ExecStart=$PYBIN/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8787|" /etc/systemd/system/armor-gw.service
fi
systemctl daemon-reload
systemctl enable armor-gw >/dev/null 2>&1
systemctl start armor-gw
sleep 3

echo "[6/6] 健康检查"
for i in 1 2 3 4 5; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 4 http://127.0.0.1:8787/health || true)
    if [ "$CODE" = "200" ]; then break; fi
    sleep 3
done
if [ "$CODE" = "200" ]; then
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    echo ""
    echo "════════════════════════════════════════"
    echo "  部署成功 ✓"
    echo "  控制面板: http://$IP:8787/panel"
    echo "  网关 API: http://$IP:8787/v1/chat/completions"
    echo "  管理密钥: 见 "$GW_DIR"/.env 的 GW_KEYS"
    echo "════════════════════════════════════════"
    curl -s http://127.0.0.1:8787/ | head -c 300; echo
else
    echo "  健康检查失败（$CODE），查日志: journalctl -u armor-gw -n 50"
    exit 1
fi
