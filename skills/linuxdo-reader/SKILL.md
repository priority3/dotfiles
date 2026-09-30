---
name: linuxdo-reader
description: "读取 LINUX DO（linux.do，L 站）论坛的公开内容：最新/热门/Top 话题、分类与标签下的话题、帖子正文与楼层、用户动态、分类列表。内置系统代理 + 浏览器 UA、全局节流与本地缓存；遇到 429 限频或线路故障时自动换出口（临时起独立 mihomo 轮换 Clash Verge 节点 → HTTP 代理池），不改动系统代理和主 Clash。触发词：linux.do / linuxdo / LINUX DO / L站 / 佬友 / 始皇 / 福利羊毛 / 公益站 / 「L站最近在聊什么」「看看 linux.do 上关于 X 的讨论」「帮我读一下这个帖子」。用户贴出 linux.do/t/topic/… 链接时也应触发。"
---

# linux.do 阅读器

通过 RSS 和帖子页读取 linux.do 的公开内容。所有请求都经 `scripts/ld.py` 发出，它负责节流、缓存、换出口和脱敏日志。

## 快速开始

```bash
LD="python3 ~/.claude/skills/linuxdo-reader/scripts/ld.py"
$LD latest -n 10
```

| 命令 | 作用 |
| --- | --- |
| `latest` / `hot` / `posts` | 最新话题 / 热门话题 / 全站最新回帖 |
| `top --period weekly` | Top 话题（daily / weekly / monthly / quarterly / yearly / all） |
| `category <ref>` | 分类下的话题；`ref` 可写 `welfare/36`、`36`、`welfare` 或 `福利羊毛` |
| `tag <名称>` | 标签下的话题，如 `tag 纯水` |
| `topic <id或链接> [--page N] [--pages K] [--full]` | 帖子正文，每页 20 楼；链接带楼层号（`/t/topic/123/35`）时自动跳到所在页 |
| `user <用户名> [--topics]` | 用户最近的帖子；`--topics` 只看他发起的话题 |
| `categories [--refresh]` | 分类列表（名称、slug/id），缓存 24h |
| `rss <路径>` | 任意 Discourse RSS，如 `/g/<群组>/posts.rss`、`/badges/<id>/<slug>.rss` |
| `routes` / `doctor [--live]` / `reset [key] [--cache]` | 线路与冷却状态 / 自检 / 清除冷却 |

通用参数：`--json`（结构化输出，正文不截断）、`--no-cache`、`--route system|direct|clash|pool`（只走某条线路）；列表命令另有 `-n 条数`、`--excerpt 摘要长度`。

## 工作守则（agent 必须遵守）

1. **只通过 ld.py 访问 linux.do**。不要用 WebFetch、裸 curl、浏览器或 Python 请求库：它们要么被 Cloudflare 拦，要么绕开了节流和换线。
2. **先看列表，再读正文**。先用列表命令筛出相关话题，只对确实需要的 1–5 个调用 `topic`。长帖先读第 1 页，需要时再用 `--page` 往后翻，不要一口气读完所有页。
3. **不要并行调用**。ld.py 有跨进程请求锁，默认每次请求至少间隔 5 秒，顺序调用即可；同一地址 2 分钟（RSS）/ 10 分钟（帖子页）内会直接命中本地缓存。
4. **搜索**：站内搜索页被 Cloudflare 整页拦截，本 skill 不提供搜索。先用 WebSearch 搜 `site:linux.do 关键词`（中文内容搜不到时改用百度），拿到话题 id 后再 `topic <id>`。
5. **退出码 4（所有线路失败）**：如实告诉用户 linux.do 正在限流或线路不可用，附上 stderr 里的尝试记录。不要循环重试，可以建议过一段时间再来（`routes` 能看到剩余冷却时间）。
6. **退出码 6（要求浏览器验证）**：该页面被 Cloudflare 整页挑战，换出口也没用。不要尝试绕过：不打 `.json` 接口、不用浏览器过验证、不换 TLS 指纹库。
7. **退出码 3（不存在或需登录）**：私有分类和仅登录可见的内容不在本 skill 范围内，本 skill 不做登录。
8. **不回显代理凭证**：日志里代理只显示 `host:port`。排查时也不要 cat 代理池文件或 Clash 配置。

