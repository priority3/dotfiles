---
name: gemini-share-reader
description: Read Gemini shared conversation links and extract the rendered chat into structured text. Use when users provide `https://gemini.google.com/share/*` or `https://g.co/gemini/share/*` and ask to read, summarize, archive, migrate, or analyze the shared conversation content.
---

# Gemini Share Reader

## Overview

Extract public Gemini share pages by rendering the page with Playwright and collecting user/assistant messages in DOM order.
Output clean conversation data as Markdown, JSON, or plain text for downstream summarization and analysis tasks.

## Quick Start

1. Validate the URL starts with `https://gemini.google.com/share/` or `https://g.co/gemini/share/`.
2. Run the extractor script:
   - `python3 scripts/read_gemini_share.py "<url>"`
3. Use output format as needed:
   - Markdown (default): `--format markdown`
   - JSON: `--format json`
   - Plain text: `--format txt`
4. Save to file when needed:
   - `--output /tmp/gemini_share.md`

## Workflow

1. Prefer the script in `scripts/read_gemini_share.py` for deterministic extraction.
2. Pass one share URL at a time; aggregate multiple links in a caller loop.
3. Prefer `--format json` when another tool will parse the output.
4. Prefer `--format markdown` when the next step is human reading or summarization.
5. If extraction returns zero messages, retry once with:
   - `--headful --wait-ms 12000`
6. If Playwright is missing, install dependencies and rerun:
   - `python3 -m pip install playwright`
   - `python3 -m playwright install chromium`

## Output Contract

- JSON output structure:
  - `source_url`: input share URL
  - `final_url`: resolved URL after redirects
  - `title`: page title
  - `message_count`: extracted message count
  - `messages`: ordered list of `{role, content}`
- Roles:
  - `user`
  - `assistant`

## Constraints

- Require internet access to load Gemini pages.
- Handle only public share pages.
- Expect occasional breakage if Gemini DOM structure changes.
