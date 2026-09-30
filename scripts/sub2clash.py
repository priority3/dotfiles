#!/usr/bin/env python3
"""通用 base64 订阅 -> Clash(mihomo) 配置转换器。

用途：部分机场后端不做格式分发（忽略 ?flag=clash，永远返回 v2ray 风格的
base64 节点列表），导致 Clash Verge 无法直接订阅。本脚本在本地完成转换。

用法:
    python3 sub2clash.py <订阅URL> [-o 输出路径] [--chain]

依赖：仅标准库（macOS 自带 python3 即可，无需 pip install）。
"""

import argparse
import base64
import json
import sys
import urllib.parse
import urllib.request

UA = "clash-verge/v2.3.1"


# ---------------------------------------------------------------- 抓取 / 解码

def fetch(url: str) -> tuple[str, dict]:
    """拉取订阅，返回 (正文, 响应头)。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace"), dict(resp.headers)


def b64_decode(text: str) -> str:
    """解码订阅正文。已经是明文链接列表时原样返回。"""
    stripped = "".join(text.split())
    if "://" in text and not stripped.endswith("="):
        # Reason: 已是明文 URL 列表（部分后端直接返回未编码内容）
        if any(line.strip().startswith(("hysteria2://", "vless://", "ss://"))
               for line in text.splitlines()):
            return text
    # urlsafe 变体 + 补齐 padding
    stripped = stripped.replace("-", "+").replace("_", "/")
    stripped += "=" * (-len(stripped) % 4)
    return base64.b64decode(stripped).decode("utf-8", "replace")


# ---------------------------------------------------------------- 节点解析

def parse_hysteria2(url: str) -> dict:
    u = urllib.parse.urlsplit(url)
    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
    name = urllib.parse.unquote(u.fragment) or f"{u.hostname}:{u.port}"

    node = {
        "name": name,
        "type": "hysteria2",
        "server": u.hostname,
        "port": u.port,
        "password": urllib.parse.unquote(u.username or ""),
        "udp": True,
    }
    if q.get("sni"):
        node["sni"] = q["sni"]
    if q.get("obfs"):
        node["obfs"] = q["obfs"]
        # 混淆密码在不同后端有两种键名
        pwd = q.get("obfs-password") or q.get("obfs_password")
        if not pwd and q.get("fm"):
            # Reason: 部分后端把混淆密码塞在 fm 这个 JSON 字段里而不是独立参数
            try:
                fm = json.loads(urllib.parse.unquote(q["fm"]))
                for entry in fm.get("udp", []):
                    pwd = entry.get("settings", {}).get("password") or pwd
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
        if pwd:
            node["obfs-password"] = pwd
    if q.get("alpn"):
        node["alpn"] = q["alpn"].split(",")
    node["skip-cert-verify"] = q.get("insecure", "0") in ("1", "true")
    return node


PARSERS = {"hysteria2": parse_hysteria2, "hy2": parse_hysteria2}


def parse_nodes(text: str) -> list[dict]:
    nodes, unsupported = [], set()
    for line in text.splitlines():
        line = line.strip()
        if not line or "://" not in line:
            continue
        scheme = line.split("://", 1)[0].lower()
        parser = PARSERS.get(scheme)
        if parser is None:
            unsupported.add(scheme)
            continue
        nodes.append(parser(line))

    if unsupported:
        # Reason: 静默丢弃节点会让用户以为转换成功，必须显式报错
        sys.exit(f"错误：订阅含本脚本未支持的协议 {sorted(unsupported)}，"
                 f"请扩展 PARSERS 后重试（已解析 {len(nodes)} 个）")

    # 去重：mihomo 遇到同名节点会直接启动失败
    seen, deduped = {}, []
    for n in nodes:
        base = n["name"]
        if base in seen:
            seen[base] += 1
            n["name"] = f"{base} #{seen[base]}"
        else:
            seen[base] = 1
        deduped.append(n)
    return deduped


# ---------------------------------------------------------------- YAML 输出

def yq(value) -> str:
    """标量转 YAML 字面量。字符串一律双引号，避免 emoji / 冒号 / 破折号踩坑。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_js(nodes: list[dict]) -> str:
    """输出可直接内联进 Clash Verge 扩展脚本的 JS 数组字面量。

    Reason: Clash Verge 的扩展脚本运行在无网络的沙箱里，拿不到订阅，
    所以节点必须硬编码；本函数负责生成这段可粘贴的代码。
    """
    lines = ["const CCWU_NODES = ["]
    for n in nodes:
        fields = [f'name: {json.dumps(n["name"], ensure_ascii=False)}',
                  f'type: "{n["type"]}"',
                  f'server: "{n["server"]}"',
                  f'port: {n["port"]}',
                  f'password: {json.dumps(n["password"])}']
        if "obfs" in n:
            fields.append(f'obfs: "{n["obfs"]}"')
        if "obfs-password" in n:
            fields.append(f'"obfs-password": {json.dumps(n["obfs-password"])}')
        if "sni" in n:
            fields.append(f'sni: "{n["sni"]}"')
        if "alpn" in n:
            fields.append(f'alpn: {json.dumps(n["alpn"])}')
        fields.append(f'"skip-cert-verify": {str(n.get("skip-cert-verify", False)).lower()}')
        fields.append("udp: true")
        lines.append("  { " + ", ".join(fields) + " },")
    lines.append("];")
    return "\n".join(lines)


