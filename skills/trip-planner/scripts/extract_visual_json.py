#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_visual_json.py — 解析同程程心 CLI 的输出。

同程的 *-query.js 把结构化结果包在 stdout 的
WORKBUDDY_VISUAL_JSON_START / WORKBUDDY_VISUAL_JSON_END 之间，其余是噪声。
本脚本负责把它取出来，并可进一步从 markdown 表格里抽出结构化报价，
供 cost_table.py 计算预算。

用法：
    node flight-query.js ... | python3 extract_visual_json.py [选项]
    python3 extract_visual_json.py --input raw.txt [选项]

选项：
    --field NAME   只输出该字段原文（markdown / adviceMarkdown / htmlFilePath ...）
    --prices       从 markdown 表格抽结构化报价，输出 JSON
    --summary      只输出元信息（条数、HTML 路径等），不含长文本
    (默认)         输出完整 JSON

设计约束：同程的输出契约要求 markdown 字段原样呈现给用户，不得改写。
因此 --prices 只做「读取」，产出独立的报价数据供预算计算，
绝不修改或重排 markdown 本身。
"""
import argparse
import json
import re
import sys

START = "WORKBUDDY_VISUAL_JSON_START"
END = "WORKBUDDY_VISUAL_JSON_END"

# 表头关键词 → 标准字段名。各业务表头不同（机票「价格」、火车「票价/席别」、
# 景区「景点」、酒店「酒店」），故做映射。匹配用「别名是表头的子串」，
# 因此「位置」能命中「位置/亮点」，但「景区」命中不了「景点」—— 别名要列全。
HEADER_ALIASES = {
    "price":    ["价格", "票价", "票价/席别", "房价", "参考价", "起价"],
    "name":     ["航班", "车次", "班次", "酒店", "景点", "景区", "名称", "产品", "线路", "门票"],
    "route":    ["出发到达", "路线", "地址", "位置", "区域", "地区"],
    "date":     ["日期"],
    "duration": ["时长", "历时", "车程"],
    # Reason: hours 必须排在 time 之前 —— 否则「开放时间」会被 time 的「时间」先截走。
    "hours":    ["开放", "营业", "游玩"],
    "time":     ["时间", "出发时间"],
    "rating":   ["评分", "星级", "等级"],
    "index":    ["序号"],
}

PRICE_RE = re.compile(r"[¥￥]\s*([\d,]+(?:\.\d+)?)")

# 标题里的前导 emoji 与尾部条数统计，对分类无用，剥掉后 section 才好当 key 用。
_EMOJI_PREFIX_RE = re.compile(r"^[^\w一-鿿]+")
_COUNT_SUFFIX_RE = re.compile(r"[（(]\s*\d+\s*条\s*[）)]\s*$")


def _clean_heading(title):
    """把「#### ✈️ 机票（46 条）」净化为「机票」。"""
    title = _EMOJI_PREFIX_RE.sub("", title).strip()
    title = _COUNT_SUFFIX_RE.sub("", title).strip()
    return title


def extract_json(text):
    """从 CLI 原始输出中取出 VISUAL_JSON 块。"""
    match = re.search(re.escape(START) + r"(.*?)" + re.escape(END), text, re.S)
    if not match:
        raise ValueError(
            "未找到 WORKBUDDY_VISUAL_JSON 标记。可能原因：\n"
            "  - 未设置 CHENGXIN_OUTPUT_GUARD=display_contract\n"
            "  - token 失效（去 WorkBuddy「连应用」重连同程旅行）\n"
            "  - 脚本报错，请查看 stderr"
        )
    return json.loads(match.group(1))


def _norm_header(cell):
    """把表头单元格归一到标准字段名，未知表头原样保留。"""
    text = cell.strip()
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in text:
                return field
    return text


def parse_md_tables(md):
    """解析 markdown 中所有 GFM 表格，附带其所在章节标题。

    返回 [{"section": str, "group": str, "headers": [...], "rows": [dict, ...]}]
    """
    tables = []
    section = group = ""
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 追踪最近的标题，作为表格的归属上下文
        heading = re.match(r"^(#{3,6})\s+(.*)$", line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2).strip()
            title = _clean_heading(title)
            if level <= 4:
                section, group = title, ""
            else:
                group = title
            i += 1
            continue

        # 表格：表头行 + 分隔行 + 数据行
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|$", lines[i + 1].strip()):
            headers = [_norm_header(c) for c in line.strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if len(cells) == len(headers):
                    rows.append(dict(zip(headers, cells)))
                i += 1
            tables.append({"section": section, "group": group, "headers": headers, "rows": rows})
            continue
        i += 1
    return tables


def _parse_price(text):
    """从单元格文本取第一个金额。火车的「票价/席别」形如「二等座 ¥553」，取数字部分。"""
    match = PRICE_RE.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def extract_prices(md):
    """从 markdown 表格抽出带价格的条目，供预算计算。"""
    items = []
    for table in parse_md_tables(md):
        if "price" not in table["headers"]:
            continue
        for row in table["rows"]:
            price = _parse_price(row.get("price", ""))
            if price is None:
                continue
            items.append({
                "section": table["section"],
                "group": table["group"],
                "name": _strip_md(row.get("name", "")),
                "route": _strip_md(row.get("route", "")),
                "date": row.get("date", ""),
                "time": row.get("time", ""),
                "duration": row.get("duration", ""),
                "rating": _strip_md(row.get("rating", "")),
                "hours": _strip_md(row.get("hours", "")),
                "price": price,
                "price_raw": row.get("price", ""),
            })

    prices = [it["price"] for it in items]
    # 同程会把同一班次同时列进「最便宜」「耗时最短」「综合推荐」等分组，
    # 因此 count 含重复；unique_count 按 名称+价格 去重，用于判断真实选择面。
    unique = {(it["name"], it["price"]) for it in items}
    return {
        "count": len(items),
        "unique_count": len(unique),
        "min_price": min(prices) if prices else None,
        "max_price": max(prices) if prices else None,
        "items": items,
    }


def _strip_md(text):
    """去掉单元格里的 markdown 链接语法，只留可读文本。"""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text or "")
    return re.sub(r"[*_`]", "", text).strip()


def main():
    parser = argparse.ArgumentParser(description="解析同程 CLI 输出", add_help=True)
    parser.add_argument("--input", help="读取文件而非 stdin")
    parser.add_argument("--field", help="只输出该字段原文")
    parser.add_argument("--prices", action="store_true", help="抽取结构化报价")
    parser.add_argument("--summary", action="store_true", help="只输出元信息")
    args = parser.parse_args()

    raw = open(args.input, encoding="utf-8").read() if args.input else sys.stdin.read()

    try:
        data = extract_json(raw)
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"❌ VISUAL_JSON 不是合法 JSON: {exc}", file=sys.stderr)
        return 2

    if args.field:
        value = data.get(args.field)
        if value is None:
            print(f"❌ 字段不存在: {args.field}（可用: {', '.join(data)}）", file=sys.stderr)
            return 3
        print(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))
        return 0

    if args.prices:
        print(json.dumps(extract_prices(data.get("markdown", "")), ensure_ascii=False, indent=2))
        return 0

    if args.summary:
        print(json.dumps({
            "stats": data.get("stats", {}),
            "htmlFilePath": data.get("htmlFilePath", ""),
            "htmlFileName": data.get("htmlFileName", ""),
            "fallbackReason": data.get("fallbackReason", ""),
            "markdownChars": len(data.get("markdown", "")),
        }, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
