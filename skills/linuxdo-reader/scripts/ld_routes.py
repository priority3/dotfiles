"""出口线路：system（系统代理）→ clash（独立 mihomo 轮换节点）→ pool（HTTP 代理池）。

只在请求失败时换线（被动故障转移），不做主动轮换来分摊请求量。
"""

from __future__ import annotations

import glob
import os
import random
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass

from ld_config import CLASH_VERGE_DIR, State
from ld_mihomo import MihomoError, PrivateMihomo, find_binary, find_source


def log(msg: str) -> None:
    print(f"[linuxdo] {msg}", file=sys.stderr, flush=True)


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds >= 3600:
        return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


@dataclass
class Route:
    key: str            # 状态文件里的键：system / direct / clash:<节点名> / pool:<host>:<port>
    kind: str           # system | direct | clash | pool
    proxy: str | None   # 传给 curl 的代理；None 表示直连
    label: str          # 可打印的名字（已脱敏，不含账号密码）
    source: str = ""    # pool 线路所属的代理池文件


def host_port(url: str) -> str:
    parts = urllib.parse.urlsplit(url if "://" in url else f"http://{url}")
    return f"{parts.hostname}:{parts.port}" if parts.hostname else "?"


def system_proxy(cfg: dict) -> str | None:
    """系统代理：配置 > 环境变量 > Clash Verge 的 mixed-port；都没有就直连。"""
    if cfg.get("system_proxy"):
        return cfg["system_proxy"]
    for var in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        text = (CLASH_VERGE_DIR / "config.yaml").read_text("utf-8")
        match = re.search(r"^mixed-port:\s*(\d+)", text, re.M)
    except OSError:
        match = None
    return f"http://127.0.0.1:{match.group(1)}" if match else None


def normalize_proxy(line: str) -> str | None:
    """支持 scheme://user:pass@host:port、host:port、host:port:user:pass 三种写法。"""
    line = line.strip()  # Reason: 顺带去掉 CRLF 文件残留的 \r——Downloads 里那份代理池就是 CRLF
    if not line or line.startswith("#"):
        return None
    if "://" in line:
        return line
    parts = line.split(":")
    if len(parts) == 4 and parts[1].isdigit():
        host, port, user, pwd = parts
        return f"http://{urllib.parse.quote(user, safe='')}:{urllib.parse.quote(pwd, safe='')}@{host}:{port}"
    if len(parts) == 2 and parts[1].isdigit():
        return f"http://{line}"
    return None


def load_pool(patterns: list[str]) -> list[tuple[str, str]]:
    """读取代理池文件，返回 [(文件路径, 代理 URL)]，按 URL 去重。"""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for pattern in patterns:
        for path in sorted(glob.glob(os.path.expanduser(pattern))):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    lines = fh.read().splitlines()
            except OSError:
                continue
            for line in lines:
                url = normalize_proxy(line)
                if url and url not in seen:
                    seen.add(url)
                    out.append((path, url))
    return out


