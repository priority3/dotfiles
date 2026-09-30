#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_route.py — 把地点与按天路线注入 route_map.html 模板，生成最终地图。

与上游 weekend-city-trip 的 inject.py 的区别：多注入一个 {{ROUTES_JSON}}，
使地图能画出按天连线。没有 routes 时注入空数组，模板行为退化为普通散点图。

用法：
  python3 inject_route.py <geo.json> <output.html> <城市> [日期范围] [--routes routes.json]

输入 geo.json 支持两种形态：
  1. 数组          —— 上游 geocode.py 的原生输出，即 places 列表
  2. 对象          —— {"places": [...], "routes": [...]}，routes 可省

routes.json（可选，也可内嵌于 geo.json）：
  [
    {"day": 1, "name": "老城人文", "stops": ["U001", "F002", "L003"],
     "transport": "地铁2号线 → 步行", "cost": 280, "note": "上午博物馆下午骑楼"}
  ]
  stops 按游览顺序引用 places[].id。

环境变量（必填）：
  AMAP_JS_KEY    高德「Web 端 JS API」Key（浏览器加载底图）
  AMAP_SECURITY  与之配套的安全密钥

模板占位符：
  {{CITY}} {{DATE_RANGE}} {{TOTAL}} {{CENTER_LNG}} {{CENTER_LAT}} {{ZOOM}}
  {{PLACES_JSON}} {{ROUTES_JSON}} {{AMAP_JS_KEY}} {{AMAP_SECURITY}}
