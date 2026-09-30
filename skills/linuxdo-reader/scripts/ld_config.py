"""linuxdo-reader 的配置、路径与跨进程状态。

配置优先级（后者覆盖前者）：内置默认值 → ~/.config/linuxdo-reader/config.json → 环境变量。

Reason: dotfiles 仓库是公开的，这里只放路径和策略参数；代理凭证、Clash secret
一律在运行时从本机文件读取，绝不写进仓库。
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import time
from pathlib import Path

HOME = Path.home()
CONFIG_FILE = Path(os.environ.get("LD_CONFIG") or HOME / ".config" / "linuxdo-reader" / "config.json")
CACHE_DIR = Path(os.environ.get("LD_CACHE_DIR") or HOME / ".cache" / "linuxdo-reader")
STATE_FILE = CACHE_DIR / "state.json"
LOCK_FILE = CACHE_DIR / "request.lock"
HTTP_CACHE_DIR = CACHE_DIR / "http"
CATEGORIES_FILE = CACHE_DIR / "categories.json"
MIHOMO_HOME = CACHE_DIR / "mihomo"
CLASH_VERGE_DIR = HOME / "Library" / "Application Support" / "io.github.clash-verge-rev.clash-verge-rev"

# Reason: 实测 Cloudflare 只按客户端指纹拦（curl 放行、Python urllib 拦），UA 不影响放行；
# 用浏览器 UA 是因为 Discourse 会据此返回带 data-preloaded JSON 的完整页面，比爬虫版 HTML 好解析。
CHROME_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

DEFAULTS: dict = {
    "base_url": "https://linux.do",
    "user_agent": CHROME_UA,
    "routes": ["system", "clash", "pool"],
    "system_proxy": "",
    "min_interval": 5.0,
    "max_switches": 2,
    "max_conn_failures": 6,
    "timeout": 25,
    "max_pages": 5,
    "cache_ttl": {"rss": 120, "html": 600},
    "cooldown": {
        "rate_limited": 900,
        "error": 300,
        "server_error": 60,
        "proxy_dead": 3600,
        "pool_exhausted": 21600,
    },
    "clash": {
        "binary": "",
        "source_config": "",
        "include": "",
        "exclude": "🏠|剩余|到期|流量|官网|套餐|重置",
    },
    "pool": {"files": ["~/Downloads/*proxies*.txt"], "max_tries": 4},
}

# Reason: 换出口只是为了从单个 IP 的限频惩罚中恢复，不是为了放大抓取速率，所以节流间隔设下限。
MIN_INTERVAL_FLOOR = 2.0


def _merge(base: dict, extra: dict) -> None:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


def load_config() -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if CONFIG_FILE.is_file():
        try:
            _merge(cfg, json.loads(CONFIG_FILE.read_text("utf-8")))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"配置文件解析失败 {CONFIG_FILE}: {exc}") from exc
    env = os.environ
    if env.get("LD_ROUTES"):
        cfg["routes"] = [r.strip() for r in env["LD_ROUTES"].split(",") if r.strip()]
    if env.get("LD_MIN_INTERVAL"):
        cfg["min_interval"] = float(env["LD_MIN_INTERVAL"])
    if env.get("LD_SYSTEM_PROXY"):
        cfg["system_proxy"] = env["LD_SYSTEM_PROXY"]
    cfg["min_interval"] = max(float(cfg["min_interval"]), MIN_INTERVAL_FLOOR)
    return cfg


class State:
    """跨进程共享的运行状态：上次请求时间（节流用）、线路与代理池冷却、Clash 轮换游标。"""

    BUCKETS = ("routes", "pool_files")

    def __init__(self, data: dict):
        self.data = data

    @classmethod
    def load(cls) -> "State":
        try:
            data = json.loads(STATE_FILE.read_text("utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault("last_request_at", 0.0)
        data.setdefault("clash_cursor", 0)
        now = time.time()
        for bucket in cls.BUCKETS:
            # 过期的冷却记录直接丢弃，避免状态文件无限增长
            data[bucket] = {k: v for k, v in (data.get(bucket) or {}).items() if v.get("until", 0) > now}
        return cls(data)

    def save(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, STATE_FILE)

    def cooling(self, key: str, bucket: str = "routes") -> dict | None:
        entry = self.data[bucket].get(key)
        return entry if entry and entry.get("until", 0) > time.time() else None

    def cool(self, key: str, seconds: float, reason: str, bucket: str = "routes") -> None:
        now = time.time()
        self.data[bucket][key] = {"until": now + seconds, "reason": reason, "at": now}

    def clear(self, key: str | None = None) -> int:
        removed = 0
        for bucket in self.BUCKETS:
            if key is None:
                removed += len(self.data[bucket])
                self.data[bucket] = {}
            elif key in self.data[bucket]:
                del self.data[bucket][key]
                removed += 1
        return removed


class RequestLock:
    """跨进程请求锁：多个 ld.py 同时运行时排队执行，保证全局节流真正生效。"""

    def __init__(self, timeout: float = 180):
        self.timeout = timeout
        self._handle = None

    def acquire(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._handle = open(LOCK_FILE, "a+")
        deadline = time.time() + self.timeout
        while True:
            try:
                fcntl.flock(self._handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.time() > deadline:
                    self.release()
                    raise SystemExit("另一个 ld.py 进程占用请求锁超过 3 分钟，请稍后再试")
                time.sleep(0.5)

    def release(self) -> None:
        if self._handle:
            fcntl.flock(self._handle, fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


def load_categories(max_age: float = 86400) -> list[dict]:
    try:
        data = json.loads(CATEGORIES_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return data.get("items", []) if time.time() - data.get("fetched_at", 0) < max_age else []


def save_categories(items: list[dict]) -> None:
    if not items:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CATEGORIES_FILE.write_text(json.dumps({"fetched_at": time.time(), "items": items}, ensure_ascii=False), "utf-8")
