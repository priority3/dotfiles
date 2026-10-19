---
name: linuxdo-reader
description: "读取 LINUX DO（linux.do，L 站）论坛内容：最新/热门/Top 话题、分类与标签下的话题、帖子正文与楼层、用户动态、分类列表；用 Discourse User API Key（只读）授权登录后还能读按信任等级开放的板块。内置系统代理 + 浏览器 UA、全局节流与本地缓存；遇到 429 限频或线路故障时自动换出口（临时起独立 mihomo 轮换 Clash Verge 节点 → HTTP 代理池），不改动系统代理和主 Clash。触发词：linux.do / linuxdo / LINUX DO / L站 / 佬友 / 始皇 / 福利羊毛 / 公益站 / 「L站最近在聊什么」「看看 linux.do 上关于 X 的讨论」「帮我读一下这个帖子」。用户贴出 linux.do/t/topic/… 链接时也应触发。"
---

# linux.do 阅读器

通过 RSS 和帖子页读取 linux.do 的内容：匿名可读公开板块，授权登录后可读按信任等级开放的板块。所有请求都经 `scripts/ld.py` 发出，它负责节流、缓存、换出口、登录态和脱敏日志。

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
| `login` / `logout` / `whoami` | 授权登录（User API Key，只读）/ 清除本机凭证 / 查看当前身份与信任等级 |
| `routes` / `doctor [--live]` / `reset [key] [--cache]` | 线路与冷却状态 / 自检 / 清除冷却 |

通用参数：`--json`（结构化输出，正文不截断）、`--no-cache`、`--route system|direct|clash|pool`（只走某条线路）、`--anonymous`（忽略本机登录态）；列表命令另有 `-n 条数`、`--excerpt 摘要长度`。

## 工作守则（agent 必须遵守）

1. **只通过 ld.py 访问 linux.do**。不要用 WebFetch、裸 curl、浏览器或 Python 请求库：它们要么被 Cloudflare 拦，要么绕开了节流和换线。
2. **先看列表，再读正文**。先用列表命令筛出相关话题，只对确实需要的 1–5 个调用 `topic`。长帖先读第 1 页，需要时再用 `--page` 往后翻，不要一口气读完所有页。
3. **不要并行调用**。ld.py 有跨进程请求锁，默认每次请求至少间隔 5 秒，顺序调用即可；同一地址 2 分钟（RSS）/ 10 分钟（帖子页）内会直接命中本地缓存（**带 `LD_COOKIE` 时不读写缓存**）。
4. **搜索**：站内搜索页被 Cloudflare 整页拦截，本 skill 不提供搜索。先用 WebSearch 搜 `site:linux.do 关键词`（中文内容搜不到时改用百度），拿到话题 id 后再 `topic <id>`。
5. **退出码 4（所有线路失败）**：如实告诉用户 linux.do 正在限流或线路不可用，附上 stderr 里的尝试记录。不要循环重试，可以建议过一段时间再来（`routes` 能看到剩余冷却时间）。
6. **退出码 6（要求浏览器验证）**：该页面被 Cloudflare 整页挑战，换出口也没用。不要尝试绕过：不打 `.json` 接口、不用浏览器过验证、不换 TLS 指纹库。
7. **退出码 3（不存在或需登录）**：先 `ld.py whoami` 看是否已登录。未登录就告诉用户运行 `ld.py login` 完成授权（授权要在用户自己的浏览器里点，agent 不能代替，也不要向用户索要密码）；已登录仍是 3，说明信任等级不够、内容不存在或是私信，如实说明即可。
8. **不回显凭证**：日志里代理只显示 `host:port`，登录 key 从不打印。排查时也不要 cat 代理池文件、Clash 配置或 `~/.config/linuxdo-reader/auth.json`。

## 登录（读按信任等级开放的板块）

默认匿名，只能看游客可见的板块。要读 TL1 / TL2 / TL3 才开放的板块，授权一次即可：

1. `ld.py login`：生成一对 RSA 密钥，打印授权链接；
2. 用户在**已登录 linux.do 的浏览器**里打开链接，点「授权」，页面会显示一段密文；
3. `ld.py login --payload '<密文>'`（或 `--payload -` 从标准输入粘贴）：解密、保存 key，并自动 `whoami` 确认身份。

