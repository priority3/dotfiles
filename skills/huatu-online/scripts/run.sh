#!/usr/bin/env bash
# 华图在线刷题数据抓取：解密 cookie → 启动无头 Chrome → 抓取 → 输出 JSON
# 用法：./run.sh [progress|report|records|errors|all]   默认 all
set -uo pipefail

MODE="${1:-all}"
DIR="$(cd "$(dirname "$0")" && pwd)"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT="${HUATU_CDP_PORT:-9231}"
PROFILE="/tmp/huatu-skill-profile"

if [ ! -x "$CHROME" ]; then
  echo "找不到 Chrome：$CHROME" >&2
  exit 1
fi

python3 "$DIR/huatu_cookies.py" >&2 || { echo "cookie 解密失败，先确认浏览器里登录着华图在线" >&2; exit 2; }

# 端口占用就先清掉旧实例
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  lsof -ti:"$PORT" | xargs kill -9 2>/dev/null || true
  sleep 1
fi

rm -rf "$PROFILE"
"$CHROME" --headless=new --disable-gpu --no-sandbox \
  --remote-debugging-port="$PORT" --user-data-dir="$PROFILE" about:blank >/dev/null 2>&1 &
CPID=$!
cleanup() { kill "$CPID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 24); do
  if curl -s --noproxy '*' "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

if [ "$MODE" = "detail" ]; then
  CDP_PORT="$PORT" node "$DIR/huatu_detail.js" "${2:-6}"
elif [ "$MODE" = "wrongs" ]; then
  CDP_PORT="$PORT" node "$DIR/huatu_wrongs.js" "${2:-12}"
else
  CDP_PORT="$PORT" node "$DIR/huatu_fetch.js" "$MODE"
fi
