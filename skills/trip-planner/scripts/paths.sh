#!/usr/bin/env bash
# paths.sh — trip-planner 的依赖路径解析与自检（宿主兼容层）
#
# 本 skill 不复制上游代码，而是按绝对路径复用两个已安装的 WorkBuddy skill。
# 这些路径在 WorkBuddy 与 Claude Code 两个宿主里可见性不同，故收敛到此单点。
#
# 用法：
#   source paths.sh          # 提供 TC_BIN / TC_SKILL / WCT / PY / NODE 等变量
#   bash   paths.sh --check  # 自检依赖与密钥，人类可读报告
#
# 兼容性：本文件同时被 bash 与 zsh source（Claude Code 的默认 shell 是 zsh），
# 因此不使用 ${!var} 间接展开等 bash 专有语法。
#
# 导出变量：
#   SKILL_DIR  本 skill 根目录
#   TC_BIN     同程 CLI（取 token 用）
#   TC_SKILL   同程 skill 目录（七类 *-query.js 所在）
#   WCT        weekend-city-trip skill 目录（复用 anysearch/geocode/md_to_html）
#   NODE / PY  运行时

# Reason: zsh 没有 BASH_SOURCE，source 时须回退到 $0 才能定位到本文件。
if [ -n "${BASH_VERSION:-}" ]; then
    _tp_self="${BASH_SOURCE[0]}"
else
    _tp_self="$0"
fi
SKILL_DIR="$(cd "$(dirname "$_tp_self")/.." && pwd)"
export SKILL_DIR

# ---------- .env 加载 ----------
# Reason: 与上游 inject.py 的行为对齐（skill 目录优先、已存在的环境变量不覆盖），
# 这样用户在 shell 里临时 export 的 key 始终优先于 .env 里的旧值。
_load_dotenv() {
    local f k v line
    for f in "$SKILL_DIR/.env" "$PWD/.env"; do
        [ -f "$f" ] || continue
        while IFS= read -r line || [ -n "$line" ]; do
            case "$line" in ''|'#'*) continue ;; esac
            case "$line" in *=*) ;; *) continue ;; esac
            k="${line%%=*}"; v="${line#*=}"
            k="$(printf '%s' "$k" | tr -d '[:space:]')"
            v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
            # Reason: printenv 代替 bash 专有的 ${!k}，兼容 zsh。
            [ -n "$k" ] && [ -z "$(printenv "$k" 2>/dev/null)" ] && export "$k=$v"
        done < "$f"
    done
}
_load_dotenv

# ---------- 同程程心 ----------
# WorkBuddy 内 tc-chengxin 在 PATH 里；Claude Code 内不在，回退到已知安装路径。
TC_BIN="$(command -v tc-chengxin 2>/dev/null)"
[ -z "$TC_BIN" ] && TC_BIN="$HOME/.workbuddy/binaries/node/cli-connector-packages/bin/tc-chengxin"
export TC_BIN

# 优先「已安装」目录；marketplace 目录只是市场缓存，作为回退。
for _cand in \
    "$HOME/.workbuddy/connectors/skills/connector-tc-chengxin" \
    "$HOME/.workbuddy/connectors-marketplace/connectors/tc-chengxin/skills"
do
    [ -d "$_cand/scripts" ] && { TC_SKILL="$_cand"; break; }
done
export TC_SKILL="${TC_SKILL:-}"

# ---------- weekend-city-trip ----------
# 目录名带 skillhub 后缀，且后缀可能随安装源变化，故先精确匹配再 glob 兜底。
WCT="$HOME/.workbuddy/skills/weekend-city-trip__skillhub"
if [ ! -d "$WCT/scripts" ]; then
    for _cand in "$HOME"/.workbuddy/skills/weekend-city-trip*; do
        [ -d "$_cand/scripts" ] && { WCT="$_cand"; break; }
    done
fi
export WCT

# ---------- 运行时 ----------
NODE="$(command -v node 2>/dev/null)"
PY="$(command -v python3 2>/dev/null || command -v python 2>/dev/null)"
export NODE PY

