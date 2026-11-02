#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把日报 Markdown 发布成静态页，传到 shengkao.razet.me/daily/

用法：
  python3 publish.py --date 2026-11-02 --file /tmp/report.md
  cat report.md | python3 publish.py --date 2026-11-02
  python3 publish.py --rebuild-index        # 只重建索引页

生成：daily/<date>.html + daily/index.html，然后 rsync 到服务器。
"""
import argparse
import datetime as dt
import html
import pathlib
import re
import subprocess
import sys

HOST = 'root@47.115.163.124'
KEY = str(pathlib.Path.home() / '.ssh/server/work-m1-connect.pem')
REMOTE_DIR = '/var/www/shengkao/daily'
LOCAL_DIR = pathlib.Path.home() / '.workbuddy/data/daily_pages'

CSS = """
:root{--bg:#fbfaf7;--surface:#fff;--line:#e8e3da;--text:#2b2b28;--text-2:#5c5a54;--accent:#3f6b4f;--code:#f2efe8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans CJK SC",sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:24px 18px 60px}
h1{font-size:22px;margin:8px 0 20px;letter-spacing:-.3px}
h2{font-size:17px;margin:30px 0 10px;padding-left:10px;border-left:3px solid var(--accent)}
h3{font-size:15px;margin:22px 0 6px;color:var(--text-2)}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px;background:var(--surface);border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:#f4f1ea;font-weight:600;white-space:nowrap}
tr:last-child td{border-bottom:none}
blockquote{margin:10px 0;padding:10px 14px;background:var(--surface);border-left:3px solid var(--line);color:var(--text-2);font-size:14px;border-radius:0 6px 6px 0}
ul,ol{padding-left:22px;margin:8px 0}
li{margin:5px 0}
code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:13px}
strong{color:#1f4d33}
hr{border:0;border-top:1px solid var(--line);margin:24px 0}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:6px;font-size:13px;color:var(--text-2)}
.top a{color:var(--accent);text-decoration:none}
.nav{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}
.nav a{padding:6px 12px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--text-2);text-decoration:none;font-size:13px}
.nav a.on{border-color:var(--accent);color:#fff;background:var(--accent)}
.none{color:var(--text-2);font-size:14px}
"""


def inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'`(.+?)`', r'<code>\1</code>', s)
    return s


def md_to_html(text: str) -> str:
    out, i, lines = [], 0, text.split('\n')
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        # 表格
        if ln.lstrip().startswith('|') and i + 1 < len(lines) and re.match(r'^\s*\|[\s:|-]+\|', lines[i + 1]):
            head = [c.strip() for c in ln.strip().strip('|').split('|')]
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')])
                i += 1
            out.append('<table><thead><tr>' + ''.join(f'<th>{inline(c)}</th>' for c in head) + '</tr></thead><tbody>')
            for r in rows:
                out.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r) + '</tr>')
            out.append('</tbody></table>')
            continue
        # 标题
        m = re.match(r'^(#{1,3})\s+(.*)$', ln)
        if m:
            lvl = len(m.group(1))
            out.append(f'<h{lvl}>{inline(m.group(2))}</h{lvl}>')
            i += 1
            continue
        # 引用
        if ln.lstrip().startswith('>'):
            buf = []
            while i < len(lines) and lines[i].lstrip().startswith('>'):
                buf.append(lines[i].lstrip()[1:].strip())
                i += 1
            out.append('<blockquote>' + '<br>'.join(inline(x) for x in buf) + '</blockquote>')
            continue
        # 列表
        if re.match(r'^\s*[-*]\s+', ln) or re.match(r'^\s*\d+\.\s+', ln):
            ordered = bool(re.match(r'^\s*\d+\.\s+', ln))
            tag = 'ol' if ordered else 'ul'
            out.append(f'<{tag}>')
            while i < len(lines) and (re.match(r'^\s*[-*]\s+', lines[i]) or re.match(r'^\s*\d+\.\s+', lines[i])):
                item = re.sub(r'^\s*(?:[-*]|\d+\.)\s+', '', lines[i])
                out.append(f'<li>{inline(item)}</li>')
                i += 1
            out.append(f'</{tag}>')
            continue
        if ln.strip() == '---':
            out.append('<hr>')
            i += 1
            continue
        # 段落
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(r'^(#{1,3}\s|\s*[-*]\s|\s*\d+\.\s|>|\||---)', lines[i]):
            buf.append(lines[i].strip())
            i += 1
        out.append('<p>' + '<br>'.join(inline(x) for x in buf) + '</p>')
    return '\n'.join(out)


def page(title: str, body: str, nav: str = '') -> str:
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body><div class="wrap">{nav}{body}</div></body></html>"""


def build_index(pages: list) -> str:
    items = []
    for d, title in pages:
        tail = f'　<span class="none">{html.escape(title)}</span>' if title and title != d else ''
        items.append(f'<li><a href="{d}.html">{d}</a>{tail}</li>')
    body = ('<h1>华图刷题日报</h1>'
            + '<p class="none">每天 10:30 自动生成，共 ' + str(len(pages)) + ' 期</p>'
            + '<ul>' + ''.join(items) + '</ul>') if items else \
           '<h1>华图刷题日报</h1><p class="none">还没有日报。</p>'
    return page('华图刷题日报', body)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=dt.date.today().isoformat())
    ap.add_argument('--file')
    ap.add_argument('--rebuild-index', action='store_true')
    ap.add_argument('--no-upload', action='store_true')
    args = ap.parse_args()

    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    if not args.rebuild_index:
        text = pathlib.Path(args.file).read_text(encoding='utf-8') if args.file else sys.stdin.read()
        if not text.strip():
            print('内容为空，不发布', file=sys.stderr)
            return 1
        title = ''
        for ln in text.split('\n'):
            if ln.startswith('# '):
                title = ln[2:].strip()
                break
        nav = '<div class="top"><span>华图刷题日报</span><a href="index.html">全部期数</a></div>'
        (LOCAL_DIR / f'{args.date}.html').write_text(page(title or args.date, md_to_html(text), nav), encoding='utf-8')
        print(f'已生成 {args.date}.html')

    def title_of(path):
        try:
            h = path.read_text(encoding='utf-8')
            m = re.search(r'<title>(.*?)</title>', h)
            return (m.group(1) if m else '').replace('华图刷题日报 · ', '')
        except Exception:
            return ''

    pages = sorted([(p.stem, title_of(p)) for p in LOCAL_DIR.glob('*.html') if p.stem != 'index'],
                   reverse=True)[:60]
    (LOCAL_DIR / 'index.html').write_text(build_index(pages), encoding='utf-8')
    print(f'索引已更新，共 {len(pages)} 期')

    if args.no_upload:
        return 0
    cmd = ['rsync', '-az', '-e', f'ssh -i {KEY} -o BatchMode=yes -o StrictHostKeyChecking=no',
           f'{LOCAL_DIR}/', f'{HOST}:{REMOTE_DIR}/']
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print('上传失败：' + (r.stderr or '')[-300:], file=sys.stderr)
        return 2
    print('已上传 → https://shengkao.razet.me/daily/')
    return 0


if __name__ == '__main__':
    sys.exit(main())
