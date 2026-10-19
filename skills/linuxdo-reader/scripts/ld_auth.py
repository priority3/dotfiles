"""登录态：Discourse User API Key（首选，只读 scope）或浏览器 _t cookie（兜底）。

Reason: 按信任等级开放的板块只有登录后才能看。User API Key 走 Discourse 官方的第三方应用授权流程，
与浏览器会话完全独立、可在偏好设置里随时撤销；直接复制浏览器 cookie 会和浏览器争抢同一个会话
（Discourse 每 10 分钟轮换 token，脚本一用、浏览器 2 分钟后就被登出），所以只作兜底。
凭证只存在本机 ~/.config/linuxdo-reader/（0600），不进仓库，日志里也不打印。
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.parse
import uuid
from pathlib import Path

from ld_config import AUTH_FILE, CONFIG_DIR, COOKIE_FILE, PENDING_AUTH_FILE

APP_NAME = "linuxdo-reader"
SCOPES = "read"  # 只申请只读权限：所有 GET 可用，发帖/点赞/改资料一律不行


class AuthError(RuntimeError):
    pass


def _openssl(*args: str, data: bytes | None = None) -> bytes:
    try:
        proc = subprocess.run(["openssl", *args], input=data, capture_output=True)
    except FileNotFoundError as exc:
        raise AuthError("缺少 openssl 命令，无法生成密钥对 / 解密授权密文") from exc
    if proc.returncode != 0:
        raise AuthError(f"openssl {args[0]} 失败：{proc.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return proc.stdout


def _write_private(path: Path, text: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    path.write_text(text, "utf-8")
    os.chmod(path, 0o600)


def load() -> dict | None:
    """读取本机凭证；没有或不完整就返回 None（即匿名访问）。"""
    try:
        data = json.loads(AUTH_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("type") == "user_api_key" and data.get("key") and data.get("client_id"):
        return data
    if data.get("type") == "cookie" and COOKIE_FILE.is_file():
        return data
    return None


def auth_mode(auth: dict | None) -> str:
    return auth["type"] if auth else "anon"


def curl_options(auth: dict | None) -> list[tuple[str, str]]:
    """追加到 curl 配置文件的登录态选项。API key 走请求头；cookie 用同一个 jar 读写，轮换后的新 token 会自动保存。"""
    if not auth:
        return []
    if auth["type"] == "user_api_key":
        return [("header", f"User-Api-Key: {auth['key']}"),
                ("header", f"User-Api-Client-Id: {auth['client_id']}")]
    return [("cookie", str(COOKIE_FILE)), ("cookie-jar", str(COOKIE_FILE))]


def describe(auth: dict | None) -> str:
    if not auth:
        return "未登录（匿名，只能看游客可见的板块；ld.py login 可授权）"
    who = f"@{auth['username']}，" if auth.get("username") else ""
    since = time.strftime("%Y-%m-%d", time.localtime(auth.get("created_at", 0)))
    if auth["type"] == "user_api_key":
        return f"User API Key（{who}{since} 授权，只读）"
    return f"浏览器 cookie（{who}{since} 导入）"


def begin(base_url: str) -> str:
    """第一步：生成 RSA 密钥对，返回授权链接。私钥暂存本机，第二步解密完即删。"""
    private_pem = _openssl("genrsa", "2048").decode("utf-8")
    public_pem = _openssl("rsa", "-pubout", data=private_pem.encode("utf-8")).decode("utf-8")
    pending = {"client_id": str(uuid.uuid4()), "nonce": secrets.token_hex(16),
               "private_key": private_pem, "created_at": time.time()}
    _write_private(PENDING_AUTH_FILE, json.dumps(pending))
    query = urllib.parse.urlencode({
        "application_name": APP_NAME, "client_id": pending["client_id"], "scopes": SCOPES,
        "public_key": public_pem, "nonce": pending["nonce"],
    })
    return f"{base_url}/user-api-key/new?{query}"


def finish(payload: str) -> dict:
    """第二步：用私钥解开授权页给的密文，核对 nonce，保存 key。"""
    try:
        pending = json.loads(PENDING_AUTH_FILE.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise AuthError("没有进行中的授权，请先运行 ld.py login 生成授权链接") from exc
    try:
        cipher = base64.b64decode("".join(payload.split()), validate=True)
    except ValueError as exc:
        raise AuthError("密文不是合法的 base64，请只粘贴授权页显示的那一段") from exc
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as fh:
        fh.write(pending["private_key"])
        key_path = fh.name
    try:
        os.chmod(key_path, 0o600)
        plain = _openssl("pkeyutl", "-decrypt", "-inkey", key_path, data=cipher)
    finally:
        os.unlink(key_path)
    try:
        data = json.loads(plain)
    except ValueError as exc:
        raise AuthError("解密结果不是 JSON，密文可能不完整或不是本次授权产生的") from exc
    if data.get("nonce") != pending["nonce"]:
        raise AuthError("nonce 不匹配：这段密文不是本次授权链接产生的，请重新 ld.py login")
    auth = {"type": "user_api_key", "key": data["key"], "client_id": pending["client_id"],
            "api_version": data.get("api"), "created_at": time.time()}
    _write_private(AUTH_FILE, json.dumps(auth))
    PENDING_AUTH_FILE.unlink(missing_ok=True)
    return auth


def set_cookie(token: str, host: str = "linux.do") -> dict:
    """兜底：把浏览器里的 _t 写成 Netscape 格式的 cookie jar。"""
    token = token.strip()
    if token.startswith("_t="):
        token = token[3:]
    if not token or any(ch.isspace() for ch in token):
        raise AuthError("cookie 值不合法，只需要 _t 的值本身")
    expires = int(time.time()) + 60 * 86400
    jar = f"# Netscape HTTP Cookie File\n#HttpOnly_{host}\tFALSE\t/\tTRUE\t{expires}\t_t\t{token}\n"
    _write_private(COOKIE_FILE, jar)
    auth = {"type": "cookie", "created_at": time.time()}
    _write_private(AUTH_FILE, json.dumps(auth))
    return auth


def remember_user(user: dict) -> None:
    """把 whoami 确认到的用户名和信任等级记进凭证文件，routes 里好显示。"""
    auth = load()
    if auth:
        auth.update({"username": user.get("username"), "trust_level": user.get("trust_level")})
        _write_private(AUTH_FILE, json.dumps(auth))


def logout() -> int:
    removed = 0
    for path in (AUTH_FILE, PENDING_AUTH_FILE, COOKIE_FILE):
        if path.exists():
            path.unlink()
            removed += 1
    return removed
