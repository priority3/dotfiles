# linux.do 端点与数据结构

linux.do 是 Discourse 站点，前面挂着 Cloudflare。以下内容均为 2026-09-30 实测结果（curl 经系统代理或 Clash 节点访问）。

## 可用端点

| 用途 | 路径 | 返回 | 备注 |
| --- | --- | --- | --- |
| 最新话题 | `/latest.rss` | 30 条话题 | |
| 热门话题 | `/hot.rss` | 30 条话题 | 置顶帖排在最前 |
| Top 话题 | `/top.rss?period=weekly` | 30 条话题 | `period`：daily / weekly / monthly / quarterly / yearly / all |
| 全站最新回帖 | `/posts.rss` | 50 条帖子 | link 形如 `/t/topic/<id>?page=2#post_31` |
| 分类话题 | `/c/<slug>/<id>.rss` | 话题列表 | 只写 `/c/<id>.rss` 会 301 到规范地址（curl `-L` 会跟随） |
| 标签话题 | `/tag/<名称>.rss` | 话题列表 | 中文标签要 URL 编码 |
| 话题最近回帖 | `/t/topic/<id>.rss` | 最近 25 楼，倒序 | guid 形如 `linux.do-post-<话题id>-<楼层>` |
| 用户动态 | `/u/<用户名>/activity.rss` | 帖子 | |
| 用户发起的话题 | `/u/<用户名>/activity/topics.rss` | 话题 | |
| 帖子正文 | `/t/topic/<id>`、`/t/topic/<id>?page=N`（HTML） | 内嵌 JSON | 每页 20 楼，见下文 |
| 分类表 | `/categories`（HTML） | 内嵌 JSON | 其实任意 HTML 页都带 `site.categories` |

群组（`/g/<群组>/posts.rss`、`/g/<群组>/mentions.rss`）和徽章（`/badges/<id>/<slug>.rss`）是 Discourse 的标准 RSS，可用 `ld.py rss <路径>` 读取，本次没有实测。

## 不可用端点

| 路径 | 表现 |
| --- | --- |
| 所有 `.json` 接口（`/latest.json`、`/t/<id>.json` …） | `403` + `cf-mitigated: challenge`，与 UA、出口 IP 无关 |
| 站内搜索 `/search?q=…` | 同上，system 与 3 个不同 Clash 节点全部 403 挑战 |

## RSS 字段

话题类 feed（latest / hot / top / 分类 / 标签 / 用户话题）的每个 `<item>`：

- `title`、`link`（`/t/topic/<id>`）、`pubDate`（RFC 822，UTC）、`dc:creator`（用户名）、`category`（分类名）
- `description`：首帖 cooked HTML，末尾追加 `<p><small>N 个帖子 - M 位参与者</small></p>` 和「阅读完整话题」链接（ld.py 会把这两段剥掉，统计数单独输出）
- `discourse:topicPinned` / `topicClosed` / `topicArchived`：`Yes` / `No`
- `guid`：`linux.do-topic-<id>`

帖子类 feed（posts / 话题 RSS / 用户动态）：`guid` 含 `-post-`；`dc:creator` 在 posts.rss 里形如 `@user user`，在话题 RSS 里是纯用户名；`description` 是该楼的 cooked HTML。

## 帖子页内嵌 JSON（data-preloaded）

浏览器 UA 访问帖子页时，页面里有 `<script type="application/json" id="data-preloaded">`：

- 内容本身就是合法 JSON（`<` 已转义成 `\u003c`），**不要**再做 HTML 反转义，否则正文里的 `&quot;` 之类会被破坏。
- 键：`topic_<id>`、`site`、`siteSettings`、`customEmoji` 等；多数值是**二次编码的 JSON 字符串**，需要再 `json.loads` 一次。
- `topic_<id>`：`title`、`posts_count`、`views`、`like_count`、`participant_count`、`category_id`、`tags`（对象数组 `{id, name, slug}`）、`created_at`、`closed`、`chunk_size`（20）、`details.created_by`、`post_stream.posts`（本页 20 楼）、`post_stream.stream`（全部楼层的 post id，用来算总页数和当前页）。
- 每楼：`post_number`、`username`、`name`、`created_at`、`cooked`、`reply_to_post_number`、`reactions`（`[{id, type, count}]`）、`actions_summary`。linux.do 装了 discourse-reactions，`actions_summary` 里 `id=2` 的 `count` 等于所有表情回应的总数。
- `site.categories`：17 个分类，包括子分类（带 `parent_category_id`），字段有 `id`、`slug`、`name`、`description_text`、`topic_count`。

非浏览器 UA 拿到的是 Discourse 的「爬虫版」HTML（`crawler-post` 结构，没有 data-preloaded），ld.py 不解析这个版本。

## Cloudflare 行为（实测记录）

| 条件 | 结果 |
| --- | --- |
| curl + 浏览器 UA 或非浏览器 UA，经系统代理 | RSS 和帖子页 200 |
| Python urllib + 任意 UA，同一出口 | RSS 也是 403 挑战（按客户端指纹拦截） |
| 本机不走代理直连 | 20 秒超时 |
| 约 10 分钟内 20 多次请求（其中 11 次间隔 3 秒） | 该出口 IP 此后所有请求都是 `429` + `cf-mitigated: challenge`，不到 20 分钟自动解除 |
| 限频期间换成 Clash 节点出口 | 立即恢复 200 |

参考：此前另一个抓取脚本用 5 秒间隔连续抓 25 个帖子页，也碰到过 429。所以默认节流设为 5 秒，并且优先用列表 RSS，少抓帖子页。