def render(nodes: list[dict], chain: bool) -> str:
    names = [n["name"] for n in nodes]
    out = [
        "# 由 scripts/sub2clash.py 自动生成，请勿手工编辑（重跑脚本即可刷新）",
        "# 含订阅凭据，切勿提交到 git 或分享",
        "",
        "mixed-port: 7897",
        "allow-lan: false",
        "mode: rule",
        "log-level: info",
        "ipv6: false",
        "external-controller: 127.0.0.1:9097",
        "unified-delay: true",
        "tcp-concurrent: true",
        "",
        "proxies:",
    ]

    key_order = ["name", "type", "server", "port", "password", "obfs",
                 "obfs-password", "sni", "alpn", "skip-cert-verify", "udp"]
    for n in nodes:
        first = True
        for key in key_order:
            if key not in n:
                continue
            prefix = "  - " if first else "    "
            first = False
            if key == "alpn":
                out.append(f"{prefix}alpn: [{', '.join(yq(a) for a in n['alpn'])}]")
            else:
                out.append(f"{prefix}{key}: {yq(n[key])}")

    out.append("")
    out.append("proxy-groups:")

    def group(name, gtype, members, **extra):
        out.append(f"  - name: {yq(name)}")
        out.append(f"    type: {gtype}")
        for k, v in extra.items():
            out.append(f"    {k.replace('_', '-')}: {yq(v)}")
        out.append("    proxies:")
        out.extend(f"      - {yq(m)}" for m in members)

    if chain:
        # 前置链：落地组的每条连接先经由前置组建立
        group("🔗 前置入口", "select", ["DIRECT", *names])
        group("🎯 落地出口", "select", names, dialer_proxy="🔗 前置入口")
        group("🚀 节点选择", "select", ["🎯 落地出口", "♻️ 自动选择", "DIRECT", *names])
    else:
        group("🚀 节点选择", "select", ["♻️ 自动选择", "DIRECT", *names])

    group("♻️ 自动选择", "url-test", names,
          url="https://www.gstatic.com/generate_204")
    out.append("    interval: 300")
    out.append("    tolerance: 50")

    group("🐟 漏网之鱼", "select", ["🚀 节点选择", "DIRECT"])

    out += [
        "",
        "rules:",
        "  - GEOIP,lan,DIRECT,no-resolve",
        "  - GEOIP,private,DIRECT,no-resolve",
        "  - GEOSITE,private,DIRECT",
        "  - GEOSITE,cn,DIRECT",
        "  - GEOIP,CN,DIRECT",
        "  - MATCH,🐟 漏网之鱼",
        "",
    ]
    return "\n".join(out)


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description="通用 base64 订阅 -> Clash(mihomo) 配置")
    ap.add_argument("url", help="订阅链接")
    ap.add_argument("-o", "--output", default="-", help="输出文件路径，默认 stdout")
    ap.add_argument("--chain", action="store_true",
                    help="生成前置链（dialer-proxy）策略组")
    ap.add_argument("--format", choices=["clash", "js"], default="clash",
                    help="clash=完整配置文件；js=可内联进 Clash Verge 扩展脚本的节点数组")
    args = ap.parse_args()

    body, headers = fetch(args.url)
    nodes = parse_nodes(b64_decode(body))
    if not nodes:
        sys.exit("错误：订阅中未解析到任何节点")

    yaml_text = render_js(nodes) if args.format == "js" else render(nodes, args.chain)
    if args.output == "-":
        print(yaml_text)
    else:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(yaml_text)

    info = headers.get("subscription-userinfo", "")
    print(f"✓ {len(nodes)} 个节点 -> {args.output}", file=sys.stderr)
    if info:
        used = {}
        for part in info.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                used[k.strip()] = int(v.strip() or 0)
        total_gb = (used.get("upload", 0) + used.get("download", 0)) / 1024 ** 3
        print(f"  已用流量 {total_gb:.1f} GiB", file=sys.stderr)


if __name__ == "__main__":
    main()
