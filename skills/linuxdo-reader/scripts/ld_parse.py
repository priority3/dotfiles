"""解析层：RSS（话题/帖子列表）、页面内嵌的 data-preloaded JSON、cooked HTML 转纯文本。"""

from __future__ import annotations

import html as htmllib
import json
import math
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

_DC = "{http://purl.org/dc/elements/1.1/}"
_DS = "{http://www.discourse.org/}"
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_BLOCK = {"p", "div", "ul", "ol", "table", "tr", "figure", "details", "section"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_NO_URL_LINKS = {"mention", "mention-group", "hashtag-cooked", "lightbox", "anchor"}
# 引用层级哨兵：解析时只记录进出，后处理再按层级给每行加 "> " 前缀
_Q_OPEN, _Q_CLOSE = "\x01", "\x02"


class _Cooked2Text(HTMLParser):
    """把 Discourse 的 cooked HTML 转成适合阅读的纯文本（保留链接、代码块和引用层级）。"""

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.out: list[str] = []
        self.skip = 0              # >0 时丢弃内容：脚本、图片元信息、链接预览卡片等
        self.pre = 0
        self.quote_title = False   # 刚进入引用框，下一个 div.title（「xxx:」）是噪音
        self.links: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        if self.skip:
            if tag not in _VOID:  # 自闭合标签没有结束标签，不能计入嵌套深度
                self.skip += 1
            return
        a = dict(attrs)
        cls = set((a.get("class") or "").split())
        if tag in ("script", "style", "svg", "noscript") or (tag == "div" and "meta" in cls):
            self.skip = 1  # div.meta 是 lightbox 图片下的文件名/尺寸
        elif tag == "div" and "title" in cls and self.quote_title:
            self.quote_title, self.skip = False, 1
        elif tag == "aside" and "onebox" in cls:
            self.out.append(f"\n[链接预览] {a.get('data-onebox-src') or ''}\n")
            self.skip = 1
        elif tag == "aside" and "quote" in cls:
            user = a.get("data-username")
            self.out.append(f"\n[引用 @{user}]" if user else "\n[引用]")
            self.quote_title = True
        elif tag == "blockquote":
            self.out.append("\n" + _Q_OPEN)
        elif tag == "br":
            self.out.append("\n")
        elif tag == "hr":
            self.out.append("\n---\n")
        elif tag in _HEADINGS:
            self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag == "pre":
            self.pre += 1
            self.out.append("\n```\n")
        elif tag == "code" and not self.pre:
            self.out.append("`")
        elif tag == "img":
            self.out.append((a.get("alt") or a.get("title") or "") if "emoji" in cls else "[图片]")
        elif tag in ("iframe", "video", "audio"):
            self.out.append("[媒体]")
        elif tag == "summary":
            self.out.append("\n▶ ")
        elif tag == "a":
            self.links.append((len(self.out), "" if cls & _NO_URL_LINKS else a.get("href") or ""))
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if self.skip:
            if tag not in _VOID:
                self.skip -= 1
            return
        if tag == "blockquote":
            self.out.append(_Q_CLOSE + "\n")
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.out.append("\n```\n")
        elif tag == "code" and not self.pre:
            self.out.append("`")
        elif tag == "a" and self.links:
            start, href = self.links.pop()
            text = "".join(self.out[start:]).strip()
            url = self._absolute(href)
            # 链接文字本身就是网址时不重复输出
            if url and text and not text.startswith("http") and text.rstrip("/") != url.rstrip("/"):
                self.out.append(f"（{url}）")
            elif url and not text:
                self.out.append(url)
        elif (tag in _BLOCK and tag != "tr") or tag in _HEADINGS:
            # li / tr 的换行已由下一个 li / tr 的开始标签输出，这里再加会多出空行
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data if self.pre else re.sub(r"\s+", " ", data))

    def _absolute(self, href: str) -> str:
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            return ""
        if href.startswith("//"):
            return "https:" + href
        return self.base + href if href.startswith("/") else href


