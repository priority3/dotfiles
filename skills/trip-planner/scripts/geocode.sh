#!/usr/bin/env bash
# geocode.sh — 上游 geocode.py 的格式适配包装。
#
# 上游 weekend-city-trip 的 geocode.py 只接受**纯数组**的 places.json，
# 但它自己的文档里写的是 {"city":..., "places":[...]} 对象格式 —— 文档与代码
# 不一致，直接按文档写会报 "string indices must be integers"。
#
# 本包装同时接受两种格式：对象格式会先抽出 places 数组，跑完再把产物放回
# 调用方预期的 <输入名>.geo.json 路径，并可从对象的 city 字段自动取城市名。
#
# 用法:
#   bash geocode.sh <places.json> [城市名]
#
# 输出:
#   <places 去扩展名>.geo.json

set -uo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=paths.sh
. "$SELF_DIR/paths.sh" ""

die() { printf '❌ %s\n' "$1" >&2; exit "${2:-1}"; }

[ $# -ge 1 ] || die "用法: bash geocode.sh <places.json> [城市名]"
IN="$1"
CITY="${2:-}"

[ -f "$IN" ] || die "文件不存在：${IN}"
[ -n "${PY:-}" ] || die "未找到 python3"
UPSTREAM="$WCT/scripts/geocode.py"
[ -f "$UPSTREAM" ] || die "上游 geocode.py 不存在：${UPSTREAM}（确认已安装 weekend-city-trip）"

if [ -z "${AMAP_KEY:-}" ]; then
    die "缺少 AMAP_KEY（高德「Web 服务」类型 Key），无法地理编码。
   配置：编辑 $SKILL_DIR/.env
   申请：https://console.amap.com/dev/key/app（应用类型选「Web 服务」）" 2
fi

BASE="${IN%.json}"
FINAL="${BASE}.geo.json"

# 规范化：对象格式抽出 places；顺便回填 city。输出 "<临时文件路径>\t<city>"
NORM_INFO="$("$PY" - "$IN" "$CITY" <<'PY'
import json, os, sys, tempfile

in_path, cli_city = sys.argv[1], sys.argv[2]
with open(in_path, encoding="utf-8") as fp:
    data = json.load(fp)

city = cli_city
if isinstance(data, dict):
    places = data.get("places", [])
    city = city or data.get("city", "")
elif isinstance(data, list):
    places = data
else:
    print("ERR\t输入既不是数组也不是对象", end="")
    raise SystemExit(1)

if not isinstance(places, list):
    print("ERR\tplaces 不是数组", end="")
    raise SystemExit(1)
bad = [i for i, p in enumerate(places) if not isinstance(p, dict) or not p.get("name")]
if bad:
    print(f"ERR\t第 {bad[:5]} 项缺少 name 字段", end="")
    raise SystemExit(1)

# 已是纯数组则直接用原文件，避免多一次拷贝
if isinstance(data, list):
    print(f"{in_path}\t{city}", end="")
else:
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(places, tmp, ensure_ascii=False)
    tmp.close()
    print(f"{tmp.name}\t{city}", end="")
PY
)" || die "输入解析失败：${NORM_INFO#ERR	}"

NORM_PATH="${NORM_INFO%%	*}"
CITY="${NORM_INFO##*	}"
case "$NORM_PATH" in ERR*) die "输入格式错误：${CITY}" ;; esac

if [ "$NORM_PATH" != "$IN" ]; then
    # Reason: 走了临时文件时，上游会打印临时路径作为「输出」，对调用方毫无意义
    # 且与稍后打印的真实路径冲突，故过滤掉，由本脚本统一报告最终位置。
    "$PY" "$UPSTREAM" "$NORM_PATH" "$CITY" | grep -v '^📁 输出:'
    STATUS=${PIPESTATUS[0]}
else
    "$PY" "$UPSTREAM" "$NORM_PATH" "$CITY"
    STATUS=$?
fi

# 上游把结果写到 <规范化输入去扩展名>.geo.json，若走了临时文件需搬回预期位置
NORM_OUT="${NORM_PATH%.json}.geo.json"
if [ "$NORM_OUT" != "$FINAL" ]; then
    if [ -f "$NORM_OUT" ]; then
        mv "$NORM_OUT" "$FINAL"
        printf '📁 输出: %s\n' "$FINAL"
    fi
    [ "$NORM_PATH" != "$IN" ] && rm -f "$NORM_PATH"
fi

exit "$STATUS"
