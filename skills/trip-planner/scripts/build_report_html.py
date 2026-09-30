#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_report_html.py — 把攻略 Markdown 与行程地图合成**单个自包含 HTML**。

为什么不复用上游的 md_to_html.py：它在 Python 3.12 以下有语法错误
（f-string 表达式里含反斜杠），本机 3.10 直接 SyntaxError，跑不起来。
本脚本自带一个够用的 GFM 子集渲染器，不依赖任何第三方库。

地图用 <iframe srcdoc> 内嵌：地图 HTML 一字不改地放进属性里，
交互（按天筛选/点击飞至/搜索）全部保留，样式与正文完全隔离，
且 srcdoc 继承父文档 origin，file:// 下高德 JS API 仍能正常加载。

用法:
  python3 build_report_html.py <report.md> <output.html> [--map <map.html>]

Markdown 里写 {{TRIP_MAP}} 标记地图插入位置；没有该标记则追加到文末。

支持的 Markdown 子集（够写攻略）：
  # ~ #### 标题 / GFM 表格（含对齐）/ 有序无序列表 / 引用 / 分隔线
  **粗体** / `代码` / [链接](url) / 段落 / 保留 <br>
"""
import argparse
import html as html_mod
import os
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

MAP_SLOT = "{{TRIP_MAP}}"

CSS = """
:root{--ink:#1f2329;--muted:#6b7280;--border:#e5e7eb;--accent:#1565c0;--bg:#f6f7f9}
*{box-sizing:border-box}
body{margin:0;padding:0;background:var(--bg);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Segoe UI",Roboto,sans-serif;
  line-height:1.75;font-size:15px}
.wrap{max-width:980px;margin:0 auto;padding:32px 24px 80px;background:#fff;
  box-shadow:0 1px 3px rgba(0,0,0,.06);min-height:100vh}
h1{font-size:26px;font-weight:700;margin:0 0 20px;padding-bottom:14px;
  border-bottom:3px solid var(--accent)}
h2{font-size:20px;font-weight:700;margin:34px 0 14px;padding-left:11px;
  border-left:4px solid var(--accent)}
h3{font-size:17px;font-weight:600;margin:24px 0 10px}
h4{font-size:15px;font-weight:600;margin:18px 0 8px;color:var(--muted)}
p{margin:10px 0}
/* 同程原文表格很宽，容器横向滚动而不是压缩列宽 */
.tw{overflow-x:auto;margin:14px 0;border:1px solid var(--border);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:13.5px;background:#fff}
th,td{border-bottom:1px solid var(--border);border-right:1px solid var(--border);
  padding:8px 11px;text-align:left;vertical-align:top}
th{background:#fafbfc;font-weight:600;white-space:nowrap;position:sticky;top:0}
tr:last-child td{border-bottom:none}
th:last-child,td:last-child{border-right:none}
tbody tr:hover{background:#fafbfc}
td.r,th.r{text-align:right}
blockquote{margin:14px 0;padding:10px 16px;background:#f8f9fa;
  border-left:4px solid #cbd5e1;color:#475569;border-radius:0 6px 6px 0}
blockquote p{margin:4px 0}
ul,ol{margin:10px 0;padding-left:24px}
li{margin:5px 0}
code{background:#f1f3f5;padding:2px 6px;border-radius:4px;font-size:.9em;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
hr{border:none;border-top:1px solid var(--border);margin:26px 0}
strong{font-weight:600}
.mapbox{margin:16px 0}
.mapbox iframe{width:100%;height:660px;border:1px solid var(--border);
  border-radius:8px;background:#fff;display:block}
.maphint{font-size:12.5px;color:var(--muted);margin-top:7px}
@media(max-width:768px){
  .wrap{padding:20px 14px 60px}
  h1{font-size:21px}h2{font-size:18px}
  body{font-size:14px}
  .mapbox iframe{height:520px}
}
@media print{
  body{background:#fff}.wrap{box-shadow:none;max-width:none}
  .mapbox iframe{height:420px}
  h2{break-after:avoid}.tw{break-inside:avoid}
}
"""


def _inline(text):
    """行内格式化。先整体转义，再放行 <br> 与我们自己生成的标签。"""
    out = html_mod.escape(text, quote=False)
    out = out.replace("&lt;br&gt;", "<br>").replace("&lt;br/&gt;", "<br>")
    # 顺序要紧：代码优先，避免其内部的 * 和 [] 被当作格式符
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)",
                 r'<a href="\2" target="_blank" rel="noopener">\1</a>', out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", out)
    return out


def _split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_align_row(line):
    return bool(re.match(r"^\|[\s:\-|]+\|?\s*$", line.strip())) and "-" in line


def _aligns(line):
    """从对齐行解析每列对齐方式，只区分右对齐（金额列常用）与其他。"""
    out = []
    for cell in _split_row(line):
        out.append("r" if cell.endswith(":") and not cell.startswith(":") else "")
    return out


def render_markdown(md):
    """把 Markdown 子集渲染为 HTML 片段。"""
    lines = md.split("\n")
    out = []
    i, n = 0, len(lines)
    list_stack = []          # 'ul' / 'ol'
    in_para = False

    def close_para():
        nonlocal in_para
        if in_para:
            out.append("</p>")
            in_para = False

    def close_lists():
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    def close_all():
        close_para()
        close_lists()

    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            close_all()
            i += 1
            continue

        # 地图占位符单独成段
        if stripped == MAP_SLOT:
            close_all()
            out.append(MAP_SLOT)
            i += 1
            continue

        # 表格：当前行以 | 开头且下一行是对齐行
        if stripped.startswith("|") and i + 1 < n and _is_align_row(lines[i + 1]):
            close_all()
            headers = _split_row(stripped)
            aligns = _aligns(lines[i + 1])
            aligns += [""] * (len(headers) - len(aligns))
            out.append('<div class="tw"><table><thead><tr>')
            for idx, cell in enumerate(headers):
                cls = f' class="{aligns[idx]}"' if aligns[idx] else ""
                out.append(f"<th{cls}>{_inline(cell)}</th>")
            out.append("</tr></thead><tbody>")
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                cells = _split_row(lines[i].strip())
                out.append("<tr>")
                for idx, cell in enumerate(cells):
                    cls = f' class="{aligns[idx]}"' if idx < len(aligns) and aligns[idx] else ""
                    out.append(f"<td{cls}>{_inline(cell)}</td>")
                out.append("</tr>")
                i += 1
            out.append("</tbody></table></div>")
            continue

        # 标题
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            close_all()
            level = min(len(heading.group(1)), 4)
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        # 分隔线
        if re.match(r"^([-*_])\1{2,}$", stripped.replace(" ", "")):
            close_all()
            out.append("<hr>")
            i += 1
            continue

        # 引用（连续行合并为一个 blockquote）
        if stripped.startswith(">"):
            close_all()
            out.append("<blockquote>")
            while i < n and lines[i].strip().startswith(">"):
                text = re.sub(r"^>\s?", "", lines[i].strip())
                out.append(f"<p>{_inline(text)}</p>" if text else "")
                i += 1
            out.append("</blockquote>")
            continue

        # 列表
        ul = re.match(r"^[-*+]\s+(.*)$", stripped)
        ol = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if ul or ol:
            close_para()
            want = "ul" if ul else "ol"
            if not list_stack:
                out.append(f"<{want}>")
                list_stack.append(want)
            elif list_stack[-1] != want:
                out.append(f"</{list_stack.pop()}>")
                out.append(f"<{want}>")
                list_stack.append(want)
            content = (ul or ol).group(1)
            i += 1
            # Reason: 吸收缩进续行（Markdown lazy continuation）。不处理的话
            # 「- 条目第一行\n  第二行」会把第二行变成独立段落并中断列表。
            # 缩进后又是列表符号的属于嵌套列表，留给下一轮处理，不吸收。
            while i < n and lines[i].strip():
                nxt = lines[i]
                if re.match(r"^\s{2,}\S", nxt) and not re.match(r"^\s*([-*+]|\d+[.)])\s", nxt):
                    content += " " + nxt.strip()
                    i += 1
                else:
                    break
            out.append(f"<li>{_inline(content)}</li>")
            continue

        # 普通段落
        close_lists()
        if not in_para:
            out.append("<p>")
            in_para = True
        else:
            out.append("<br>")
        out.append(_inline(stripped))
        i += 1

    close_all()
    return "\n".join(x for x in out if x != "")


def build_map_block(map_path):
    """把地图 HTML 原样塞进 iframe srcdoc。"""
    with open(map_path, encoding="utf-8") as fp:
        map_html = fp.read()
    # srcdoc 是 HTML 属性：& 与 " 必须转义，其余原样保留
    escaped = map_html.replace("&", "&amp;").replace('"', "&quot;")
    return (
        '<div class="mapbox">'
        f'<iframe srcdoc="{escaped}" '
        'sandbox="allow-scripts allow-popups allow-same-origin" '
        'title="行程地图" loading="lazy"></iframe>'
        '<div class="maphint">地图已内嵌于本文件，可按天筛选、点击卡片飞至；'
        '连线为站点直连用于示意方向，不是实际驾驶路径。</div>'
        "</div>"
    )


def main():
    parser = argparse.ArgumentParser(description="攻略 Markdown + 地图 → 单文件 HTML")
    parser.add_argument("report_md", help="攻略 Markdown")
    parser.add_argument("output_html", help="输出的单文件 HTML")
    parser.add_argument("--map", dest="map_html", help="行程地图 HTML（可选）")
    parser.add_argument("--title", help="页面标题，默认取 Markdown 的一级标题")
    args = parser.parse_args()

    if not os.path.exists(args.report_md):
        print(f"❌ 文件不存在：{args.report_md}", file=sys.stderr)
        return 1
    if args.map_html and not os.path.exists(args.map_html):
        print(f"❌ 地图文件不存在：{args.map_html}", file=sys.stderr)
        return 1

    with open(args.report_md, encoding="utf-8") as fp:
        md = fp.read()

    title = args.title
    if not title:
        first = re.search(r"^#\s+(.*)$", md, re.M)
        title = first.group(1).strip() if first else "行程攻略"

    body = render_markdown(md)

    if args.map_html:
        block = build_map_block(args.map_html)
        if MAP_SLOT in body:
            body = body.replace(MAP_SLOT, block)
        else:
            body += f"\n<h2>行程地图</h2>\n{block}"
            print(f"ℹ️  未找到 {MAP_SLOT} 占位符，地图已追加到文末")
    else:
        body = body.replace(MAP_SLOT, "")

    page = (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n"
        "<meta charset=\"UTF-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        f"<title>{html_mod.escape(title)}</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n"
        f"<div class=\"wrap\">\n{body}\n</div>\n</body>\n</html>\n"
    )

    with open(args.output_html, "w", encoding="utf-8") as fp:
        fp.write(page)

    size_kb = os.path.getsize(args.output_html) / 1024
    print(f"✅ {args.output_html}")
    print(f"   大小 {size_kb:.0f}KB · 表格 {body.count('<table')} 个 · "
          f"地图 {'已内嵌' if args.map_html else '未包含'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
