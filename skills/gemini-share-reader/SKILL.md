---
name: gemini-share-reader
description: "Read Gemini shared conversation links and extract the rendered chat into structured text. Use when users provide `https://gemini.google.com/share/*` or `https://g.co/gemini/share/*` and ask to read, summarize, archive, migrate, or analyze the shared conversation content. Triggers: Gemini/分享链接/对话内容/gemini share."
---

# Gemini Share Reader

## Overview

从 Gemini 公开分享链接中提取完整对话内容。Gemini 分享页面是纯客户端渲染（JavaScript SPA），必须通过浏览器引擎加载后才能提取 DOM 内容。

## Quick Start

当用户提供 Gemini 分享链接时，按以下流程操作：

1. 验证 URL 格式：`https://gemini.google.com/share/*` 或 `https://g.co/gemini/share/*`
2. 使用 Chrome DevTools MCP 提取对话内容（首选方案）
3. 输出结构化的对话数据

## Workflow（Chrome DevTools MCP 方案）

### Step 1：打开页面

使用 `mcp__chrome-devtools__new_page` 打开分享链接：

```
url: "https://gemini.google.com/share/<share_id>"
timeout: 15000
```

### Step 2：等待页面加载

页面打开后，等待 2-3 秒让 JavaScript 完成渲染。可以使用 `mcp__chrome-devtools__wait_for` 等待关键元素出现：

```
text: ["message-content", "query-text"]
timeout: 10000
```

### Step 3：提取对话内容

使用 `mcp__chrome-devtools__evaluate_script` 执行以下 JavaScript 提取对话：

```javascript
() => {
  const clean = (value) => {
    if (!value) return "";
    return value
      .replace(/ /g, " ")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
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
      const content = clean(lines.length ? lines.join("\n") : node.innerText);
      if (content) rows.push({ role: "user", content });
    }
  }

  return {
    title: (document.title || "").trim(),
    final_url: window.location.href,
    message_count: rows.length,
    messages: rows
  };
}
```

### Step 4：格式化输出

提取到数据后，根据用户需求选择输出格式：

- **Markdown（默认）**：适合人类阅读和后续总结
  ```markdown
  # <title>

  Source: <url>

  ## user

  <content>

  ## assistant

  <content>
  ```

- **JSON**：适合程序解析
  ```json
  {
    "source_url": "...",
    "final_url": "...",
    "title": "...",
    "message_count": N,
    "messages": [{"role": "user", "content": "..."}, ...]
  }
  ```

- **Plain text**：纯文本格式
  ```
  [user]
  content...

  [assistant]
  content...
  ```

### Step 5：关闭页面

提取完成后，使用 `mcp__chrome-devtools__close_page` 关闭打开的页面。

## Fallback：Playwright 脚本方案

当 Chrome DevTools MCP 不可用时（如无头环境、CLI 场景），可使用 Playwright 脚本：

```bash
python3 scripts/read_gemini_share.py "<url>" --format markdown
```

脚本依赖：
```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

脚本参数：
- `<url>`：Gemini 分享链接（必填）
- `--format markdown|json|txt`：输出格式（默认 markdown）
- `--output <path>`：写入文件而非 stdout
- `--timeout-ms <n>`：页面加载超时（默认 60000）
- `--wait-ms <n>`：额外等待时间（默认 8000）
- `--headful`：显示浏览器窗口（调试用）

## Output Contract

- `source_url`：输入的分享链接
- `final_url`：重定向后的最终 URL
- `title`：页面标题
- `message_count`：提取消息数量
- `messages`：有序消息列表，每条包含 `role`（user/assistant）和 `content`

## Constraints

- 需要网络访问来加载 Gemini 页面
- 仅处理公开分享页面（无需登录）
- Gemini DOM 结构可能变化，选择器可能需要更新
- 单次只能处理一个分享链接；多个链接需循环调用
