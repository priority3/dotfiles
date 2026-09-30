#!/usr/bin/env bash
# tc_query.sh — 同程程心 CLI 的调用封装。
#
# 负责三件上游 SKILL.md 要求、但每次调用都得重复的事：
#   1. 注入 CHENGXIN_API_KEY（从 tc-chengxin token 取，不让用户手输）
#   2. 注入 CHENGXIN_WORKBUDDY_OUTPUT_DIR 与 CHENGXIN_OUTPUT_GUARD=display_contract
#   3. 从 stdout 的 VISUAL_JSON 块里取出结果
#
# 用法：
#   bash tc_query.sh <类型> [查询参数...] [输出选项]
#
# 类型：flight | train | bus | hotel | scenery | traffic | travel
#
# 查询参数（透传给底层 *-query.js）：
#   --departure <城市>     出发地
#   --destination <城市>   目的地
#   --extra "<修饰需求>"   日期、人数、星级、偏好等，务必完整保留用户原话
#
# 输出选项（本封装消费，不透传）：
#   --out <目录>    HTML 产物目录，默认 $PWD/outputs
#   --markdown      只输出 markdown 原文（用于直接呈现给用户）
#   --prices        输出结构化报价 JSON（用于预算计算）
#   --summary       只输出元信息
#   --save <前缀>   同时把 raw/markdown/prices 落盘到 <前缀>.*
#   --raw           输出完整 JSON（默认）
#
# 示例：
#   bash tc_query.sh traffic --departure 上海 --destination 成都 --extra "10月1日 2人"
#   bash tc_query.sh hotel --destination 成都 --extra "春熙路附近 10月1日入住 2晚" --prices

set -uo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
# Reason: source 会把本脚本的位置参数传给 paths.sh，显式传空串避免它误当作 --check 之类的子命令。
# shellcheck source=paths.sh
. "$SELF_DIR/paths.sh" ""

VALID_TYPES="flight train bus hotel scenery traffic travel"

die() { printf '❌ %s\n' "$1" >&2; exit "${2:-1}"; }

usage() { sed -n '/^# 用法：/,/^$/p' "$0" | sed 's/^# \{0,1\}//'; }

[ $# -ge 1 ] || { usage; exit 1; }

QTYPE="$1"; shift
case "$QTYPE" in
    -h|--help) usage; exit 0 ;;
esac
case " $VALID_TYPES " in
    *" $QTYPE "*) ;;
    # Reason: 变量后紧跟全角标点时必须用 ${} 界定，否则 bash 会把标点并入变量名。
    *) die "未知类型「${QTYPE}」，可选：${VALID_TYPES}" ;;
esac

# ---------- 分离本封装的选项与透传给 CLI 的参数 ----------
OUT_DIR=""; MODE="raw"; SAVE_PREFIX=""
PASS_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --out)      OUT_DIR="${2:-}"; shift 2 ;;
        --save)     SAVE_PREFIX="${2:-}"; shift 2 ;;
        --markdown) MODE="markdown"; shift ;;
        --prices)   MODE="prices"; shift ;;
        --summary)  MODE="summary"; shift ;;
        --raw)      MODE="raw"; shift ;;
        *)          PASS_ARGS+=("$1"); shift ;;
    esac
done

# ---------- 依赖与凭证 ----------
[ -n "${NODE:-}" ] || die "未找到 node，无法执行同程查询脚本"
QUERY_JS="$TC_SKILL/scripts/${QTYPE}-query.js"
[ -f "$QUERY_JS" ] || die "查询脚本不存在：${QUERY_JS}（确认 WorkBuddy 已安装「同程程心」连接器）"

# --help 直接透传，无需 token
case " ${PASS_ARGS[*]:-} " in
    *" --help "*|*" -h "*) exec "$NODE" "$QUERY_JS" --help ;;
esac

TOKEN="$("$TC_BIN" token 2>/dev/null | head -1)"
[ -n "$TOKEN" ] || die "取不到同程令牌 —— 请打开 WorkBuddy →「连应用」→ 重新连接「同程旅行」" 4

OUT_DIR="${OUT_DIR:-${OUTPUT_DIR:-$PWD/outputs}}"
mkdir -p "$OUT_DIR" || die "无法创建输出目录：${OUT_DIR}"

export CHENGXIN_API_KEY="$TOKEN"
export CHENGXIN_WORKBUDDY_OUTPUT_DIR="$OUT_DIR"
export CHENGXIN_OUTPUT_GUARD=display_contract

# ---------- 执行 ----------
RAW_FILE="$(mktemp)"; ERR_FILE="$(mktemp)"
trap 'rm -f "$RAW_FILE" "$ERR_FILE"' EXIT

"$NODE" "$QUERY_JS" ${PASS_ARGS[@]+"${PASS_ARGS[@]}"} >"$RAW_FILE" 2>"$ERR_FILE"
STATUS=$?

if [ "$STATUS" -ne 0 ]; then
    printf '❌ 同程 %s 查询失败（exit=%s）\n' "$QTYPE" "$STATUS" >&2
    head -20 "$ERR_FILE" >&2
    exit "$STATUS"
fi

# Reason: 用函数而非字符串拼命令，路径含空格时才不会被 word splitting 拆散。
extract() { "$PY" "$SELF_DIR/extract_visual_json.py" --input "$RAW_FILE" "$@"; }

# ---------- 落盘（可选） ----------
if [ -n "$SAVE_PREFIX" ]; then
    mkdir -p "$(dirname "$SAVE_PREFIX")"
    cp "$RAW_FILE" "${SAVE_PREFIX}.raw.txt"
    extract --field markdown > "${SAVE_PREFIX}.md" 2>/dev/null || true
    extract --prices         > "${SAVE_PREFIX}.prices.json" 2>/dev/null || true
    printf '💾 已保存：%s.{raw.txt,md,prices.json}\n' "$SAVE_PREFIX" >&2
fi

# ---------- 输出 ----------
case "$MODE" in
    markdown) extract --field markdown ;;
    prices)   extract --prices ;;
    summary)  extract --summary ;;
    *)        extract ;;
esac
