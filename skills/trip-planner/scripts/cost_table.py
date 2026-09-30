#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cost_table.py — 生成行程费用明细表。

核心约束：**实时报价与经验估算永不混列。**
同程查到的机票/火车/酒店/门票是真金白银的当前报价；餐饮、市内交通只能靠
经验拍脑袋。把两者混进同一列求和，会让用户以为整份预算都同样可靠。
因此本脚本强制分成 🟢 / 🟡 两张表，各自小计，最后才合并成总计。

用法:
  python3 cost_table.py <cost.json> [--format markdown|json|routes-cost]
  python3 cost_table.py --example > cost.json     # 生成输入模板

输入 JSON:
  {
    "trip":   {"title": "上海 → 成都 3天2晚", "people": 2},
    "quoted": [                                   # 🟢 实时报价
      {"item": "往返高铁", "detail": "G1974/G1976 二等座", "unit_price": 842,
       "qty": 2, "unit": "人", "source": "同程 train-query", "day": 1}
    ],
    "estimated": [                                # 🟡 经验估算
      {"item": "市内交通", "detail": "地铁约 6 段 × 2 人", "unit_price": 5,
       "qty": 12, "unit": "次", "basis": "成都地铁均价", "day": 1}
    ]
  }

字段说明:
  unit_price × qty = 小计；unit 只用于显示。
  day 可选；填了就能额外产出按天汇总，喂给 inject_route.py 的 routes[].cost。
"""
import argparse
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

QUOTED_MARK = "🟢"
ESTIMATED_MARK = "🟡"

EXAMPLE = {
    "trip": {"title": "上海 → 成都 3天2晚", "people": 2},
    "quoted": [
        {"item": "去程高铁", "detail": "G1974 二等座 08:00-19:30", "unit_price": 842,
         "qty": 2, "unit": "人", "source": "同程 train-query", "day": 1},
        {"item": "返程机票", "detail": "MU5441 20:45-23:55", "unit_price": 1193,
         "qty": 2, "unit": "人", "source": "同程 flight-query", "day": 3},
        {"item": "住宿", "detail": "春熙路全季 2 晚", "unit_price": 389,
         "qty": 2, "unit": "晚", "source": "同程 hotel-query"},
        {"item": "景区门票", "detail": "大熊猫繁育研究基地", "unit_price": 55,
         "qty": 2, "unit": "人", "source": "同程 scenery-query", "day": 2},
    ],
    "estimated": [
        {"item": "市内交通", "detail": "地铁 + 打车", "unit_price": 40,
         "qty": 3, "unit": "天", "basis": "成都市内日均", "day": 1},
        {"item": "餐饮", "detail": "人均每天约 120 元", "unit_price": 120,
         "qty": 6, "unit": "人·天", "basis": "本地中等餐标"},
    ],
}


def _num(value, field, where):
    """把输入里的数字字段转成 float，出错时给出能定位的报错。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{where} 的 {field} 不是数字：{value!r}") from None


def _money(value):
    """金额显示：整数不带小数点，避免 ¥1684.0 这种碍眼的写法。"""
    return f"{value:,.0f}" if abs(value - round(value)) < 0.005 else f"{value:,.2f}"


def normalize(data):
    """校验并补全输入，返回 (trip, quoted, estimated)。"""
    if not isinstance(data, dict):
        raise ValueError("输入必须是 JSON 对象")

    trip = data.get("trip", {})
    if not isinstance(trip, dict):
        raise ValueError("trip 必须是对象")
    people = trip.get("people", 1)
    try:
        people = max(1, int(people))
    except (TypeError, ValueError):
        raise ValueError(f"trip.people 不是整数：{people!r}") from None
    trip["people"] = people

    groups = []
    for key in ("quoted", "estimated"):
        rows = data.get(key, [])
        if not isinstance(rows, list):
            raise ValueError(f"{key} 必须是数组")
        out = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"{key}[{idx}] 必须是对象")
            where = f"{key}[{idx}]"
            unit_price = _num(row.get("unit_price", 0), "unit_price", where)
            qty = _num(row.get("qty", 1), "qty", where)
            out.append({
                "item": str(row.get("item", "未命名")),
                "detail": str(row.get("detail", "")),
                "unit_price": unit_price,
                "qty": qty,
                "unit": str(row.get("unit", "")),
                "note": str(row.get("source") or row.get("basis") or ""),
                "day": row.get("day"),
                "subtotal": unit_price * qty,
            })
        groups.append(out)
    return trip, groups[0], groups[1]


