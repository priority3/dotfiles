"""按需启动一个独立的 mihomo 实例，专门给 linux.do 请求轮换出口节点。

Reason: 不能直接切主 Clash 的节点——主配置里 anthropic.com / claude.ai 也走「🔰 选择节点」，
切到不受支持地区的节点会让正在运行本 skill 的 agent 会话自己断线；浏览器里的 linux.do
会话也会跟着换 IP。独立实例只承载本脚本的请求、用完即停，主 Clash 与系统代理完全不受影响。
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ld_config import CLASH_VERGE_DIR, MIHOMO_HOME

GROUP = "LD"
# 目前只验证过 Clash Verge Rev 自带的内核；其它安装方式请在配置里指定 clash.binary
_BINARY_CANDIDATES = ("/Applications/Clash Verge.app/Contents/MacOS/verge-mihomo",)
_RUNTIME_FILES = ("nodes.yaml", "config.yaml", "pid")
# 控制器监听在本机，必须绕开环境变量里的 HTTP(S)_PROXY
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class MihomoError(RuntimeError):
    pass


def find_binary(configured: str = "") -> str | None:
    candidates = [configured, *_BINARY_CANDIDATES, shutil.which("mihomo") or "", shutil.which("verge-mihomo") or ""]
    for cand in candidates:
        path = os.path.expanduser(cand) if cand else ""
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def find_source(configured: str = "") -> Path | None:
    """节点来源：默认取 Clash Verge 生成的运行时配置（订阅 + 扩展合并后的全部节点）。"""
    path = Path(os.path.expanduser(configured)) if configured else CLASH_VERGE_DIR / "clash-verge.yaml"
    return path if path.is_file() else None


def _free_ports(count: int) -> list[int]:
    socks = [socket.socket() for _ in range(count)]
    try:
        for sock in socks:
            sock.bind(("127.0.0.1", 0))
        return [sock.getsockname()[1] for sock in socks]
    finally:
        for sock in socks:
            sock.close()


def _yaml_str(text: str) -> str:
    # Reason: JSON 字符串同时是合法的 YAML 双引号标量，省得为转义规则引入 PyYAML
    return json.dumps(text, ensure_ascii=False)


def running_pid(home: Path = MIHOMO_HOME) -> int | None:
    try:
        pid = int((home / "pid").read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def cleanup_stale(home: Path = MIHOMO_HOME) -> bool:
    """清理上次异常退出遗留的实例。核对命令行确实指向本 skill 的目录才结束进程，避免误杀主 Clash。"""
    killed = False
    pid = running_pid(home)
    if pid:
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
        if str(home) in cmd:
            try:
                os.kill(pid, signal.SIGTERM)
                killed = True
            except ProcessLookupError:
                pass
    for name in _RUNTIME_FILES:
        (home / name).unlink(missing_ok=True)
    return killed


class PrivateMihomo:
    def __init__(self, binary: str, source: Path, include: str = "", exclude: str = "",
                 home: Path = MIHOMO_HOME):
        self.binary, self.source, self.include, self.exclude, self.home = binary, source, include, exclude, home
        self.proc: subprocess.Popen | None = None
        self.nodes: list[str] = []
        self.secret = ""
        self.mixed_port = self.ctl_port = 0

    @property
    def proxy_url(self) -> str:
        return f"http://127.0.0.1:{self.mixed_port}"

    def start(self) -> None:
        cleanup_stale(self.home)
        self.home.mkdir(parents=True, exist_ok=True)
        os.chmod(self.home, 0o700)
        # Reason: mihomo 只允许 provider 文件位于 -d 目录内，只能复制一份节点配置（0600，停止时删除）
        nodes_file = self.home / "nodes.yaml"
        shutil.copyfile(self.source, nodes_file)
        os.chmod(nodes_file, 0o600)
        self.secret = secrets.token_hex(16)
        self.mixed_port, self.ctl_port = _free_ports(2)
        cfg_file = self.home / "config.yaml"
        cfg_file.write_text(self._render_config(), "utf-8")
        os.chmod(cfg_file, 0o600)
        with open(self.home / "mihomo.log", "wb") as log:
            self.proc = subprocess.Popen([self.binary, "-d", str(self.home), "-f", str(cfg_file)],
                                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        (self.home / "pid").write_text(str(self.proc.pid))
        self._wait_ready()
        info = self._api("GET", f"/proxies/{urllib.parse.quote(GROUP)}")
        self.nodes = [name for name in info.get("all", []) if name not in ("DIRECT", "REJECT")]
        if not self.nodes:
            self.stop()
            raise MihomoError("节点列表为空（检查 clash.include / clash.exclude 过滤条件）")

    def _render_config(self) -> str:
        group = [f"  - name: {GROUP}", "    type: select", "    use: [user]"]
        if self.include:
            group.append(f"    filter: {_yaml_str(self.include)}")
        if self.exclude:
            group.append(f"    exclude-filter: {_yaml_str(self.exclude)}")
        return "\n".join([
            f"mixed-port: {self.mixed_port}",
            "bind-address: 127.0.0.1",
            "allow-lan: false",
            "mode: rule",
            "log-level: warning",
            "ipv6: false",
            "find-process-mode: off",
            f"external-controller: 127.0.0.1:{self.ctl_port}",
            f"secret: {_yaml_str(self.secret)}",
            "profile: {store-selected: false, store-fake-ip: false}",
            "proxy-providers:",
            "  user: {type: file, path: ./nodes.yaml}",
            "proxy-groups:",
            *group,
            "rules:",
            f"  - MATCH,{GROUP}",
            "",
        ])

    def _wait_ready(self, timeout: float = 8.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline and self.proc.poll() is None:
            try:
                self._api("GET", "/version")
                return
            except (OSError, MihomoError):
                time.sleep(0.15)
        tail = self._log_tail()
        self.stop()
        raise MihomoError(f"mihomo 未能就绪：{tail or '无日志输出'}")

    def _log_tail(self, lines: int = 3) -> str:
        try:
            text = (self.home / "mihomo.log").read_text("utf-8", "replace")
        except OSError:
            return ""
        return " | ".join(text.strip().splitlines()[-lines:])[:300]

    def select(self, node: str) -> None:
        self._api("PUT", f"/proxies/{urllib.parse.quote(GROUP)}", {"name": node})

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)
        self.proc = None
        for name in _RUNTIME_FILES:
            (self.home / name).unlink(missing_ok=True)

    def _api(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.ctl_port}{path}", data=data, method=method,
                                     headers={"Authorization": f"Bearer {self.secret}",
                                              "Content-Type": "application/json"})
        try:
            with _LOCAL.open(req, timeout=5) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise MihomoError(f"控制器 {method} {path} → HTTP {exc.code}") from exc
        return json.loads(raw) if raw.strip() else {}
