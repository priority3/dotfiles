#!/usr/bin/env python3
"""Read a Gemini share URL and extract conversation messages."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, List

VALID_PREFIXES = (
    "https://gemini.google.com/share/",
    "https://g.co/gemini/share/",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract rendered chat messages from a Gemini share URL.",
    )
    parser.add_argument("url", help="Gemini share URL")
    parser.add_argument(
        "--format",
        choices=("markdown", "json", "txt"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        help="Write output to file instead of stdout",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=60000,
        help="Page navigation timeout in milliseconds (default: 60000)",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=8000,
        help="Additional wait after network idle in milliseconds (default: 8000)",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Run Chromium with UI for debugging",
    )
    return parser.parse_args()


def normalize_and_validate_url(url: str) -> str:
    normalized = url.strip()
    if not any(normalized.startswith(prefix) for prefix in VALID_PREFIXES):
        raise ValueError(
            "Invalid URL. Expected https://gemini.google.com/share/* "
            "or https://g.co/gemini/share/*"
        )
    return normalized


def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def dedupe_adjacent_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    last_role = None
    last_content = None
    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        if not role or not content:
            continue
        if role == last_role and content == last_content:
            continue
        result.append({"role": role, "content": content})
        last_role = role
        last_content = content
    return result


def extract_with_playwright(
    url: str,
    timeout_ms: int,
    wait_ms: int,
    headful: bool,
) -> Dict[str, Any]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run:\n"
            "  python3 -m pip install playwright\n"
            "  python3 -m playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Navigation timeout after {timeout_ms}ms") from exc

        try:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            # Continue even if network never fully idles.
            pass

        # Trigger lazy render paths.
        for _ in range(3):
            page.mouse.wheel(0, 20000)
            page.wait_for_timeout(400)

        if wait_ms > 0:
            page.wait_for_timeout(wait_ms)

        payload = page.evaluate(
            """
            () => {
              const clean = (value) => {
                if (!value) return "";
                return value
                  .replace(/\\u00a0/g, " ")
                  .replace(/[ \\t]+\\n/g, "\\n")
                  .replace(/\\n{3,}/g, "\\n\\n")
                  .trim();
              };

              const rows = [];
              const nodes = Array.from(document.querySelectorAll("div.query-text, message-content"));

              for (const node of nodes) {
                const tag = node.tagName.toLowerCase();
                if (tag === "message-content") {
                  const markdown = node.querySelector("div.markdown");
                  const content = clean(markdown ? markdown.innerText : node.innerText);
                  if (content) rows.push({ role: "assistant", content });
                  continue;
                }

                if (node.classList.contains("query-text")) {
                  const lines = Array.from(node.querySelectorAll("p.query-text-line"))
                    .map((line) => (line.innerText || "").trim())
                    .filter(Boolean);
                  const content = clean(lines.length ? lines.join("\\n") : node.innerText);
                  if (content) rows.push({ role: "user", content });
                }
              }

              return {
                title: (document.title || "").trim(),
                final_url: window.location.href,
                messages: rows
              };
            }
            """
        )

        browser.close()

    messages = [
        {"role": item.get("role", ""), "content": clean_text(item.get("content", ""))}
        for item in payload.get("messages", [])
    ]
    messages = dedupe_adjacent_messages(messages)
    return {
        "source_url": url,
        "final_url": payload.get("final_url", url),
        "title": payload.get("title", ""),
        "message_count": len(messages),
        "messages": messages,
    }


def to_markdown(data: Dict[str, Any]) -> str:
    title = data.get("title") or "Gemini Share"
    lines = [f"# {title}", "", f"Source: {data.get('final_url')}", ""]
    for item in data.get("messages", []):
        role = item["role"]
        content = item["content"]
        lines.extend([f"## {role}", "", content, ""])
    return "\n".join(lines).strip() + "\n"


def to_text(data: Dict[str, Any]) -> str:
    chunks: List[str] = [f"Source: {data.get('final_url', '')}", ""]
    for item in data.get("messages", []):
        chunks.append(f"[{item['role']}]")
        chunks.append(item["content"])
        chunks.append("")
    return "\n".join(chunks).strip() + "\n"


def format_output(data: Dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output_format == "txt":
        return to_text(data)
    return to_markdown(data)


def main() -> int:
    args = parse_args()
    try:
        url = normalize_and_validate_url(args.url)
        data = extract_with_playwright(
            url=url,
            timeout_ms=args.timeout_ms,
            wait_ms=args.wait_ms,
            headful=args.headful,
        )
        output = format_output(data, args.format)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
        else:
            print(output, end="")
        return 0
    except Exception as exc:
        print(f"[gemini-share-reader] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