def _table(rows, mark, note_header):
    """渲染单组费用表，返回 (markdown 行列表, 小计)。"""
    if not rows:
        return [f"_（无{mark}项）_", ""], 0.0

    lines = [
        f"| 项目 | 说明 | 单价 | 数量 | 小计 | {note_header} |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    total = 0.0
    for row in rows:
        total += row["subtotal"]
        qty = f"{row['qty']:g} {row['unit']}".strip()
        lines.append(
            f"| {row['item']} | {row['detail']} | ¥{_money(row['unit_price'])} | "
            f"{qty} | ¥{_money(row['subtotal'])} | {row['note']} |"
        )
    lines.append(f"| **小计** | | | | **¥{_money(total)}** | |")
    lines.append("")
    return lines, total


def by_day(quoted, estimated):
    """按 day 汇总，返回 {day: 金额}。未标 day 的项不计入。"""
    totals = {}
    for row in list(quoted) + list(estimated):
        day = row.get("day")
        if day is None:
            continue
        try:
            day = int(day)
        except (TypeError, ValueError):
            continue
        totals[day] = totals.get(day, 0.0) + row["subtotal"]
    return totals


def render_markdown(trip, quoted, estimated):
    people = trip["people"]
    title = trip.get("title", "行程")

    lines = [f"## 💰 费用明细 · {title}", ""]

    lines.append(f"### {QUOTED_MARK} 实时报价")
    lines.append("")
    lines.append("以下为查询时的同程实时价格，含可预订入口；价格随时间波动，下单前请以页面为准。")
    lines.append("")
    quoted_lines, quoted_total = _table(quoted, QUOTED_MARK, "来源")
    lines += quoted_lines

    lines.append(f"### {ESTIMATED_MARK} 经验估算")
    lines.append("")
    lines.append("以下为按常见消费水平推算，**不是报价**，仅用于把总预算补全。")
    lines.append("")
    est_lines, est_total = _table(estimated, ESTIMATED_MARK, "估算依据")
    lines += est_lines

    grand = quoted_total + est_total
    ratio = (quoted_total / grand * 100) if grand else 0.0
    lines += [
        "### 合计",
        "",
        "| 口径 | 金额 |",
        "| --- | ---: |",
        f"| {QUOTED_MARK} 实时报价小计 | ¥{_money(quoted_total)} |",
        f"| {ESTIMATED_MARK} 经验估算小计 | ¥{_money(est_total)} |",
        f"| **总计** | **¥{_money(grand)}** |",
        f"| **人均**（{people} 人） | **¥{_money(grand / people)}** |",
        "",
    ]

    day_totals = by_day(quoted, estimated)
    if day_totals:
        lines += ["### 按天分摊", "", "| 天 | 金额 |", "| --- | ---: |"]
        for day in sorted(day_totals):
            lines.append(f"| Day {day} | ¥{_money(day_totals[day])} |")
        unassigned = grand - sum(day_totals.values())
        if abs(unassigned) > 0.005:
            lines.append(f"| 未分摊（住宿等跨天项） | ¥{_money(unassigned)} |")
        lines.append("")

    lines += [
        f"> {QUOTED_MARK} 为查询时点的真实报价，{ESTIMATED_MARK} 为经验估算，实际以现场为准。",
        f"> 报价占总预算 {ratio:.0f}%。",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成行程费用明细表")
    parser.add_argument("cost_json", nargs="?", help="费用输入 JSON；省略则读 stdin")
    parser.add_argument("--format", default="markdown",
                        choices=["markdown", "json", "routes-cost"],
                        help="markdown=明细表；json=结构化汇总；routes-cost=按天金额，喂给 inject_route.py")
    parser.add_argument("--example", action="store_true", help="打印输入模板")
    args = parser.parse_args()

    if args.example:
        print(json.dumps(EXAMPLE, ensure_ascii=False, indent=2))
        return 0

    try:
        raw = open(args.cost_json, encoding="utf-8").read() if args.cost_json else sys.stdin.read()
        data = json.loads(raw)
        trip, quoted, estimated = normalize(data)
    except FileNotFoundError:
        print(f"❌ 文件不存在：{args.cost_json}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"❌ JSON 解析失败：{exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"❌ 输入格式错误：{exc}", file=sys.stderr)
        print("   用 --example 查看正确格式", file=sys.stderr)
        return 1

    if args.format == "markdown":
        print(render_markdown(trip, quoted, estimated))
    elif args.format == "routes-cost":
        print(json.dumps({str(k): round(v) for k, v in sorted(by_day(quoted, estimated).items())},
                         ensure_ascii=False, indent=2))
    else:
        quoted_total = sum(r["subtotal"] for r in quoted)
        est_total = sum(r["subtotal"] for r in estimated)
        print(json.dumps({
            "trip": trip,
            "quoted_total": quoted_total,
            "estimated_total": est_total,
            "grand_total": quoted_total + est_total,
            "per_person": (quoted_total + est_total) / trip["people"],
            "by_day": by_day(quoted, estimated),
            "quoted": quoted,
            "estimated": estimated,
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