# ---------- 自检 ----------
tp_check() {
    local fail=0 warn=0
    echo "trip-planner 依赖自检"
    echo "===================="

    _ok()   { printf '  ✅ %s · %s\n' "$1" "$2"; }
    _bad()  { printf '  ❌ %s · %s\n' "$1" "$2"; fail=$((fail+1)); }
    _warn() { printf '  ⚠️  %s · %s\n' "$1" "$2"; warn=$((warn+1)); }

    echo "[运行时]"
    [ -n "$NODE" ] && _ok "node" "$($NODE -v 2>/dev/null)" || _bad "node" "未找到，同程查询不可用"
    [ -n "$PY" ]   && _ok "python3" "$($PY -V 2>&1)"       || _bad "python3" "未找到，地图与费用脚本不可用"

    echo "[同程程心 tc-chengxin]"
    if [ -x "$TC_BIN" ] || [ -f "$TC_BIN" ]; then
        _ok "CLI" "$TC_BIN"
        local tok
        tok="$("$TC_BIN" token 2>/dev/null | head -1)"
        if [ -n "$tok" ]; then
            _ok "token" "已获取（${#tok} 字符）"
        else
            _bad "token" "取不到 —— 请在 WorkBuddy「连应用」中重新连接「同程旅行」"
        fi
    else
        _bad "CLI" "未找到：$TC_BIN"
    fi
    if [ -n "$TC_SKILL" ] && [ -d "$TC_SKILL/scripts" ]; then
        _ok "查询脚本" "$TC_SKILL/scripts"
    else
        _bad "查询脚本" "未找到同程 skill 目录"
    fi

    echo "[weekend-city-trip]"
    if [ -d "$WCT/scripts" ]; then
        _ok "skill 目录" "$WCT"
        for s in anysearch_cli.py geocode.py md_to_html.py; do
            [ -f "$WCT/scripts/$s" ] && _ok "$s" "可复用" || _warn "$s" "缺失"
        done
    else
        _bad "skill 目录" "未找到：$WCT"
    fi

    echo "[密钥]"
    # Reason: 缺 key 只警告不失败 —— 同程链路（方案比选 + 费用表）不依赖这些 key，
    # 应当允许用户在没配高德/anysearch 的情况下先跑通行程与预算部分。
    echo "  来源: $SKILL_DIR/.env"
    # 高德两类 Key 不能互通：Web 服务 Key 调 JS API 或反之都会失败，故分别检查。
    [ -n "${AMAP_KEY:-}" ]           && _ok "AMAP_KEY" "地理编码（Web 服务类型）"      || _warn "AMAP_KEY" "缺失 → 地点转不了坐标，地图无标记"
    [ -n "${AMAP_JS_KEY:-}" ]        && _ok "AMAP_JS_KEY" "底图加载（Web端 JS API）"   || _warn "AMAP_JS_KEY" "缺失 → 地图底图空白"
    [ -n "${AMAP_SECURITY:-}" ]      && _ok "AMAP_SECURITY" "JS API 安全密钥"          || _warn "AMAP_SECURITY" "缺失 → 地图底图空白"
    [ -n "${ANYSEARCH_API_KEY:-}" ]  && _ok "ANYSEARCH_API_KEY" "已配置"               || _warn "ANYSEARCH_API_KEY" "缺失 → 搜索走匿名，QPS 极低"

    echo "===================="
    if [ "$fail" -gt 0 ]; then
        echo "❌ $fail 项阻断性缺失，$warn 项警告"
        echo
        echo "修复指引："
        echo "  同程 token 失效  → 打开 WorkBuddy →「连应用」→ 重新连接「同程旅行」"
        echo "  同程 CLI 缺失    → 确认 WorkBuddy 已安装「同程程心」连接器"
        echo "  weekend 缺失     → 确认 WorkBuddy 已安装 weekend-city-trip skill"
        return 1
    fi
    if [ "$warn" -gt 0 ]; then
        echo "✅ 核心依赖就绪（$warn 项密钥警告，相关步骤会明确提示而非静默失败）"
        echo "   高德 Key 申请：https://console.amap.com/dev/key/app"
        echo "   配置：编辑 $SKILL_DIR/.env"
        return 0
    fi
    echo "✅ 全部就绪"
    return 0
}

# 带参数时执行对应动作；无参数（典型的 source 场景）只提供变量。
# Reason: 不用 BASH_SOURCE=$0 判断是否被 source —— 该技巧在 zsh 下失效。
case "${1:-}" in
    --check|check) tp_check ;;
    --print)
        echo "SKILL_DIR=$SKILL_DIR"
        echo "TC_BIN=$TC_BIN"
        echo "TC_SKILL=$TC_SKILL"
        echo "WCT=$WCT"
        echo "NODE=$NODE"
        echo "PY=$PY"
        ;;
    '') : ;;  # source 场景，静默
    *) echo "用法: bash paths.sh [--check|--print]" >&2 ;;
esac
