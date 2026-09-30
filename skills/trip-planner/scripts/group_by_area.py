#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
group_by_area.py — 把同程结果按「区县」分组，识别周边游的候选目的地。

周边游模式下用户不知道去哪，`travel-query --destination "{基地}周边"` 会返回
一批散落在各区县的酒店/景点/度假产品。按区县把它们聚起来，每个区县就是一个
候选目的地，供 Phase 2 组织成方案。

难点在于同程各业务的位置字段层级不一致：

    酒店   都江堰市 · 幸福路88号华光寺3楼；禅意四合院     ← 区县在前，后面是街道
    景点   成都 · 都江堰市；延续两千年的水利工程          ← 地级市在前，区县在后
    度假   （无位置字段，只能从产品名里认）

所以不能按位置取段，只能按「哪个片段长得像区县」来判断。

用法:
    python3 extract_visual_json.py --input x.raw.txt --prices \
      | python3 group_by_area.py --base 成都
    python3 group_by_area.py --input prices.json --base 成都 [--json]
"""
import argparse
import json
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 区县级行政区的常见后缀。「市」放最后：地级市与县级市同后缀，靠排除基地城市区分。
AREA_SUFFIX = ("县", "区", "镇", "乡", "旗", "市")
UNKNOWN = "(未识别)"


def _norm(name):
    """把「成都市」「成都」归一，便于与基地城市比对。"""
    return re.sub(r"(省|市|自治区|特别行政区)$", "", (name or "").strip())


def extract_area(text, base_city=""):
    """从位置字符串里认出区县名；认不出返回空串。"""
    if not text:
        return ""
    # 只看分号前的地址部分，后面是营销文案
    head = re.split(r"[；;]", text)[0]
    segments = [s.strip() for s in re.split(r"[·•・]", head) if s.strip()]
    base = _norm(base_city)

    for seg in segments:
        # 片段可能是「大邑县 西岭镇云华村」这种，取首个词做判断
        candidate = seg.split()[0] if seg.split() else seg
        if not candidate.endswith(AREA_SUFFIX):
            continue
        if len(candidate) > 12:          # 过长的多半是详细地址
            continue
        if _norm(candidate) == base:     # 基地城市本身不算「周边目的地」
            continue
        return candidate
    return ""


def extract_area_from_name(name, base_city=""):
    """度假产品没有位置字段，从产品名里找区县/景区名。"""
    if not name:
        return ""
    area = extract_area(name, base_city)
    if area:
        return area
    # 退而求其次：认知名景区关键词（产品名形如「都江堰青城山一日游」）
    match = re.search(r"([一-鿿]{2,6}(?:雪山|古镇|景区|湖|山|温泉|草原|峡谷))", name)
    return match.group(1) if match else ""


def group(items, base_city=""):
    """按区县聚合，返回 [{area, count, min_price, max_price, sections, samples}]"""
    buckets = {}
    for item in items:
        area = extract_area(item.get("route", ""), base_city) \
            or extract_area_from_name(item.get("name", ""), base_city) \
            or UNKNOWN
        buckets.setdefault(area, []).append(item)

    out = []
    for area, group_items in buckets.items():
        prices = [i["price"] for i in group_items if isinstance(i.get("price"), (int, float))]
        sections = {}
        for i in group_items:
            sections[i.get("section", "?")] = sections.get(i.get("section", "?"), 0) + 1
        out.append({
            "area": area,
            "count": len(group_items),
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "sections": sections,
            # 景点最能代表一个目的地值不值得去，优先取景点做样例
            "samples": [
                {"name": i["name"], "price": i["price"], "hours": i.get("hours", ""),
                 "rating": i.get("rating", ""), "section": i.get("section", "")}
                for i in sorted(group_items, key=lambda x: x.get("section") != "景点")[:4]
            ],
        })
    # 未识别的排最后，其余按条目数降序
    out.sort(key=lambda g: (g["area"] == UNKNOWN, -g["count"]))
    return out


def main():
    parser = argparse.ArgumentParser(description="按区县分组，识别周边游候选目的地")
    parser.add_argument("--input", help="prices.json；省略则读 stdin")
    parser.add_argument("--base", default="", help="出发基地城市名，用于排除市区自身")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而非人类可读文本")
    args = parser.parse_args()

    try:
        raw = open(args.input, encoding="utf-8").read() if args.input else sys.stdin.read()
        data = json.loads(raw)
    except FileNotFoundError:
        print(f"❌ 文件不存在：{args.input}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"❌ JSON 解析失败：{exc}", file=sys.stderr)
        return 1

    items = data.get("items", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        print("❌ 输入里找不到 items 数组", file=sys.stderr)
        return 1

    groups = group(items, args.base)

    if args.json:
        print(json.dumps(groups, ensure_ascii=False, indent=2))
        return 0

    real = [g for g in groups if g["area"] != UNKNOWN]
    print(f"候选目的地 {len(real)} 个（共 {len(items)} 条资源，基地：{args.base or '未指定'}）")
    print("-" * 62)
    for entry in groups:
        price = ""
        if entry["min_price"] is not None:
            price = (f"¥{entry['min_price']:.0f}" if entry["min_price"] == entry["max_price"]
                     else f"¥{entry['min_price']:.0f}-{entry['max_price']:.0f}")
        kinds = " ".join(f"{k}{v}" for k, v in sorted(entry["sections"].items()))
        print(f"■ {entry['area']}  （{entry['count']} 条 · {kinds}{' · ' + price if price else ''}）")
        for sample in entry["samples"]:
            bits = [f"{sample['name'][:26]}"]
            if sample["price"]:
                bits.append(f"¥{sample['price']:.0f}")
            if sample["hours"]:
                bits.append(sample["hours"][:26])
            print(f"    - {' | '.join(bits)}")
    if real:
        print("-" * 62)
        print("→ 把这些区县组合成 2-3 个方案（见 references/plan_compare.md 的「按目的地比选」）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
