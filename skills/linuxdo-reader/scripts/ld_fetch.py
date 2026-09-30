"""请求层：curl 执行、全局节流、响应缓存、失败分类与换线重试。

Reason: 用 curl 而不用 urllib——2026-09-30 同一出口实测，curl 返回 200，而 Python urllib
无论什么 UA 都会被 Cloudflare 403 挑战（差别在客户端指纹）。本模块不做指纹伪装、不求解挑战：
429 限频时冷却当前出口并换线；403 挑战直接停止报告（换出口也过不去）；全部失败就如实报错。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime

from ld_config import HTTP_CACHE_DIR, RequestLock, State
from ld_routes import Route, RoutePlanner, fmt_duration, log

EXIT_NOT_FOUND = 3
EXIT_ALL_FAILED = 4
EXIT_CHALLENGED = 6

OUTCOME_ZH = {
    "ok": "成功",
    "not_found": "不存在或需登录",
    "forbidden": "无权限",
    "rate_limited": "429 限频",
    "challenged": "Cloudflare 挑战",
    "proxy_error": "线路不通",
    "proxy_exhausted": "代理不可用（流量耗尽/鉴权失败）",
    "server_error": "服务端错误",
    "bad_body": "返回内容异常",
    "unexpected": "意外响应",
}

_ACCEPT = {
    "rss": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    "html": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_CACHE_KEEP = 200


class FetchError(Exception):
    def __init__(self, message: str, exit_code: int, attempts: list[dict]):
        super().__init__(message)
        self.exit_code = exit_code
        self.attempts = attempts


@dataclass
class Response:
    url: str
    status: int
    body: str
    route: str
    cached: bool = False
    age: float = 0.0


@dataclass
class _Raw:
    exit: int
    code: int
    connect: int
    headers: dict = field(default_factory=dict)
    body: str = ""
    stderr: str = ""
    elapsed: float = 0.0


def _curl_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _last_headers(text: str) -> dict:
    """-D 文件里可能先有代理的 CONNECT 响应和重定向，只取最后一个响应块。"""
    blocks = [b for b in re.split(r"\r?\n\r?\n", text) if b.lstrip().startswith("HTTP/")]
    headers: dict = {}
    if blocks:
        for line in blocks[-1].splitlines()[1:]:
            name, sep, value = line.partition(":")
            if sep:
                headers[name.strip().lower()] = value.strip()
    return headers


def run_curl(url: str, route: Route, cfg: dict, kind: str) -> _Raw:
    with tempfile.TemporaryDirectory(prefix="linuxdo-") as tmp:
        hdr_file, body_file = os.path.join(tmp, "headers"), os.path.join(tmp, "body")
        args = ["curl", "-sS", "-L", "--max-redirs", "3", "--compressed",
                "-m", str(cfg["timeout"]), "--connect-timeout", "10",
                "-A", cfg["user_agent"], "-H", f"Accept: {_ACCEPT[kind]}",
                "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
                "-D", hdr_file, "-o", body_file, "-w", "%{http_code} %{http_connect}",
                "-K", "-", url]
        # Reason: 代理 URL 可能带账号密码，经 stdin 的 curl 配置传入，不出现在 ps 能看到的命令行里
        conf = f"proxy = {_curl_quote(route.proxy)}\n" if route.proxy else 'noproxy = "*"\n'
        start = time.time()
        proc = subprocess.run(args, input=conf, capture_output=True, text=True)
        codes = (proc.stdout.split() + ["0", "0"])[:2]
        raw = _Raw(exit=proc.returncode,
                   code=int(codes[0]) if codes[0].isdigit() else 0,
                   connect=int(codes[1]) if codes[1].isdigit() else 0,
                   stderr=proc.stderr, elapsed=time.time() - start)
        try:
            with open(hdr_file, encoding="latin-1") as fh:
                raw.headers = _last_headers(fh.read())
            with open(body_file, encoding="utf-8", errors="replace") as fh:
                raw.body = fh.read()
        except OSError:
            pass
        return raw


def _retry_after(raw: _Raw) -> int:
    value = raw.headers.get("retry-after", "")
    if value.isdigit():
        return int(value)
    if value:
        try:
            return max(0, int(parsedate_to_datetime(value).timestamp() - time.time()))
        except (TypeError, ValueError):
            pass
    match = re.search(r'"wait_seconds"\s*:\s*(\d+)', raw.body[:4000])  # Discourse 自己的限频响应
    return int(match.group(1)) if match else 0


def classify(raw: _Raw, route: Route, kind: str, cd: dict) -> tuple[str, float, str]:
    """把一次 curl 结果归类为 (结局, 该线路冷却秒数, 说明)。"""
    if raw.code == 0:
        if route.proxy and raw.connect not in (0, 200):
            detail = f"代理拒绝 CONNECT（HTTP {raw.connect}）"
            if route.kind == "pool" and raw.connect in (402, 407, 429):
                return "proxy_exhausted", cd["pool_exhausted"], detail
            return "proxy_error", cd["error"], detail
        err = raw.stderr.strip().splitlines()[-1] if raw.stderr.strip() else ""
        return "proxy_error", cd["error"], f"curl exit {raw.exit} {err[:120]}".strip()
    head = raw.body[:4000]
    challenge = raw.headers.get("cf-mitigated") == "challenge" or (
        raw.code in (403, 429, 503) and "Just a moment" in head)
    if raw.code == 429:
        wait = _retry_after(raw)
        seconds = max(60, wait) if wait else cd["rate_limited"]
        return "rate_limited", seconds, "HTTP 429" + ("（Cloudflare 挑战页）" if challenge else "")
    if challenge:
        return "challenged", 0, f"HTTP {raw.code}（Cloudflare 挑战页）"
    if raw.code in (404, 410):
        return "not_found", 0, f"HTTP {raw.code}：内容不存在，或需要登录才能看"
    if raw.code in (401, 403):
        return "forbidden", 0, f"HTTP {raw.code}：无权限（私有内容需要登录）"
    if raw.code >= 500:
        return "server_error", cd["server_error"], f"HTTP {raw.code}"
    if raw.code == 200:
        if kind == "rss" and "<rss" not in head:
            return "bad_body", cd["error"], "返回的不是 RSS"
        return "ok", 0, ""
    return "unexpected", cd["error"], f"HTTP {raw.code}"


def _cache_file(url: str, kind: str):
    return HTTP_CACHE_DIR / (hashlib.sha1(f"{kind} {url}".encode("utf-8")).hexdigest() + ".json")


def cache_get(url: str, kind: str, ttl: float) -> Response | None:
    path = _cache_file(url, kind)
    try:
        age = time.time() - path.stat().st_mtime
        if age > ttl:
            return None
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return Response(url, data["status"], data["body"], data["route"], cached=True, age=age)


def cache_put(url: str, kind: str, resp: Response) -> None:
    HTTP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"url": url, "status": resp.status, "route": resp.route, "body": resp.body}
    _cache_file(url, kind).write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
    files = sorted(HTTP_CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for old in files[:-_CACHE_KEEP]:
        old.unlink(missing_ok=True)


class Fetcher:
    """进程内唯一的请求入口：首次联网时才拿锁、载入状态、建线路规划器；close() 负责收尾。"""

    def __init__(self, cfg: dict, only_route: str | None = None, use_cache: bool = True):
        self.cfg, self.only, self.use_cache = cfg, only_route, use_cache
        self.lock: RequestLock | None = None
        self.state: State | None = None
        self.planner: RoutePlanner | None = None

    def _ensure(self) -> None:
        if self.state is None:
            self.lock = RequestLock()
            self.lock.acquire()
            self.state = State.load()
            self.planner = RoutePlanner(self.cfg, self.state, self.only)

    def close(self) -> None:
        if self.planner:
            self.planner.close()
        if self.state:
            self.state.save()
        if self.lock:
            self.lock.release()
        self.lock = self.state = self.planner = None

    def get(self, path: str, kind: str = "rss") -> Response:
        url = path if path.startswith("http") else self.cfg["base_url"] + path
        short = url.replace(self.cfg["base_url"], "") or "/"
        ttl = self.cfg["cache_ttl"].get(kind, 0)
        if self.use_cache and ttl:
            hit = cache_get(url, kind, ttl)
            if hit:
                log(f"GET {short} ← 缓存（{fmt_duration(hit.age)}前，经 {hit.route}）")
                return hit
        self._ensure()
        cd = self.cfg["cooldown"]
        attempts: list[dict] = []
        site_hits = conn_fails = 0
        last_site_outcome = ""
        for route in self.planner.candidates():
            self._pace()
            raw = run_curl(url, route, self.cfg, kind)
            reached = raw.code != 0  # 拿到了 HTTP 响应 = 请求确实打到了 linux.do，计入节流
            if reached:
                self.state.data["last_request_at"] = time.time()
            outcome, seconds, detail = classify(raw, route, kind, cd)
            attempts.append({"route": route.label, "outcome": outcome, "detail": detail})
            if outcome == "ok":
                log(f"GET {short} via {route.label} → 200（{raw.elapsed:.1f}s）")
                self.state.save()
                resp = Response(url, raw.code, raw.body, route.label)
                cache_put(url, kind, resp)
                return resp
            if outcome in ("not_found", "forbidden"):
                self.state.save()
                raise FetchError(f"{short}：{detail}", EXIT_NOT_FOUND, attempts)
            if outcome == "challenged":
                # Reason: 实测 403 挑战只出现在 .json、/search 这类整页面被要求浏览器验证的路径上，
                # 与出口无关；继续换线等于拿多个 IP 硬闯挑战，所以直接停下，也不冷却这条线路。
                self.state.save()
                raise FetchError(f"{short}：Cloudflare 要求浏览器验证（与出口无关，本 skill 不绕过）",
                                 EXIT_CHALLENGED, attempts)
            log(f"GET {short} via {route.label} → {OUTCOME_ZH[outcome]}（{detail}），"
                f"该线路冷却 {fmt_duration(seconds)}，换下一条")
            self.planner.penalize(route, outcome, seconds, detail)
            self.state.save()
            if reached:
                site_hits += 1
                if outcome == "rate_limited" and last_site_outcome == "rate_limited":
                    # 连续两个不同出口都被限频，多半是全站或路径级限流，再换线只会继续加压
                    log("连续两个出口都被限频，判定为全站限流，停止换线")
                    break
                last_site_outcome = outcome
            else:
                conn_fails += 1
            if site_hits > self.cfg["max_switches"] or conn_fails >= self.cfg["max_conn_failures"]:
                break
        raise FetchError(f"{short}：所有可用线路都失败了", EXIT_ALL_FAILED, attempts)

    def _pace(self) -> None:
        wait = self.state.data["last_request_at"] + self.cfg["min_interval"] - time.time()
        if wait > 0:
            if wait >= 1:
                log(f"节流：等待 {wait:.1f}s")
            time.sleep(wait)
