#!/bin/sh
# armor-gw 守护：每 30 秒检查，挂了就拉起（iSH 环境后台进程会被系统回收）
cd /root/armor-gw
while true; do
  if ! curl -s --max-time 4 -o /dev/null http://127.0.0.1:8787/health 2>/dev/null; then
    # 先清尸：杀掉可能僵住/打架的旧进程，保证单实例
    pkill -9 -f "uvicorn app.main" 2>/dev/null
    sleep 2
    set -a; . ./.env; set +a
    nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8787 > logs/gw.log 2>&1 &
    sleep 8
    # 双实例纠察：启动完成后若进程数 >1，保留最新拉起的、清掉旧尸
    N=$(ps | grep "[u]vicorn app.main" | wc -l)
    if [ "$N" -gt 1 ]; then
      NEWEST=$(ps -o pid,args | grep "[u]vicorn app.main" | tail -1 | awk '{print $1}')
      ps -o pid | grep -v PID | while read P; do
        [ "$P" != "$NEWEST" ] && kill -9 "$P" 2>/dev/null
      done
    fi
    curl -s -X PUT localhost:8787/v1/admin/policy -H "Content-Type: application/json" \
      -H "Authorization: Bearer sk-armor-test" -d '{"max_retry":8}' -o /dev/null 2>/dev/null
  fi
  sleep 30
done
