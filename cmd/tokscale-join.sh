#!/usr/bin/env bash
# tokscale-join.sh — 一键把当前电脑接入 token.razet.me 的 AI 用量统计
#
# 用法:
#   ./tokscale-join.sh                  # 全自动：主机名当用户名，经 SSH 自动发号
#   ./tokscale-join.sh --user NAME      # 指定用户名（面板上显示的账号名）
#   ./tokscale-join.sh --token tt_...   # 已有 token 时直接用，跳过发号
#
# 发 token 的三个途径（按优先级）:
#   1. --token 参数
#   2. 本机 ~/.tokscale-hub/env 里已有的 token（重复执行直接复用）
#   3. ssh tencent-cvm 到服务器自动注册新用户并发号（需要 dotfiles 已同步 ssh 配置）
#   4. 都不行就交互提示粘贴 token
#
# 本仓库是公开的，脚本里没有任何密钥。
# 面板地址: https://token.razet.me  |  登录账号密码找管理员。
set -euo pipefail

HUB="https://token.razet.me"
TS_HOME="$HOME/.tokscale-hub"
SSH_HOST="tencent-cvm"

USER_NAME=""
GIVEN_TOKEN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --user)  USER_NAME="${2:?--user 需要一个名字}"; shift 2 ;;
    --token) GIVEN_TOKEN="${2:?--token 需要一个 tt_ 开头的值}"; shift 2 ;;
    -h|--help) grep '^#' "$0" | head -16; exit 0 ;;
    *) echo "未知参数: $1（--help 看用法）" >&2; exit 2 ;;
  esac
done

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[失败]\033[0m %s\n' "$*" >&2; exit 1; }

# ── 1. 用户名：默认取主机名，清洗成合法 username（列宽 39，唯一约束在小写形式上） ──
if [ -z "$USER_NAME" ]; then
  USER_NAME="$(hostname -s | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//' | cut -c1-39)"
fi
[ -n "$USER_NAME" ] || die "无法从主机名推导用户名，请用 --user 指定"
DEVICE_NAME="$(hostname -s)"

# ── 2. 拿 token ──
TOKEN="$GIVEN_TOKEN"
if [ -z "$TOKEN" ] && [ -f "$TS_HOME/env" ]; then
  TOKEN="$(sed -n 's/^TOKSCALE_API_TOKEN="\(.*\)"$/\1/p' "$TS_HOME/env" || true)"
  [ -n "$TOKEN" ] && say "复用已有 token（$TS_HOME/env）"
fi
if [ -z "$TOKEN" ]; then
  say "尝试经 $SSH_HOST 自动发号（用户: ${USER_NAME}）"
  if ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_HOST" true 2>/dev/null; then
    TOKEN="$(ssh -o BatchMode=yes "$SSH_HOST" "/opt/tokscale-ops/bootstrap-user.sh '$USER_NAME' '$USER_NAME'")" \
      || die "服务器发号失败"
    [ -n "$TOKEN" ] || die "服务器返回了空 token"
  else
    printf '无法 SSH 到服务器。粘贴管理员发的 tt_ 开头 token: '
    read -r TOKEN
    [ -n "$TOKEN" ] || die "没有 token 无法继续"
  fi
fi
case "$TOKEN" in tt_*) ;; *) die "token 应以 tt_ 开头，当前: ${TOKEN%%_*}..." ;; esac

# ── 3. 验证 token ──
say "验证 token"
RESP="$(curl -sS --max-time 15 -H "Authorization: Bearer $TOKEN" "$HUB/api/auth/token" || true)"
echo "$RESP" | grep -q '"username"' || die "token 校验失败: $RESP"
echo "    $RESP"

# ── 4. 安装 CLI（独立目录，不污染全局） ──
say "安装 tokscale CLI"
command -v node >/dev/null 2>&1 || die "未找到 node（需要 Node.js 20+）"
mkdir -p "$TS_HOME/pkg"
if [ ! -x "$TS_HOME/pkg/node_modules/.bin/tokscale" ]; then
  (cd "$TS_HOME/pkg" && npm install --no-fund --no-audit tokscale@latest >/dev/null 2>&1) \
    || die "npm install tokscale 失败"
fi
BIN="$TS_HOME/pkg/node_modules/.bin/tokscale"
[ -x "$BIN" ] || die "安装后仍未找到 $BIN"

# ── 5. 写配置和同步脚本 ──
say "写入配置（${TS_HOME}）"
mkdir -p "$TS_HOME"
umask 077
cat > "$TS_HOME/env" <<EOF
export TOKSCALE_API_URL="$HUB"
export TOKSCALE_API_TOKEN="$TOKEN"
export TOKSCALE_DEVICE_NAME="$DEVICE_NAME"
EOF
cat > "$TS_HOME/sync.sh" <<'SYNC'
#!/bin/bash
# 定时上报本机用量。关键：显式 export TOKSCALE_API_URL，
# 避免 submit 退回默认的 tokscale.ai（会把私有用量交到公开排行榜）
set -uo pipefail
# PATH 里放通配符不会展开，逐个探测可用的 node
for d in "$HOME"/.nvm/versions/node/*/bin "$HOME"/.workbuddy/binaries/node/versions/*/bin \
         "$HOME/.local/share/mise/shims" /opt/homebrew/bin /usr/local/bin; do
  if [ -x "$d/node" ]; then export PATH="$d:$PATH"; break; fi