之后所有命令自动带登录态；`--anonymous` 可临时以游客身份访问；`ld.py logout` 清除本机凭证（撤销授权要到 linux.do 偏好设置 →「应用」里操作）。

- 申请的 scope 只有 `read`：只能 GET，不能发帖、点赞、改资料。
- key 存在 `~/.config/linuxdo-reader/auth.json`（0600），经 curl 的 stdin 配置传入，不进命令行、不进日志、不进仓库。
- 与浏览器会话互不影响。兜底方案 `ld.py login --cookie <_t 值>` 会和浏览器抢同一个会话（Discourse 每 10 分钟轮换 token，脚本一用浏览器就会被登出），只在站点关闭了 User API Key 时才用，且要从单独登录的浏览器窗口取 cookie。
- 登录与匿名的响应缓存、分类表分开存放。

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
| `system` 线路 `curl exit 28 Proxy CONNECT aborted due to timeout` | `HTTPS_PROXY` 可能指向的不是 Clash 而是别的本地代理（实测本机被设成 `http://127.0.0.1:49720`，是沙箱代理，连不上 linux.do）。用 `LD_SYSTEM_PROXY=http://127.0.0.1:7897` 强制走 Clash Verge 的 mixed-port；端口以 `~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml` 里的 `mixed-port` 为准（可能读不到主 yaml，同目录 `config.yaml` 也有一份） |
| `clash` 线路 `Brokered host copy source refused by file policy` | 复制 clash-verge.yaml 被沙箱/权限拦截；先走 `LD_SYSTEM_PROXY` 指定 system 线路，别死等 clash 冷却 |
| 全网段都不通时 | `python3 ld.py reset` 清冷却后再试；`reset` 只清冷却，不会重置缓存（要连缓存一起清用 `reset --cache`） |
| `routes` 提示独立 mihomo 仍在运行 | 上次进程被强杀后遗留，执行 `ld.py reset` 清理 |
| 已登录仍 404 / 退出码 3 | 信任等级不够，或内容是私信 / 已删除；`whoami` 能看到当前 TL |
| 已登录却 403（不是挑战页） | key 被撤销或失效，`ld.py login` 重新授权 |

## 登录态（读等级帖 / 私密分类）

默认匿名访问，所以**需要登录或信任等级的分类一律读不到**（Discourse 对匿名返回 404，
和「帖子已删除」无法从外面区分）—— 表现就是 `退出码 3：不存在或需登录`。

要读这类内容，用浏览器自己的登录态（本 skill 不做账号密码登录）：

```bash
LD_COOKIE='_t=<...>; _forum_session=<...>' python3 ld.py topic <id> --no-cache
```

- Cookie 取值：浏览器登录 linux.do → DevTools → Application → Cookies → `https://linux.do`，
  至少复制 `_t` 和 `_forum_session` 两项，按 `name=value; name=value` 拼起来。
- **只走环境变量，不要写进 `config.json`**（cookie 等同账号密码）。
- 带 cookie 时自动跳过缓存读写：既不读匿名时缓存的 404，也不会把等级帖内容写进公共缓存。
- 仍返回 404 → 说明帖子确实不存在/已删，不是权限问题。

## 配置与文件

- 可选配置 `~/.config/linuxdo-reader/config.json`，字段见 [config.example.json](config.example.json)（节流间隔、线路顺序、代理池路径、节点过滤等）。环境变量 `LD_ROUTES`、`LD_MIN_INTERVAL`、`LD_SYSTEM_PROXY` 可以临时覆盖，`LD_CONFIG`、`LD_CACHE_DIR` 用来改路径。
- 运行时文件在 `~/.cache/linuxdo-reader/`：`state.json`（节流与冷却）、`http/`（响应缓存）、`categories.json`、`mihomo/`（独立实例；节点副本权限 0600，停止即删）。
- 端点清单、数据字段和 Cloudflare 实测记录见 [references/endpoints.md](references/endpoints.md)。
- 登录凭证在 `~/.config/linuxdo-reader/`：`auth.json`（key 或 cookie 模式标记）、`cookies.txt`（仅 cookie 模式），均 0600。
- 仓库里不存任何凭证：代理池、Clash 节点、secret 和登录 key 都在运行时从本机读取。
