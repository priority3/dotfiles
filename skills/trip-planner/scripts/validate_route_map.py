#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_route_map.py — 验证 inject_route.py 生成的行程地图 HTML。

在上游 validate_map.py 的 7 项检查之上，增加 4 项路线检查。

用法:
  python3 validate_route_map.py <map.html> [--verbose]
  python3 validate_route_map.py <目录>     [--verbose]   # 批量

基础检查:
  1. 文件存在且非空
  2. 无未替换的模板占位符
  3. 中心坐标不是北京回退(有地点时)
  4. 地点坐标齐备
  5. 无 NaN 坐标
  6. 坐标在中国范围内(lat 18-55, lng 73-135)

路线检查:
  7. routes 引用的地点 id 都存在
  8. 每条路线至少 2 个可定位站点(否则画不出连线)
  9. day 编号不重复
 10. places 的 day/order 与 routes.stops 顺序一致

退出码: 0=通过, 1=有警告(可交付), 2=有失败(需修复)
"""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

LAT_RANGE = (18, 55)
LNG_RANGE = (73, 135)


def _strip_js_comments(text):
    """剥离 JS 行注释，跳过字符串字面量内部。

    Reason: 直接 re.sub(r'//.*') 会把 note 里的 "https://..." 拦腰截断，
    导致本可解析的 TRIP_DATA 解析失败。
    """
    out = []
    i, n = 0, len(text)
    quote = None
    while i < n:
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:      # 转义字符整体保留
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":   # 丢弃到行尾
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _extract_object(text, start):
    """从 start 处的 '{' 开始做括号配平，返回完整对象字面量。"""
    depth, i, n = 0, start, len(text)
    quote = None
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return None


def extract_trip_data(html_path):
    """从 HTML 提取 TRIP_DATA。返回 (data|None, error|None, content)。"""
    with open(html_path, encoding="utf-8") as fp:
        content = fp.read()

    match = re.search(r"const\s+TRIP_DATA\s*=\s*\{", content)
    if not match:
        return None, "未找到 TRIP_DATA 定义", content

    raw = _extract_object(content, match.end() - 1)
    if raw is None:
        return None, "TRIP_DATA 花括号不配平", content

    raw = _strip_js_comments(raw)
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*]", "]", raw)
    raw = re.sub(r"(?<=[{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'"\1":', raw)
    try:
        return json.loads(raw), None, content
    except json.JSONDecodeError as exc:
        return None, f"TRIP_DATA 不是合法 JSON: {exc}", content


def _valid(place):
    lat, lng = place.get("lat"), place.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return False
    if lat != lat or lng != lng:  # NaN
        return False
    return LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]


class Report:
    """收集检查结果，统一决定退出码。"""

    def __init__(self):
        self.code = 0

    def ok(self, msg):
        print(f"  ✅ {msg}")

    def warn(self, msg):
        print(f"  ⚠️  {msg}")
        self.code = max(self.code, 1)

    def fail(self, msg):
        print(f"  ❌ {msg}")
        self.code = 2

    def check(self, condition, msg, hard=True):
        if condition:
            self.ok(msg)
        elif hard:
            self.fail(msg)
        else:
            self.warn(msg)


def validate(html_path, verbose=False):
    print(f"\n🔍 验证: {os.path.basename(html_path)}")
    print("-" * 56)
    report = Report()

    if not os.path.exists(html_path):
        print("  ❌ 文件不存在")
        return 2
    size = os.path.getsize(html_path)
    report.check(size > 0, f"文件大小 {size} bytes")

    data, err, content = extract_trip_data(html_path)
    if data is None:
        print(f"  ❌ {err}")
        return 2

    places = data.get("places", [])
    routes = data.get("routes", [])
    center = data.get("center", [None, None])
    total = len(places)

    report.check(not re.search(r"\{\{.*?\}\}", content), "无未替换的模板占位符")

    clng, clat = (center + [None, None])[:2]
    if isinstance(clng, (int, float)) and isinstance(clat, (int, float)):
        is_beijing = abs(clng - 116.4) < 0.5 and abs(clat - 39.9) < 0.5
        report.check(not (is_beijing and total > 0),
                     f"中心 ({clng:.3f}, {clat:.3f}) 非北京回退", hard=False)
    else:
        report.warn("中心坐标缺失")

    geocoded = sum(1 for p in places if _valid(p))
    report.check(geocoded == total, f"坐标 {geocoded}/{total} 已编码", hard=False)

    nan_count = sum(
        1 for p in places
        for v in (p.get("lat"), p.get("lng"))
        if isinstance(v, float) and v != v
    )
    report.check(nan_count == 0, f"无 NaN 坐标（发现 {nan_count}）")

    out_of_range = []
    for place in places:
        lat, lng = place.get("lat"), place.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)) and lat == lat:
            if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]):
                out_of_range.append(f"{place.get('name')} ({lat:.3f}, {lng:.3f})")
    report.check(not out_of_range, f"坐标在中国范围内（超出 {len(out_of_range)}）")
    if out_of_range and verbose:
        for item in out_of_range:
            print(f"       {item}")

    # ---------- 路线检查 ----------
    print("  " + "·" * 40)
    if not routes:
        report.ok("散点模式（无 routes，跳过路线检查）")
    else:
        index = {str(p.get("id")): p for p in places}

        missing = [
            (r.get("day"), sid)
            for r in routes for sid in r.get("stops", [])
            if str(sid) not in index
        ]
        report.check(not missing, f"路线站点引用完整（缺失 {len(missing)}）")
        if missing and verbose:
            for day, sid in missing:
                print(f"       Day {day} → 不存在的 id「{sid}」")

        thin = []
        for route in routes:
            located = sum(
                1 for sid in route.get("stops", [])
                if str(sid) in index and _valid(index[str(sid)])
            )
            if located < 2:
                thin.append(f"Day {route.get('day')}（{located} 站可定位）")
        report.check(not thin, f"每条路线可连线（不足 2 站的：{len(thin)}）", hard=False)
        if thin and verbose:
            for item in thin:
                print(f"       {item}")

        days = [r.get("day") for r in routes]
        report.check(len(days) == len(set(days)), f"day 编号不重复（{days}）")

        # 一个地点可能被多天引用（酒店、换乘站）。inject_route.py 取首次引用为归属，
        # 因此只要 place 的 (day, order) 命中它的任意一次引用即视为一致。
        refs = {}
        for route in routes:
            for order, sid in enumerate(route.get("stops", []), start=1):
                refs.setdefault(str(sid), []).append((route.get("day"), order))

        mismatched, shared = [], []
        for sid, occurrences in refs.items():
            place = index.get(sid)
            if place is None:
                continue
            actual = (place.get("day"), place.get("order"))
            if len(occurrences) > 1:
                shared.append(f"{place.get('name')}: 被 Day {[d for d, _ in occurrences]} 经过，归属 Day {actual[0]}")
            if actual not in occurrences:
                mismatched.append(
                    f"{place.get('name')}: places 记 day={actual[0]}/order={actual[1]}，"
                    f"routes 中的引用为 {occurrences}"
                )
        report.check(not mismatched, f"places 与 routes 站序一致（不一致 {len(mismatched)}）", hard=False)
        if mismatched and verbose:
            for item in mismatched:
                print(f"       {item}")
        if shared:
            report.ok(f"多天共用站点 {len(shared)} 个（已归属首次经过的那天）")
            if verbose:
                for item in shared:
                    print(f"       {item}")

    # ---------- 概览 ----------
    print("  " + "·" * 40)
    print(f"  📊 地点 {total} 个 / 已定位 {geocoded}")
    if routes:
        stop_total = sum(len(r.get("stops", [])) for r in routes)
        print(f"  🧭 路线 {len(routes)} 条 / 站点 {stop_total} 个 / Day {sorted(d for d in (r.get('day') for r in routes) if d)}")
        for route in routes:
            bits = [f"Day {route.get('day')}"]
            if route.get("name"):
                bits.append(str(route["name"]))
            bits.append(f"{len(route.get('stops', []))} 站")
            if route.get("cost"):
                bits.append(f"¥{route['cost']}")
            print(f"       {' · '.join(bits)}")
    print(f"  🎯 中心 ({clng}, {clat}) zoom={data.get('zoom', '?')}")
    print(f"  📅 日期 {data.get('date_range', '?')}")

    if report.code == 0:
        print("  ✅ 全部通过\n")
    elif report.code == 1:
        print("  ⚠️  有警告（可交付）\n")
    else:
        print("  ❌ 有失败（需修复）\n")
    return report.code


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    if not args:
        print("用法: python3 validate_route_map.py <map.html|目录> [--verbose]")
        return 1

    path = args[0]
    if os.path.isdir(path):
        htmls = sorted(f for f in os.listdir(path) if f.endswith(".html"))
        if not htmls:
            print(f"在 {path} 下未找到 HTML 文件")
            return 1
        return max(validate(os.path.join(path, h), verbose) for h in htmls)
    return validate(path, verbose)


if __name__ == "__main__":
    sys.exit(main())
