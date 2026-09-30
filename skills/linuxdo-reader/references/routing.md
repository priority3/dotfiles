# 出口线路与换线策略

## 线路

| 线路 | 出口 | 何时用 | 状态键 |
| --- | --- | --- | --- |
| `system` | 系统代理：配置 `system_proxy` > 环境变量 `HTTPS_PROXY` 等 > Clash Verge `config.yaml` 的 `mixed-port` | 默认首选 | `system` |
| `direct` | 不走代理 | 没检测到系统代理时自动替代 `system`；也可 `--route direct` | `direct` |
| `clash` | 独立 mihomo 实例里的某个节点 | system 失败后 | `clash:<节点名>` |
| `pool` | 代理池文件里的某条 HTTP 代理 | clash 也失败后 | `pool:<host>:<port>`，整池为文件路径 |

顺序由配置 `routes` 决定（默认 `["system", "clash", "pool"]`），`--route` 或环境变量 `LD_ROUTES` 可以覆盖。

## 失败分类

| 信号 | 结局 | 处理 |
| --- | --- | --- |
| HTTP 200，内容正确 | ok | 返回并写缓存 |
| HTTP 404 / 410 | not_found | 退出码 3，不换线 |
| HTTP 401 / 403（不是挑战页） | forbidden | 退出码 3，不换线 |
| HTTP 403 / 503，带 `cf-mitigated: challenge` 或 "Just a moment" | challenged | **退出码 6，不换线、不冷却**（整页挑战，与出口无关） |
| HTTP 429（不论有没有挑战页） | rate_limited | 冷却该线路 15 分钟，有 Retry-After 时按它（至少 60 秒），然后换线 |
| HTTP 5xx | server_error | 冷却 60 秒，换线 |
| 连接失败（curl exit 7/28/35/56 …，或代理回了非 200 的 CONNECT） | proxy_error | 冷却 5 分钟（代理池里的单条代理冷却 1 小时），换线；不计入节流 |
| 代理池代理对 CONNECT 回 402 / 407 / 429 | proxy_exhausted | 账号级问题，**整个代理池文件**暂停 6 小时 |

每个请求的停止条件：命中过 linux.do 的失败超过 `max_switches`（默认 2 次）；连接层失败达到 `max_conn_failures`（默认 6 次）；连续两个不同出口都返回 429（判定为全站限流）；或者没有线路可用了。

**只在失败时换线**，不做主动轮换来分摊请求量。换出口是为了从单个 IP 的限频惩罚中恢复，不是为了提高抓取速率：全局节流间隔跨线路、跨进程生效，并且下限是 2 秒。

## 独立 mihomo（clash 线路）

为什么不直接切主 Clash 的节点：

- 主配置里 `anthropic.com`、`claude.ai`、`openai.com` 都走 `🔰 选择节点`，切到香港等不受支持的地区会让正在跑 skill 的 agent 会话断线；
- linux.do 在主 Clash 里走的是兜底组 `🐟 漏网之鱼`（当前为 DIRECT），切 `🔰 选择节点` 根本影响不到它；
- 浏览器里的 linux.do 登录会话也会跟着换 IP。

做法：

1. 内核用 `/Applications/Clash Verge.app/Contents/MacOS/verge-mihomo`（或配置 `clash.binary`，或 PATH 里的 `mihomo`）。
2. 把 Clash Verge 的运行时配置 `clash-verge.yaml` 复制到 `~/.cache/linuxdo-reader/mihomo/nodes.yaml`（权限 0600），作为 file 类型的 proxy-provider。mihomo 只允许 provider 文件放在它的 `-d` 目录里，所以只能复制。
3. 生成最小配置：随机空闲端口，只监听 127.0.0.1，随机 secret，一个 select 组 `LD`（`use: [user]`，按 `clash.include` / `clash.exclude` 过滤），规则只有 `MATCH,LD`。
4. 通过它自己的控制器 `PUT /proxies/LD` 切节点，curl 走它的 mixed-port。
5. 进程结束（包括 SIGTERM）时停掉实例、删除节点副本和配置。如果上次被强杀有遗留，下次启动或执行 `ld.py reset` 时会清理；清理前会核对进程命令行确实指向本 skill 的目录，不会误杀主 Clash。

节点轮换有一个游标（`state.json` 的 `clash_cursor`）：某个节点成功后游标停在它身上，下次优先用它；失败了游标就往后移一位。

默认 `exclude` 为 `🏠|剩余|到期|流量|官网|套餐|重置`：`🏠` 住宅节点依赖主配置里的前置代理组 `🔗 住宅前置`，在独立实例里用不了；其余几个是机场常见的信息节点。

## 代理池（pool 线路）

- 文件：配置 `pool.files`，支持 glob，默认 `["~/Downloads/*proxies*.txt"]`。
- 每行支持三种格式：`scheme://user:pass@host:port`、`host:port`、`host:port:user:pass`。空行和 `#` 开头的行会被忽略，行尾的 `\r` 会被去掉（有的代理商导出的是 CRLF 换行）。
- 每个请求最多随机试 `pool.max_tries`（默认 4）条代理。
- 代理 URL 通过 stdin 的 curl 配置（`-K -`）传给 curl，不会出现在 `ps` 能看到的命令行里；日志里只显示 `host:port`。

判断代理池是否失效：用普通 HTTP 请求（非 CONNECT）经该代理访问任意网址，代理自己回 `429 Not Enough Bandwidth` 说明流量用完，`407` 说明鉴权失败；连上即被重置多半是已过期。续费或更换文件后执行 `ld.py reset` 清掉冷却即可。

## 状态与缓存

| 文件 | 内容 |
| --- | --- |
| `~/.cache/linuxdo-reader/state.json` | `last_request_at`（全局节流）、`routes` 与 `pool_files` 的冷却记录、`clash_cursor` |
| `~/.cache/linuxdo-reader/request.lock` | 跨进程请求锁（flock），多个 ld.py 排队执行 |
| `~/.cache/linuxdo-reader/http/*.json` | 响应缓存，RSS 保留 120 秒、帖子页 600 秒，最多留 200 个文件 |
| `~/.cache/linuxdo-reader/categories.json` | 分类表，24 小时有效；每次读帖子页时顺带刷新 |
| `~/.cache/linuxdo-reader/mihomo/` | 独立实例的目录；运行时才有 `nodes.yaml` / `config.yaml` / `pid` |

## 可调参数（config.json）

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `min_interval` | 5 | 两次请求的最小间隔（秒），下限 2 |
| `routes` | `["system", "clash", "pool"]` | 线路顺序 |
| `system_proxy` | `""` | 手动指定系统代理 |
| `max_switches` / `max_conn_failures` | 2 / 6 | 单个请求的换线上限 |
| `max_pages` | 5 | `topic --pages` 的上限 |
| `cache_ttl.rss` / `cache_ttl.html` | 120 / 600 | 缓存秒数 |
| `cooldown.*` | 见 `ld_config.py` | 各类失败的冷却秒数 |
| `clash.include` / `clash.exclude` | `""` / 见上 | 节点名正则（Go RE2 语法） |
| `clash.binary` / `clash.source_config` | 自动探测 | mihomo 内核与节点来源文件 |
| `pool.files` / `pool.max_tries` | 见上 / 4 | 代理池 |
| `user_agent` | Chrome UA | 用浏览器 UA 才能拿到带 data-preloaded 的页面 |
