#!/usr/bin/env python3
"""linuxdo-reader：读取 linux.do（LINUX DO）的公开内容，限频/线路故障时自动换出口。

  ld.py latest [-n 10]            最新话题            ld.py hot / posts / top [--period weekly]
  ld.py category welfare/36       分类话题（slug/id、id、slug 或中文名）
  ld.py tag 纯水                  标签话题            ld.py user <用户名> [--topics]
  ld.py topic 2966557 [--page 2]  帖子正文（每页 20 楼，也接受完整链接）
  ld.py categories [--refresh]    分类列表            ld.py rss /badges/1/xxx.rss  任意 RSS 路径
  ld.py routes | doctor [--live] | reset [--cache]

站内搜索页被 Cloudflare 整页拦截（与出口无关），搜索请用 WebSearch「site:linux.do 关键词」拿到话题 id 再 topic。
退出码：0 成功 / 3 不存在或需登录 / 4 所有线路失败 / 5 缺少依赖 / 6 页面要求浏览器验证。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # Reason: 允许从任意工作目录调用

from ld_config import (CATEGORIES_FILE, CONFIG_FILE, HTTP_CACHE_DIR, RequestLock, State,  # noqa: E402
                       load_categories, load_config, save_categories)
from ld_fetch import EXIT_ALL_FAILED, EXIT_CHALLENGED, OUTCOME_ZH, FetchError, Fetcher  # noqa: E402
from ld_mihomo import cleanup_stale, find_binary, find_source, running_pid  # noqa: E402
from ld_parse import categories_from, clip, parse_feed, parse_preloaded, topic_from, topic_ref  # noqa: E402
from ld_routes import fmt_duration, load_pool, system_proxy  # noqa: E402


def emit_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def one_line(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


# ---------------------------------------------------------------- 列表类（RSS）

def print_items(items: list[dict], excerpt: int) -> None:
    for it in items:
        if it["type"] == "topic":
            flags = ("📌" if it["pinned"] else "") + ("🔒" if it["closed"] else "")
            stats = f"{it['posts_count']}帖/{it['participants']}人" if it["posts_count"] is not None else ""
            meta = " · ".join(x for x in (it["category"], f"@{it['author']}", it["created"], stats) if x)
            print(f"[{it['id']}] {flags}{it['title']}\n    {meta}")
            body = it["excerpt"]
        else:
            ref = f"{it['topic_id']}#{it['post_number']}" if it["post_number"] else str(it["topic_id"])
            print(f"[{ref}] {it['title']} · @{it['author']} · {it['created']}")
            body = it["text"]
        if excerpt and body:
            print(f"    {one_line(body, excerpt)}")


def run_feed(fx: Fetcher, cfg: dict, args, path: str) -> int:
    resp = fx.get(path, "rss")
    feed = parse_feed(resp.body, cfg["base_url"])
    items = feed["items"][: args.limit] if args.limit else feed["items"]
    if args.json:
        emit_json({"source": resp.url, "feed": feed["title"], "route": resp.route, "items": items})
        return 0
    print(f"## {feed['title']}（{len(items)} 条 · {path} · 链接格式 {cfg['base_url']}/t/topic/<id>）")
    if items:
        print_items(items, args.excerpt)
    else:
        print("（空）")
    return 0


def fetch_categories(fx: Fetcher, refresh: bool = False) -> list[dict]:
    cats = [] if refresh else load_categories()
    if not cats:
        pre = parse_preloaded(fx.get("/categories", "html").body)
        cats = categories_from(pre) if pre else []
        save_categories(cats)
    return cats


def category_path(fx: Fetcher, ref: str) -> str:
    ref = ref.strip().strip("/")
    ref = ref[2:] if ref.startswith("c/") else ref
    if re.fullmatch(r"[^/\s]+(?:/[^/\s]+)*/\d+", ref):  # 已经是 slug/id（或 父slug/子slug/id）
        return f"/c/{ref}.rss"
    if ref.isdigit() and not load_categories():
        return f"/c/{ref}.rss"  # 只有 id 时服务端会 301 到规范地址，curl -L 会跟随，省一次拉分类表
    cats = fetch_categories(fx)
    for c in cats:
        if ref.lower() in (str(c["id"]), str(c["slug"]).lower(), str(c["name"]).lower()):
            return f"/c/{c['slug']}/{c['id']}.rss"
    names = "、".join(f"{c['name']}({c['slug']}/{c['id']})" for c in cats)
    raise SystemExit(f"找不到分类「{ref}」。可用分类：{names}")


def cmd_feed(fx, cfg, args) -> int:
    quote = urllib.parse.quote
    if args.cmd in ("latest", "hot", "posts"):
        path = f"/{args.cmd}.rss"
    elif args.cmd == "top":
        path = "/top.rss" + (f"?period={args.period}" if args.period else "")
    elif args.cmd == "category":
        path = category_path(fx, args.ref)
    elif args.cmd == "tag":
        path = f"/tag/{quote(args.name, safe='')}.rss"
    elif args.cmd == "user":
        path = f"/u/{quote(args.username, safe='')}/activity" + ("/topics" if args.topics else "") + ".rss"
    else:  # rss：接受站内路径或完整链接
        path = args.path if args.path.startswith(("/", "http")) else "/" + args.path
    return run_feed(fx, cfg, args, path)


# ---------------------------------------------------------------- 帖子正文 / 搜索 / 分类

def print_topic(t: dict, posts: list[dict], args) -> None:
    tags = f" · 标签：{', '.join(t['tags'])}" if t["tags"] else ""
    state = "（已关闭）" if t["closed"] else ""
    print(f"# {t['title']}{state}")
    print(f"{t['url']} · {t['category']}{tags} · {t['posts_count']} 帖 · {t['views']} 浏览 · "
          f"{t['like_count']} 赞 · 楼主 @{t['author']} · {t['created']}")
    if posts:
        tail = (f"，下一页：ld.py topic {t['id']} --page {t['page'] + 1}" if t["page"] < t["pages"]
                else "，已到最后一页")
        print(f"第 {t['page']}/{t['pages']} 页（#{posts[0]['number']}–#{posts[-1]['number']}）{tail}")
    for p in posts:
        limit = 0 if args.full else (args.op_chars if p["number"] == 1 else args.reply_chars)
        name = f"（{p['name']}）" if p["name"] and p["name"] != p["username"] else ""
        likes = f" · ❤ {p['likes']}" if p["likes"] else ""
        reply = f" · 回复 #{p['reply_to']}" if p["reply_to"] else ""
        print(f"\n### #{p['number']} @{p['username']}{name} · {p['created']}{likes}{reply}")
        print(clip(p["text"], limit))


def cmd_topic(fx, cfg, args) -> int:
    tid, number = topic_ref(args.ref)
    if not tid:
        raise SystemExit(f"无法识别的话题：{args.ref}（给话题 id 或 linux.do 链接）")
    first = args.page or ((number - 1) // 20 + 1 if number else 1)
    topic, posts = None, []
    for page in range(first, first + min(max(1, args.pages), cfg["max_pages"])):
        resp = fx.get(f"/t/topic/{tid}" + (f"?page={page}" if page > 1 else ""), "html")
        pre = parse_preloaded(resp.body)
        current = topic_from(pre, cfg["base_url"]) if pre else None
        if current is None:
            break
        save_categories(categories_from(pre))  # 顺手刷新分类缓存，category 命令就不用再联网
        topic = topic or current
        topic["page"] = current["page"]
        posts.extend(current["posts"])
        if current["page"] >= current["pages"]:
            break
    if topic is None:
        # 页面结构不认识时退回话题 RSS：只有最近 25 楼，但总比没有强
        print("[linuxdo] 帖子页解析失败，改用话题 RSS（仅最近 25 楼，倒序）", file=sys.stderr)
        return run_feed(fx, cfg, args, f"/t/topic/{tid}.rss")
    if args.json:
        emit_json({**topic, "posts": posts})
    else:
        print_topic(topic, posts, args)
    return 0


def cmd_categories(fx, cfg, args) -> int:
    cats = fetch_categories(fx, refresh=args.refresh)
    if args.json:
        emit_json(cats)
        return 0
    children: dict = {}
    for c in cats:
        children.setdefault(c["parent_id"], []).append(c)
    for c in children.get(None, []):
        print(f"{c['name']}  {c['slug']}/{c['id']}  {c['description']}")
        for sub in children.get(c["id"], []):
            print(f"    └ {sub['name']}  {sub['slug']}/{sub['id']}  {sub['description']}")
    return 0


# ---------------------------------------------------------------- 线路状态 / 自检 / 重置

def _cool_desc(state: State, key: str, bucket: str = "routes") -> str:
    entry = state.cooling(key, bucket)
    if not entry:
        return "✅ 可用"
    return f"⏸ 冷却中：{entry['reason']}（还剩 {fmt_duration(entry['until'] - time.time())}）"


def cmd_routes(fx, cfg, args) -> int:
    st = State.load()
    last = st.data["last_request_at"]
    print(f"线路顺序：{' → '.join(cfg['routes'])} · 节流 ≥{cfg['min_interval']:g}s/次"
          + (f" · 上次请求 {fmt_duration(time.time() - last)}前" if last else ""))
    proxy = system_proxy(cfg)
    print(f"[system] {proxy or '未检测到系统代理，将直连'}  {_cool_desc(st, 'system' if proxy else 'direct')}")
    ccfg = cfg["clash"]
    binary, source = find_binary(ccfg.get("binary", "")), find_source(ccfg.get("source_config", ""))
    print(f"[clash]  内核：{binary or '❌ 未找到'}\n         节点来源：{source or '❌ 未找到'}  "
          f"{_cool_desc(st, 'clash-tier')}")
    for key, entry in sorted(st.data["routes"].items()):
        if key.startswith("clash:"):
            print(f"         ⏸ {key[6:]}：{entry['reason']}（还剩 {fmt_duration(entry['until'] - time.time())}）")
    pid = running_pid()
    if pid:
        print(f"         ⚠️ 独立 mihomo 仍在运行（pid {pid}），没有 ld.py 在跑的话可用 ld.py reset 清理")
    entries = load_pool(cfg["pool"]["files"])
    per_file = Counter(path for path, _ in entries)
    print(f"[pool]   {', '.join(cfg['pool']['files'])} → {len(per_file)} 个文件 / {len(entries)} 条代理")
    for path, count in per_file.items():
        print(f"         {os.path.basename(path)}：{count} 条  {_cool_desc(st, path, 'pool_files')}")
    dead = sum(1 for key in st.data["routes"] if key.startswith("pool:"))
    if dead:
        print(f"         另有 {dead} 条单个代理在冷却中")
    return 0


def cmd_doctor(fx, cfg, args) -> int:
    version = subprocess.run(["curl", "--version"], capture_output=True, text=True).stdout.split("\n")[0]
    print(f"curl：{version or '❌ 未找到'}")
    print(f"python：{sys.version.split()[0]}")
    print(f"配置文件：{CONFIG_FILE if CONFIG_FILE.is_file() else f'未创建（使用默认值，可参考 config.example.json 建 {CONFIG_FILE}）'}")
    cmd_routes(fx, cfg, args)
    if args.live:
        fx.use_cache = False
        feed = parse_feed(fx.get("/latest.rss", "rss").body, cfg["base_url"])
        print(f"实测：/latest.rss 返回 {len(feed['items'])} 条 ✅")
    return 0


def cmd_reset(fx, cfg, args) -> int:
    lock = RequestLock()
    lock.acquire()  # 与正在运行的请求互斥，免得状态被覆盖
    try:
        st = State.load()
        removed = st.clear(args.key)
        st.save()
        killed = cleanup_stale()
        cleared = 0
        if args.cache:
            for path in [*HTTP_CACHE_DIR.glob("*.json"), CATEGORIES_FILE]:
                if path.exists():
                    path.unlink()
                    cleared += 1
    finally:
        lock.release()
    print(f"已清除 {removed} 条冷却记录" + ("，并结束了遗留的独立 mihomo" if killed else "")
          + (f"，删除 {cleared} 个缓存文件" if args.cache else ""))
    return 0


# ---------------------------------------------------------------- 入口

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="输出 JSON（全文不截断）")
    common.add_argument("--no-cache", action="store_true", help="跳过本地缓存")
    common.add_argument("--route", choices=["system", "direct", "clash", "pool"], help="只用指定线路")
    listing = argparse.ArgumentParser(add_help=False)
    listing.add_argument("-n", "--limit", type=int, default=0, help="最多显示几条")
    listing.add_argument("--excerpt", type=int, default=120, help="摘要长度，0 不显示")

    parser = argparse.ArgumentParser(prog="ld.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("latest", "hot", "posts"):
        sub.add_parser(name, parents=[common, listing]).set_defaults(handler=cmd_feed)
    p = sub.add_parser("top", parents=[common, listing])
    p.add_argument("--period", choices=["daily", "weekly", "monthly", "quarterly", "yearly", "all"])
    p.set_defaults(handler=cmd_feed)
    p = sub.add_parser("category", parents=[common, listing])
    p.add_argument("ref", help="slug/id、id、slug 或中文名，如 welfare/36")
    p.set_defaults(handler=cmd_feed)
    p = sub.add_parser("tag", parents=[common, listing])
    p.add_argument("name")
    p.set_defaults(handler=cmd_feed)
    p = sub.add_parser("user", parents=[common, listing])
    p.add_argument("username")
    p.add_argument("--topics", action="store_true", help="只看发起的话题（默认是全部动态帖子）")
    p.set_defaults(handler=cmd_feed)
    p = sub.add_parser("rss", parents=[common, listing])
    p.add_argument("path", help="任意 Discourse RSS 路径，如 /g/xxx/posts.rss")
    p.set_defaults(handler=cmd_feed)
    p = sub.add_parser("topic", parents=[common, listing])
    p.add_argument("ref", help="话题 id、id/楼层 或 linux.do 链接")
    p.add_argument("--page", type=int, default=0, help="第几页（每页 20 楼）")
    p.add_argument("--pages", type=int, default=1, help="连续读几页（上限见 max_pages）")
    p.add_argument("--full", action="store_true", help="不截断正文")
    p.add_argument("--op-chars", type=int, default=6000, help="主楼最多显示字数")
    p.add_argument("--reply-chars", type=int, default=800, help="回复最多显示字数")
    p.set_defaults(handler=cmd_topic)
    p = sub.add_parser("categories", parents=[common])
    p.add_argument("--refresh", action="store_true", help="忽略缓存重新拉取")
    p.set_defaults(handler=cmd_categories)
    sub.add_parser("routes", parents=[common]).set_defaults(handler=cmd_routes)
    p = sub.add_parser("doctor", parents=[common])
    p.add_argument("--live", action="store_true", help="额外实测拉一次 /latest.rss")
    p.set_defaults(handler=cmd_doctor)
    p = sub.add_parser("reset", parents=[common])
    p.add_argument("key", nargs="?", help="只清除某条线路的冷却，如 system 或 clash:<节点名>")
    p.add_argument("--cache", action="store_true", help="同时清空响应缓存与分类缓存")
    p.set_defaults(handler=cmd_reset)
    return parser


def report_failure(exc: FetchError) -> None:
    print(f"[linuxdo] 失败：{exc}", file=sys.stderr)
    for i, attempt in enumerate(exc.attempts, 1):
        outcome = OUTCOME_ZH.get(attempt["outcome"], attempt["outcome"])
        print(f"  {i}. {attempt['route']} → {outcome}：{attempt['detail']}", file=sys.stderr)
    if exc.exit_code == EXIT_ALL_FAILED:
        print("  建议：linux.do 可能正在限流，稍后再试；ld.py routes 可查看各线路剩余冷却时间。", file=sys.stderr)
    elif exc.exit_code == EXIT_CHALLENGED:
        print("  说明：该页面要求浏览器验证，换出口也过不去，本 skill 不绕过。搜索请改用 WebSearch「site:linux.do 关键词」。",
              file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if shutil.which("curl") is None:
        print("缺少 curl，无法请求 linux.do", file=sys.stderr)
        return 5
    cfg = load_config()
    # Reason: 收到 SIGTERM 时走正常退出流程，finally 才能停掉独立 mihomo、释放请求锁
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    fx = Fetcher(cfg, only_route=args.route, use_cache=not args.no_cache)
    try:
        return args.handler(fx, cfg, args) or 0
    except FetchError as exc:
        report_failure(exc)
        return exc.exit_code
    except KeyboardInterrupt:
        return 130
    finally:
        fx.close()


if __name__ == "__main__":
    sys.exit(main())
