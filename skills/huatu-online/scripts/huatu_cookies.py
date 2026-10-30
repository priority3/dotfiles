#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从本机 Chrome 解密 huatu.com 相关 cookie，输出到 /tmp/huatu_cookies.json

原理：Chrome 在 macOS 上用 Keychain 里的 "Chrome Safe Storage" 作为口令，
PBKDF2-SHA1(salt='saltysalt', 1003 轮, 16 字节) 派生 AES-128-CBC 密钥，
IV 为 16 个空格；Chrome 130+ 还会在明文前加 32 字节域摘要。

只读：仅复制 Cookies 数据库到 /tmp 后读取，不修改浏览器任何数据。
"""
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys

OUT = pathlib.Path('/tmp/huatu_cookies.json')
CHROME_COOKIES = pathlib.Path.home() / 'Library/Application Support/Google/Chrome/Default/Cookies'


def keychain_key() -> str:
    r = subprocess.run(['security', 'find-generic-password', '-s', 'Chrome Safe Storage', '-w'],
                       capture_output=True, text=True)
    return (r.stdout or '').strip()


def decrypt(enc: bytes, dk: bytes) -> str:
    if not enc or enc[:3] != b'v10':
        return ''
    p = subprocess.run(['openssl', 'enc', '-aes-128-cbc', '-d', '-K', dk.hex(), '-iv', '20' * 16, '-nopad'],
                       input=enc[3:], capture_output=True)
    raw = p.stdout
    if not raw:
        return ''
    pad = raw[-1]
    if 0 < pad <= 16:
        raw = raw[:-pad]
    if len(raw) > 32:          # Chrome >=130 的 32 字节前缀
        raw = raw[32:]
    return raw.decode('utf-8', 'ignore')


def main() -> int:
    if not CHROME_COOKIES.exists():
        print(f'找不到 Chrome Cookies: {CHROME_COOKIES}', file=sys.stderr)
        return 1
    key = keychain_key()
    if not key:
        print('取不到 Keychain 密钥（Chrome Safe Storage）。若刚装过 Chrome，先打开一次让它生成。', file=sys.stderr)
        return 1
    dk = hashlib.pbkdf2_hmac('sha1', key.encode(), b'saltysalt', 1003, 16)

    tmp = pathlib.Path('/tmp/ck.db')
    shutil.copyfile(CHROME_COOKIES, tmp)
    db = sqlite3.connect(tmp)
    rows = db.execute(
        "select host_key, name, value, encrypted_value from cookies where host_key like '%huatu%'"
    ).fetchall()

    out = []
    for host, name, val, enc in rows:
        plain = val or decrypt(enc, dk)
        if not plain:
            continue
        out.append({'host': host, 'name': name, 'value': plain})

    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    logged = {c['name'] for c in out}
    print(f'已解密 {len(out)} 条 cookie → {OUT}')
    if 'UserName' in logged or 'ht_token' in logged:
        print('检测到登录态：有 UserName / ht_token')
        return 0
    print('⚠ 未发现登录 cookie，浏览器里可能已退出华图在线', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