"""
import argparse
import json
import math
import os
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(SKILL_DIR, "templates", "route_map.html")

# 中国大陆经纬度合理范围，用于剔除明显错误的编码结果
LAT_RANGE = (18.0, 55.0)
LNG_RANGE = (73.0, 135.0)


def load_dotenv():
    """读取 skill 目录与当前目录的 .env；已存在的环境变量不覆盖。"""
    for env_path in (os.path.join(SKILL_DIR, ".env"), os.path.join(os.getcwd(), ".env")):
        if not os.path.isfile(env_path):
            continue
        try:
            with open(env_path, encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key, val = key.strip(), val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except OSError:
            pass


def _trimmed_midpoint(values, trim=0.1):
    """去除两端 trim 比例的离群值后取中点。"""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    k = max(1, int(n * trim))
    trimmed = s[k:-k] if k < n - k else s
    return (trimmed[0] + trimmed[-1]) / 2


def _valid_coord(place):
    lat, lng = place.get("lat"), place.get("lng")
    return (
        isinstance(lat, (int, float)) and isinstance(lng, (int, float))
        and not math.isnan(lat) and not math.isnan(lng)
        and LAT_RANGE[0] <= lat <= LAT_RANGE[1]
        and LNG_RANGE[0] <= lng <= LNG_RANGE[1]
    )


def compute_center(places):
    """从地点坐标算地图中心与合适的 zoom。

    分两步，兼顾抗离群与视野完整：
      1. 用修剪中点定位「主簇」在哪 —— 抗住地理编码错到外地的点
      2. 把距主簇 3° 以内的点**全部**纳入包围盒算中心与跨度

    Reason: 只用修剪中点会在「1 个基地 + N 个目的地」的周边游场景下失真 ——
    基地城市仅一个点，会被当成离群值修掉，中心落在目的地、zoom 过大，
    打开地图看不到出发地和整条路线。3° 内的远点是合理行程范围，必须纳入。
    无有效坐标时才回退到全国视野。
    """
    coords = [(p["lat"], p["lng"]) for p in places if _valid_coord(p)]
    if not coords:
        return 116.4074, 39.9042, 4, "none"

    ref_lat = _trimmed_midpoint([c[0] for c in coords])
    ref_lng = _trimmed_midpoint([c[1] for c in coords])
    kept = [(la, ln) for la, ln in coords
            if abs(la - ref_lat) <= 3 and abs(ln - ref_lng) <= 3] or coords

    lats = [c[0] for c in kept]
    lngs = [c[1] for c in kept]
    lat = (min(lats) + max(lats)) / 2
    lng = (min(lngs) + max(lngs)) / 2
    span = max(max(lats) - min(lats), max(lngs) - min(lngs))

    for limit, zoom in ((0.05, 14), (0.2, 13), (0.5, 12), (1.5, 11), (4.0, 10)):
        if span < limit:
            break
    else:
        zoom = 8
    source = "auto" if len(kept) == len(coords) else f"auto(排除{len(coords) - len(kept)}个离群)"
    return lng, lat, zoom, source


def load_input(geo_path, routes_path):
    """载入 places 与 routes，兼容数组 / 对象两种 geo.json 形态。"""
    with open(geo_path, encoding="utf-8") as fp:
        data = json.load(fp)

    if isinstance(data, list):
        places, routes = data, []
    elif isinstance(data, dict):
        places = data.get("places", [])
        routes = data.get("routes", [])
    else:
        raise ValueError("geo.json 必须是数组或对象")

    if routes_path:
        with open(routes_path, encoding="utf-8") as fp:
            extra = json.load(fp)
        routes = extra.get("routes", extra) if isinstance(extra, dict) else extra

    if not isinstance(places, list):
        raise ValueError("places 必须是数组")
    if not isinstance(routes, list):
        raise ValueError("routes 必须是数组")
    return places, routes


def sync_place_days(places, routes):
    """按 routes 的 stops 顺序回填 places 的 day / order。

    Reason: 让 agent 只需维护一处顺序（routes.stops），
    地图上的站点序号与卡片分组自动跟随，不会两处打架。

    一个地点可能被多天引用（酒店每晚回、地铁站反复经过），而 marker 只能有
    一个归属。取「首次引用」而非最后一次：结果不随 routes 的书写顺序漂移，
    且符合直觉——先到的那天就是它的主场。重复引用记入 shared 供调用方提示。
    """
    index = {str(p.get("id")): p for p in places}
    filled = 0
    shared = {}
    for route in routes:
        day = route.get("day")
        for order, sid in enumerate(route.get("stops", []), start=1):
            place = index.get(str(sid))
            if place is None:
                continue
            if place.get("day") is not None:
                shared.setdefault(str(sid), {"name": place.get("name"), "days": [place["day"]]})
                shared[str(sid)]["days"].append(day)
                continue
            place["day"] = day
            place["order"] = order
            filled += 1
    return filled, shared


def check_routes(places, routes):
    """校验 routes 引用完整性，返回问题清单（不抛异常，交由调用方决定严重性）。"""
    index = {str(p.get("id")): p for p in places}
    problems = []
    for route in routes:
        day = route.get("day", "?")
        stops = route.get("stops", [])
        if not stops:
            problems.append(f"Day {day}: stops 为空")
            continue
        located = 0
        for sid in stops:
            place = index.get(str(sid))
            if place is None:
                problems.append(f"Day {day}: 引用了不存在的地点 id「{sid}」")
            elif not _valid_coord(place):
                problems.append(f"Day {day}: 「{place.get('name', sid)}」无有效坐标，连线会跳过该站")
            else:
                located += 1
        if located < 2:
            problems.append(f"Day {day}: 仅 {located} 个站点可定位，画不出连线")
    return problems


def main():
    parser = argparse.ArgumentParser(description="注入地点与路线，生成行程地图 HTML")
    parser.add_argument("geo_json", help="geocode.py 产出的 .geo.json")
    parser.add_argument("output_html", help="输出的 HTML 路径")
    parser.add_argument("city", help="城市名")
    parser.add_argument("date_range", nargs="?", default="", help="日期范围，如 2026/10/1-4")
    parser.add_argument("--routes", help="单独的 routes.json（可选）")
    args = parser.parse_args()

    load_dotenv()
    js_key = os.environ.get("AMAP_JS_KEY", "").strip()
    security = os.environ.get("AMAP_SECURITY", "").strip()
    if not js_key or not security:
        print("❌ 缺少 AMAP_JS_KEY / AMAP_SECURITY，无法生成可用地图")
        print()
        print("这两项是浏览器加载高德底图所需，类型必须是「Web 端(JS API)」，")
        print("与地理编码用的 AMAP_KEY（Web 服务类型）不是同一个 Key。")
        print(f"配置：编辑 {os.path.join(SKILL_DIR, '.env')}")
        print("申请：https://console.amap.com/dev/key/app")
        return 2

    if not os.path.exists(args.geo_json):
        print(f"❌ 文件不存在：{args.geo_json}")
        return 1
    if not os.path.exists(TPL):
        print(f"❌ 模板不存在：{TPL}")
        return 1

    try:
        places, routes = load_input(args.geo_json, args.routes)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"❌ 输入解析失败：{exc}")
        return 1

    filled, shared = sync_place_days(places, routes)
    lng, lat, zoom, source = compute_center(places)

    # 防御性过滤：坐标偏离中心 >3° 的点多半是编码到了同名的外地地标
    outliers = 0
    for place in places:
        if _valid_coord(place) and (abs(place["lat"] - lat) > 3 or abs(place["lng"] - lng) > 3):
            place["geocoded"] = False
            place["geocode_status"] = f"outlier:{place['lat']:.4f},{place['lng']:.4f}"
            place["lat"] = place["lng"] = None
            outliers += 1

    problems = check_routes(places, routes)
    total = len(places)
    geocoded = sum(1 for p in places if _valid_coord(p))

    with open(TPL, encoding="utf-8") as fp:
        html = fp.read()
    for token, value in (
        ("{{CITY}}", args.city),
        ("{{DATE_RANGE}}", args.date_range),
        ("{{TOTAL}}", f"{geocoded}/{total}"),
        ("{{CENTER_LNG}}", str(lng)),
        ("{{CENTER_LAT}}", str(lat)),
        ("{{ZOOM}}", str(zoom)),
        ("{{PLACES_JSON}}", json.dumps(places, ensure_ascii=False)),
        ("{{ROUTES_JSON}}", json.dumps(routes, ensure_ascii=False)),
        ("{{AMAP_JS_KEY}}", js_key),
        ("{{AMAP_SECURITY}}", security),
    ):
        html = html.replace(token, value)

    leftover = re.findall(r"\{\{.*?\}\}", html)
    if leftover:
        print(f"⚠️  未替换的模板占位符：{leftover}")

    os.makedirs(os.path.dirname(os.path.abspath(args.output_html)) or ".", exist_ok=True)
    with open(args.output_html, "w", encoding="utf-8") as fp:
        fp.write(html)

    print(f"✅ {args.output_html}")
    print(f"   地点：{total} 个（已定位 {geocoded}）")
    if routes:
        days = sorted({r.get("day") for r in routes if r.get("day")})
        print(f"   路线：{len(routes)} 条，覆盖 Day {days}，回填站序 {filled} 处")
        for info in shared.values():
            print(f"   ℹ️  「{info['name']}」被 Day {info['days']} 多次经过，归属首次出现的 Day {info['days'][0]}")
    else:
        print("   路线：无（地图为散点模式）")
    print(f"   中心：{lng:.4f},{lat:.4f} zoom={zoom}（{source}）")
    if outliers:
        print(f"   ⚠️  {outliers} 个地点偏离中心 >3°，已隐藏")
    if total - geocoded:
        print(f"   ⚠️  {total - geocoded} 个地点无坐标，地图上不显示")
    for problem in problems:
        print(f"   ⚠️  {problem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