class RoutePlanner:
    def __init__(self, cfg: dict, state: State, only: str | None = None):
        self.cfg, self.state = cfg, state
        self.order = [only] if only else list(cfg["routes"])
        self.mihomo: PrivateMihomo | None = None
        self._pool_conn_fails: dict[str, int] = {}

    def candidates(self):
        """按顺序惰性产出可用线路（跳过冷却中的）；clash 线路真正轮到时才启动独立 mihomo。"""
        for kind in self.order:
            if kind in ("system", "direct"):
                yield from self._system(kind)
            elif kind == "clash":
                yield from self._clash()
            elif kind == "pool":
                yield from self._pool()
            else:
                log(f"未知线路类型「{kind}」，已忽略")

    def _skip_cooling(self, key: str, bucket: str = "routes") -> bool:
        entry = self.state.cooling(key, bucket)
        if entry:
            log(f"跳过 {os.path.basename(key)}：冷却中（{entry['reason']}，还剩 {fmt_duration(entry['until'] - time.time())}）")
        return bool(entry)

    def _system(self, kind: str):
        proxy = None if kind == "direct" else system_proxy(self.cfg)
        if proxy:
            route = Route("system", "system", proxy, f"system({host_port(proxy)})")
        else:
            route = Route("direct", "direct", None, "direct")
        if not self._skip_cooling(route.key):
            yield route

    def _clash(self):
        ccfg = self.cfg["clash"]
        binary, source = find_binary(ccfg.get("binary", "")), find_source(ccfg.get("source_config", ""))
        if not binary or not source:
            log("clash 线路不可用：未找到 mihomo 内核或 Clash Verge 运行时配置（clash-verge.yaml）")
            return
        if self._skip_cooling("clash-tier"):
            return
        if self.mihomo is None:
            mihomo = PrivateMihomo(binary, source, ccfg.get("include", ""), ccfg.get("exclude", ""))
            try:
                mihomo.start()
            except (MihomoError, OSError) as exc:
                log(f"clash 线路不可用：{exc}")
                self.state.cool("clash-tier", 600, str(exc)[:160])
                return
            self.mihomo = mihomo
            log(f"已启动独立 mihomo（{len(mihomo.nodes)} 个节点，只承载本脚本的请求）")
        nodes = self.mihomo.nodes
        start = int(self.state.data.get("clash_cursor", 0)) % len(nodes)
        skipped = 0
        for offset in range(len(nodes)):
            idx = (start + offset) % len(nodes)
            key = f"clash:{nodes[idx]}"
            if self.state.cooling(key):
                skipped += 1
                continue
            try:
                self.mihomo.select(nodes[idx])
            except (MihomoError, OSError) as exc:
                log(f"切换节点失败 {nodes[idx]}：{exc}")
                self.state.cool(key, self.cfg["cooldown"]["error"], "select failed")
                continue
            self.state.data["clash_cursor"] = idx
            if skipped:
                log(f"跳过 {skipped} 个冷却中的节点")
                skipped = 0
            yield Route(key, "clash", self.mihomo.proxy_url, key)
        if skipped:
            log(f"clash 线路：剩余 {skipped} 个节点都在冷却中")

    def _pool(self):
        pcfg = self.cfg["pool"]
        entries = load_pool(pcfg.get("files", []))
        live_files = {p for p in {path for path, _ in entries} if not self._skip_cooling(p, "pool_files")}
        entries = [(path, url) for path, url in entries if path in live_files]
        if not entries:
            log("pool 线路不可用：没有可用的代理池文件（未配置、为空或整池暂停中）")
            return
        random.shuffle(entries)
        tried = 0
        for path, url in entries:
            key = f"pool:{host_port(url)}"
            # 本轮可能刚把整个文件判定为不可用，所以每次都重新检查
            if self.state.cooling(path, "pool_files") or self.state.cooling(key):
                continue
            tried += 1
            if tried > int(pcfg.get("max_tries", 4)):
                return
            yield Route(key, "pool", url, key, source=path)

    def penalize(self, route: Route, outcome: str, seconds: float, detail: str) -> None:
        cd = self.cfg["cooldown"]
        name = os.path.basename(route.source)
        if route.kind == "pool" and outcome == "proxy_exhausted":
            # Reason: 代理商对 CONNECT 回 402/407/429 是账号级问题（流量耗尽/鉴权失败），同文件其余代理必然一样
            self.state.cool(route.source, cd["pool_exhausted"], detail, "pool_files")
            log(f"代理池 {name} 整池暂停 {fmt_duration(cd['pool_exhausted'])}：{detail}")
            return
        if route.kind == "pool" and outcome == "proxy_error":
            fails = self._pool_conn_fails.get(route.source, 0) + 1
            self._pool_conn_fails[route.source] = fails
            seconds = cd["proxy_dead"]
            if fails >= 3:
                self.state.cool(route.source, cd["proxy_dead"], f"连续 {fails} 个代理连不上", "pool_files")
                log(f"代理池 {name} 连续 {fails} 个代理连不上，整池暂停 {fmt_duration(cd['proxy_dead'])}")
        if route.kind == "clash":
            # 下次从下一个节点开始，别在同一个坏节点上反复试
            self.state.data["clash_cursor"] = int(self.state.data.get("clash_cursor", 0)) + 1
        self.state.cool(route.key, seconds, f"{outcome}: {detail}"[:160])

    def close(self) -> None:
        if self.mihomo:
            self.mihomo.stop()
            self.mihomo = None