## 输出

- 话题列表：`[话题id] 标题`，下一行 `分类 · @作者 · 时间 · N帖/M人`，再下一行摘要；📌 置顶、🔒 已关闭。链接为 `https://linux.do/t/topic/<id>`。
- 帖子列表：`[话题id#楼层] 标题 · @作者 · 时间`，下一行正文摘要。
- `topic`：先输出标题、分类、标签、帖数/浏览/点赞、分页提示，再逐楼输出 `### #楼层 @用户 · 时间 · ❤ 点赞数 · 回复 #x`。默认主楼最多 6000 字、回复最多 800 字，`--full` 取消截断。引用显示为 `[引用 @xxx]` 加 `> ` 前缀，图片显示为 `[图片]`，链接卡片显示为 `[链接预览] URL`。
- stderr 里 `[linuxdo] …` 开头的是线路日志：走了哪条线路、是否命中缓存、为什么换线。

## 出口与换线

线路顺序为 `system → clash → pool`，只在失败时换线，不做主动轮换。细节见 [references/routing.md](references/routing.md)。

- **system**：系统代理，取自 `HTTPS_PROXY` 或 Clash Verge 的 mixed-port（本机是 `127.0.0.1:7897`）。本机不走代理直连 linux.do 会超时。
- **clash**：system 被限频或连不上时，临时启动一个**独立的 mihomo 进程**，加载 Clash Verge 运行时配置里的节点（默认排除依赖前置代理的 `🏠` 住宅节点），逐个切换出口。它只承载 ld.py 自己的请求，用完即停，**不会**动主 Clash 的节点和配置。主 Clash 的 `🔰 选择节点` 同时承载 Claude 的流量，切它会让 agent 会话自己断线。
- **pool**：`~/Downloads/*proxies*.txt` 里的 HTTP 代理池。代理商对 CONNECT 回 402/407/429（流量耗尽或鉴权失败）时整池暂停 6h；同一个文件连续 3 个代理连不上时整池暂停 1h。

冷却规则：429 限频冷却 15 分钟（响应带 Retry-After 时按它来）；连不上冷却 5 分钟；服务端 5xx 冷却 1 分钟。连续两个出口都返回 429 时判定为全站限流，停止换线。

## 排障

| 现象 | 原因与处理 |
| --- | --- |
| `429 限频（Cloudflare 挑战页）` | 该出口 IP 请求过密。ld.py 会自动换线；全部失败就等冷却结束 |
| `Cloudflare 挑战`，退出码 6 | 整页要求浏览器验证（`.json` 接口、`/search` 都是这样），与出口无关 |
| `代理不可用（流量耗尽/鉴权失败）` 或代理池整池暂停 | 代理池套餐流量用完或过期；续费后执行 `ld.py reset` |
| `clash 线路不可用` | 没装 Clash Verge Rev、找不到 `clash-verge.yaml`，或节点被过滤光了；用 `doctor` 查看 |
| 同一请求 Python 403、curl 200 | Cloudflare 按客户端指纹拦截，所以一律走 ld.py（内部用 curl） |
| `routes` 提示独立 mihomo 仍在运行 | 上次进程被强杀后遗留，执行 `ld.py reset` 清理 |

## 配置与文件

- 可选配置 `~/.config/linuxdo-reader/config.json`，字段见 [config.example.json](config.example.json)（节流间隔、线路顺序、代理池路径、节点过滤等）。环境变量 `LD_ROUTES`、`LD_MIN_INTERVAL`、`LD_SYSTEM_PROXY` 可以临时覆盖，`LD_CONFIG`、`LD_CACHE_DIR` 用来改路径。
- 运行时文件在 `~/.cache/linuxdo-reader/`：`state.json`（节流与冷却）、`http/`（响应缓存）、`categories.json`、`mihomo/`（独立实例；节点副本权限 0600，停止即删）。
- 端点清单、数据字段和 Cloudflare 实测记录见 [references/endpoints.md](references/endpoints.md)。
- 仓库里不存任何凭证：代理池、Clash 节点和 secret 都在运行时从本机读取。