done

LOCK="$HOME/.tokscale-hub/.sync.lock"
_lm=$(stat -f %m "$LOCK" 2>/dev/null || stat -c %Y "$LOCK" 2>/dev/null || echo 0)
if ! mkdir "$LOCK" 2>/dev/null; then
  # 上次异常中断（合盖/被杀）留下的陈旧锁，超过 30 分钟就回收；否则静默跳过
  [ $(( $(date +%s) - _lm )) -gt 1800 ] && rmdir "$LOCK" 2>/dev/null
  mkdir "$LOCK" 2>/dev/null || exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# shellcheck disable=SC1090
. "$HOME/.tokscale-hub/env"
BIN="$HOME/.tokscale-hub/pkg/node_modules/.bin/tokscale"
LOG="$HOME/.tokscale-hub/sync.log"

SIZE="$(stat -f%z "$LOG" 2>/dev/null || stat -c%s "$LOG" 2>/dev/null || echo 0)"
[ "${SIZE:-0}" -gt 1048576 ] && mv -f "$LOG" "$LOG.1"

{ echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="; } >>"$LOG"
"$BIN" submit >>"$LOG" 2>&1
echo "exit=$?" >>"$LOG"
SYNC
chmod 700 "$TS_HOME/sync.sh"

# ── 6. zshrc 保底钩子（开终端时距上次 >6h 就后台同步一次；有标记位，幂等） ──
ZRC="$HOME/.zshrc"
if [ -f "$ZRC" ] && ! grep -q ">>> tokscale-hub" "$ZRC"; then
  say "添加 zshrc 钩子"
  cat >> "$ZRC" <<'HOOK'

# >>> tokscale-hub 用量同步 >>>
if [ -x "$HOME/.tokscale-hub/sync.sh" ]; then
  _ts_last=$(stat -f %m "$HOME/.tokscale-hub/sync.log" 2>/dev/null || stat -c %Y "$HOME/.tokscale-hub/sync.log" 2>/dev/null || echo 0)
  if [ $(( $(date +%s) - _ts_last )) -gt 21600 ]; then
    ( "$HOME/.tokscale-hub/sync.sh" >/dev/null 2>&1 & )
  fi
  unset _ts_last
fi
# <<< tokscale-hub 用量同步 <<<
HOOK
fi

# ── 6b. 生成「后台定时」安装器（macOS launchd / Linux cron，手动执行一次即可） ──
cat > "$TS_HOME/activate-timer.command" <<'ACT'
#!/bin/bash
# 双击执行（或在终端里 bash 这个文件），把上报挂到系统定时器上。
# macOS: launchd，每 4 小时一次；Linux: crontab，每 4 小时一次。
set -uo pipefail
TS_HOME="$HOME/.tokscale-hub"
[ -x "$TS_HOME/sync.sh" ] || { echo "找不到 $TS_HOME/sync.sh，先跑 tokscale-join.sh"; exit 1; }
chmod +x "$TS_HOME/sync.sh"

if [ "$(uname)" = "Darwin" ]; then
  PLIST="$HOME/Library/LaunchAgents/me.razet.tokscale-sync.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat >"$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>me.razet.tokscale-sync</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$TS_HOME/sync.sh</string></array>
  <key>StartInterval</key><integer>14400</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$TS_HOME/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$TS_HOME/launchd.err.log</string>
</dict></plist>
PLISTEOF
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null
  launchctl bootstrap "gui/$(id -u)" "$PLIST" && echo "已启动定时器（每 4 小时）: $PLIST"
else
  ( crontab -l 2>/dev/null | grep -v 'tokscale-hub/sync.sh'; echo "17 */4 * * * $TS_HOME/sync.sh" ) | crontab -
  crontab -l | grep tokscale-hub
fi
ACT
chmod 700 "$TS_HOME/activate-timer.command"

# ── 7. 首次上报 ──
say "首次上报（约 1 分钟，取决于本地会话数量）"
"$TS_HOME/sync.sh" || true
tail -4 "$TS_HOME/sync.log"

cat <<EOF

────────────────────────────────────────────────
完成。用户: $USER_NAME  设备: $DEVICE_NAME
面板: $HUB/u/$USER_NAME  （登录账号密码找管理员）
日志: $TS_HOME/sync.log

之后：开终端会自动同步（距上次 >6h 才触发）。
想要系统级每 4 小时定时，执行一次：
  bash $TS_HOME/activate-timer.command
────────────────────────────────────────────────
EOF