def html_to_text(fragment: str, base: str = "https://linux.do") -> str:
    parser = _Cooked2Text(base)
    parser.feed(fragment or "")
    parser.close()
    lines, depth, in_code = [], 0, False
    for line in "".join(parser.out).split("\n"):
        depth += line.count(_Q_OPEN)
        level = depth
        depth = max(0, depth - line.count(_Q_CLOSE))
        line = line.replace(_Q_OPEN, "").replace(_Q_CLOSE, "")
        if line.strip() == "```":
            if in_code:
                while lines and not lines[-1].strip():
                    lines.pop()  # 代码块末尾的换行会在收尾 ``` 前留下空行
            in_code, line = not in_code, "```"
        elif in_code:
            line = line.rstrip()
        else:
            line = re.sub(r"[ \t\u00a0]+", " ", line).strip()
        lines.append("> " * level + line if level and line else line)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return re.sub(r"```\n+```", "", text).strip()


def clip(text: str, limit: int) -> str:
    if limit and len(text) > limit:
        return text[:limit].rstrip() + f" …（已截断，全文 {len(text)} 字，加 --full 查看）"
    return text


def _local(dt: datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def from_rfc822(value: str | None) -> str:
    try:
        return _local(parsedate_to_datetime(value))
    except (TypeError, ValueError, IndexError):
        return value or ""


def from_iso(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _local(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return value


def topic_ref(ref: str) -> tuple[int | None, int | None]:
    """从话题 id、`id/楼层` 或完整链接里取出 (话题 id, 楼层号)。"""
    ref = (ref or "").strip()
    match = re.search(r"/t/([^?#]+)", ref)
    segs = [s for s in (match.group(1) if match else ref).split("/") if s]
    if segs and not segs[0].isdigit():
        segs = segs[1:]  # 去掉 slug（linux.do 的链接统一是 /t/topic/<id>）
    tid = int(segs[0]) if segs and segs[0].isdigit() else None
    number = int(segs[1]) if len(segs) > 1 and segs[1].isdigit() else None
    if number is None:
        post = re.search(r"#post_(\d+)", ref)
        number = int(post.group(1)) if post else None
    return tid, number


_STATS = re.compile(r"<p>\s*<small>\s*(\d+)\s*(?:个帖子|posts?)\s*-\s*(\d+)\s*(?:位参与者|participants?)\s*</small>\s*</p>", re.I)
_READ_MORE = re.compile(r"<p>\s*<a [^>]*>\s*(?:阅读完整话题|Read full topic)\s*</a>\s*</p>", re.I)


def parse_feed(xml_text: str, base: str) -> dict:
    """解析 Discourse RSS：话题列表（latest/hot/top/分类/标签…）与帖子列表（posts/话题/用户动态）通吃。"""
    channel = ET.fromstring(xml_text).find("channel")
    if channel is None:
        raise ValueError("RSS 里没有 channel 节点")
    items = []
    for it in channel.findall("item"):
        link = it.findtext("link") or ""
        desc = it.findtext("description") or ""
        creator = (it.findtext(f"{_DC}creator") or "").strip()
        tid, number = topic_ref(link)
        title = (it.findtext("title") or "").strip()
        created = from_rfc822(it.findtext("pubDate"))
        if "-post-" in (it.findtext("guid") or ""):
            # posts.rss 的 creator 形如「@user user」，话题 RSS 里则是纯用户名
            author = creator.split()[0].lstrip("@") if creator else ""
            items.append({"type": "post", "topic_id": tid, "post_number": number, "title": title,
                          "author": author, "created": created, "url": link, "text": html_to_text(desc, base)})
            continue
        stats = _STATS.search(desc)
        items.append({
            "type": "topic", "id": tid, "title": title, "author": creator,
            "category": it.findtext("category") or "", "created": created, "url": link,
            "posts_count": int(stats.group(1)) if stats else None,
            "participants": int(stats.group(2)) if stats else None,
            "pinned": it.findtext(f"{_DS}topicPinned") == "Yes",
            "closed": it.findtext(f"{_DS}topicClosed") == "Yes",
            "archived": it.findtext(f"{_DS}topicArchived") == "Yes",
            "excerpt": html_to_text(_READ_MORE.sub("", _STATS.sub("", desc)), base),
        })
    return {"title": channel.findtext("title") or "", "items": items}


_PRELOADED_SCRIPT = re.compile(r'<script[^>]*\bid="data-preloaded"[^>]*>(.*?)</script>', re.S)
_PRELOADED_ATTR = re.compile(r'\bid="data-preloaded"[^>]*\bdata-preloaded="([^"]*)"')


def parse_preloaded(page: str) -> dict | None:
    candidates = []
    match = _PRELOADED_SCRIPT.search(page)
    if match:
        candidates.append(match.group(1))  # 新版放在 JSON script 里，本身就是合法 JSON，不能再反转义
    match = _PRELOADED_ATTR.search(page)
    if match:
        candidates.append(htmllib.unescape(match.group(1)))  # 旧版放在 HTML 属性里
    for raw in candidates:
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _decoded(pre: dict, key: str | None):
    value = pre.get(key) if key else None
    if isinstance(value, str):  # 大部分值是二次编码的 JSON 字符串
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def categories_from(pre: dict) -> list[dict]:
    site = _decoded(pre, "site") or {}
    return [{"id": c.get("id"), "slug": c.get("slug"), "name": c.get("name"),
             "parent_id": c.get("parent_category_id"), "topic_count": c.get("topic_count"),
             "description": (c.get("description_text") or "").strip()[:100]}
            for c in site.get("categories") or []]


def _likes(post: dict) -> int:
    # Reason: linux.do 装了 discourse-reactions，actions_summary 里 id=2 的计数就是全部表情回应数
    for action in post.get("actions_summary") or []:
        if action.get("id") == 2:
            return int(action.get("count") or 0)
    return sum(int(r.get("count") or 0) for r in post.get("reactions") or [])


def topic_from(pre: dict, base: str) -> dict | None:
    topic = _decoded(pre, next((k for k in pre if k.startswith("topic_")), None))
    if not isinstance(topic, dict):
        return None
    tid = topic.get("id")
    stream = topic.get("post_stream") or {}
    ids, raw_posts = stream.get("stream") or [], stream.get("posts") or []
    chunk = int(topic.get("chunk_size") or 20)
    posts = [{
        "number": p.get("post_number"), "username": p.get("username"), "name": p.get("name") or "",
        "created": from_iso(p.get("created_at")), "reply_to": p.get("reply_to_post_number"),
        "likes": _likes(p),
        "reactions": {r.get("id"): r.get("count") for r in p.get("reactions") or [] if r.get("count")},
        "url": f"{base}/t/topic/{tid}/{p.get('post_number')}",
        "text": html_to_text(p.get("cooked") or "", base),
    } for p in raw_posts]
    first_id = raw_posts[0].get("id") if raw_posts else None
    page = ids.index(first_id) // chunk + 1 if first_id in ids else 1
    category = {c["id"]: c for c in categories_from(pre)}.get(topic.get("category_id")) or {}
    return {
        "id": tid, "title": topic.get("title"), "url": f"{base}/t/topic/{tid}",
        "category": category.get("name") or "", "category_id": topic.get("category_id"),
        "tags": [t.get("name") if isinstance(t, dict) else t for t in topic.get("tags") or []],
        "author": ((topic.get("details") or {}).get("created_by") or {}).get("username"),
        "created": from_iso(topic.get("created_at")), "last_posted": from_iso(topic.get("last_posted_at")),
        "posts_count": topic.get("posts_count"), "views": topic.get("views"),
        "like_count": topic.get("like_count"), "participants": topic.get("participant_count"),
        "closed": bool(topic.get("closed")), "archived": bool(topic.get("archived")),
        "pinned": bool(topic.get("pinned")),
        "page": page, "pages": max(1, math.ceil(len(ids) / chunk)), "posts": posts,
    }
