#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO, Iterable, Optional

LOG_LINE_RE = re.compile(
    r"^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<ts>[^\]]+)\]\s+"
    r"\"(?P<request>[^\"]*)\"\s+"
    r"(?P<status>\d{3})\s+"
    r"(?P<body_bytes>\S+)"
    r"(?:\s+\"(?P<referrer>[^\"]*)\"\s+\"(?P<ua>[^\"]*)\")?"
    r".*$"
)


@dataclass(frozen=True)
class ParsedLine:
    ip: str
    ts: datetime
    method: str
    path: str
    status: int


def _open_text(path: str) -> IO[str]:
    if path == "-":
        return sys.stdin
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "rt", encoding="utf-8", errors="replace")


def _parse_ts(ts: str) -> Optional[datetime]:
    # Example: 10/Oct/2000:13:55:36 -0700
    try:
        return datetime.strptime(ts, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None


def _parse_request(request: str) -> tuple[str, str]:
    # Common: "GET /path?x=1 HTTP/1.1"
    parts = request.split()
    if len(parts) >= 2:
        method = parts[0]
        path = parts[1]
        return method, path
    return "-", "-"


def parse_lines(lines: Iterable[str]) -> tuple[list[ParsedLine], int]:
    parsed: list[ParsedLine] = []
    skipped = 0

    for raw in lines:
        line = raw.rstrip("\n")
        if not line:
            continue

        match = LOG_LINE_RE.match(line)
        if not match:
            skipped += 1
            continue

        ts = _parse_ts(match.group("ts"))
        if ts is None:
            skipped += 1
            continue

        method, path = _parse_request(match.group("request"))
        path = path.split("?", 1)[0]

        try:
            status = int(match.group("status"))
        except ValueError:
            skipped += 1
            continue

        parsed.append(
            ParsedLine(
                ip=match.group("ip"),
                ts=ts,
                method=method,
                path=path,
                status=status,
            )
        )

    return parsed, skipped


def _format_pct(count: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def _print_top(title: str, counter: Counter[str], total: int, top_n: int) -> None:
    print(f"\n{title}")
    if total <= 0:
        print("  (no data)")
        return
    for key, count in counter.most_common(top_n):
        print(f"  {count:>8}  {_format_pct(count, total):>6}  {key}")


def analyze(parsed: list[ParsedLine], *, skipped: int, top_n: int) -> int:
    total = len(parsed)
    if total == 0:
        print("No parseable access-log lines found.")
        if skipped:
            print(f"Skipped lines: {skipped}")
        return 2

    first_ts = min(p.ts for p in parsed)
    last_ts = max(p.ts for p in parsed)

    statuses = Counter(str(p.status) for p in parsed)
    methods = Counter(p.method for p in parsed)
    ips = Counter(p.ip for p in parsed)
    paths = Counter(p.path for p in parsed)

    ips_5xx = Counter(p.ip for p in parsed if p.status >= 500)
    paths_5xx = Counter(p.path for p in parsed if p.status >= 500)

    per_minute = Counter(p.ts.replace(second=0, microsecond=0).isoformat() for p in parsed)
    peak_minute, peak_minute_count = max(per_minute.items(), key=lambda kv: kv[1])

    print("nginx access log summary\n")
    print(f"Lines parsed:   {total}")
    print(f"Lines skipped:  {skipped}")
    print(f"Time range:     {first_ts.isoformat()} → {last_ts.isoformat()}")
    print(f"Peak minute:    {peak_minute} ({peak_minute_count} requests)")

    duration_s = (last_ts - first_ts).total_seconds()
    if duration_s > 0:
        rps = total / duration_s
        print(f"Avg rate:       {rps:.2f} req/s")

    _print_top("Status codes", statuses, total, top_n=50)
    _print_top("HTTP methods", methods, total, top_n=20)
    _print_top(f"Top client IPs (top {top_n})", ips, total, top_n=top_n)
    _print_top(f"Top paths (top {top_n})", paths, total, top_n=top_n)

    errors = sum(count for code, count in statuses.items() if code.startswith("5"))
    client_errors = sum(count for code, count in statuses.items() if code.startswith("4"))
    redirects = sum(count for code, count in statuses.items() if code.startswith("3"))
    ok = sum(count for code, count in statuses.items() if code.startswith("2"))

    print("\nBuckets")
    print(f"  2xx: {ok:>8}  {_format_pct(ok, total):>6}")
    print(f"  3xx: {redirects:>8}  {_format_pct(redirects, total):>6}")
    print(f"  4xx: {client_errors:>8}  {_format_pct(client_errors, total):>6}")
    print(f"  5xx: {errors:>8}  {_format_pct(errors, total):>6}")

    if errors:
        _print_top(f"Top IPs causing 5xx (top {top_n})", ips_5xx, total, top_n=top_n)
        _print_top(f"Top paths returning 5xx (top {top_n})", paths_5xx, total, top_n=top_n)

    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize an nginx access log (common/combined formats) with top status codes, "
            "IPs, paths, and request rate. Pass '-' to read from stdin."
        )
    )
    parser.add_argument("access_log", help="Path to nginx access log (or '-' for stdin). Supports .gz.")
    parser.add_argument("--top", type=int, default=20, help="Top-N rows for IPs/paths (default: 20).")
    args = parser.parse_args(argv)

    access_log_path = args.access_log
    if access_log_path != "-" and not Path(access_log_path).exists():
        print(f"File not found: {access_log_path}", file=sys.stderr)
        return 2

    with _open_text(access_log_path) as f:
        parsed, skipped = parse_lines(f)

    return analyze(parsed, skipped=skipped, top_n=max(1, args.top))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
