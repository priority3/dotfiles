---
name: fanqie-author-api
description: 适用于番茄作者后台 API 与草稿工作流。基于当前工作区的 fanqie/api-doc.md、scripts/fanqie-api.ts、scripts/fanqie-autosave.ts 执行书籍列表/卷列表/卷名修改、草稿列表/已发布章节列表查询、章节统计查询、草稿新建与覆盖保存、保存历史，并按“项目级 .env.local 仅作上下文缓存、~/.ssh/fanqie/*.env 保存私密认证”的分层约定工作。触发词：番茄/Fanqie/番茄作者后台/草稿保存/cover_article/new_article/draft_list/chapter_list/stats/chapter_list_v1/章节统计/跟读率/读完率/流失率/volume_list/volume_modify/modify_volume/改卷名/book_list/book_detail/publish_article/add_volume。
---

# Fanqie Author API

## 适用前提

- 先用 `rg --files` 确认当前工作区存在以下文件，再开始执行：
  - `fanqie/api-doc.md`
  - `scripts/fanqie-api.ts`
  - `scripts/fanqie-autosave.ts`
- 当前仓库的默认位置是 `/Users/moka/Documents/da-code/readnote`。如果不在这个仓库，先定位等价文件，再继续。

## 执行优先级

1. 用户本轮硬约束。
2. 本地 `fanqie/api-doc.md`。
3. `scripts/fanqie-api.ts` 与 `scripts/fanqie-autosave.ts` 的真实实现。
4. 本 skill 的默认流程。

若文档与脚本冲突：
- 已封装命令，以脚本真实行为为准。
- 尚未封装的接口，以 `fanqie/api-doc.md` 为准，并明确说明“当前走原始请求，不走脚本封装”。

## 配置分层

默认按四层解析，不要把“项目上下文”和“敏感认证”混在一起：

1. CLI flags：本次命令临时覆盖，优先级最高。
2. 项目级 `.env.local`：可选缓存当前仓库的书籍与写作上下文，用来避免重复查询，不是必填事实源。
3. `~/.ssh/fanqie/*.env`：保存认证、签名、浏览器抓包字段等敏感值。
4. 脚本默认值。

项目级 `.env.local` 允许保存：

- `FQ_BOOK_ID`
- `FQ_BOOK_NAME`
- `FQ_VOLUME_NAME`
- `FQ_SOURCE_FILE`
- `FQ_TITLE_FROM`
- `FQ_TITLE_OVERRIDE`
- `FQ_STRIP_FIRST_HEADING`
- `FQ_LOOKUP_DRAFT`
- `FQ_CREATE_NEW`
- `FQ_DRAFT_LIST_PAGE_INDEX`
- `FQ_DRAFT_LIST_PAGE_COUNT`
- `FQ_INTERVAL_MINUTES`
- `FQ_RUN_IMMEDIATELY`

说明：

- 这些项目级变量默认都视为“缓存命中项”，不是强制配置项。
- 若 `.env.local` 缺少 `FQ_BOOK_ID`、`FQ_VOLUME_NAME`、`FQ_SOURCE_FILE` 等业务变量，skill 应先尝试从当前仓库文件、发布记录、卷纲、最近请求上下文或番茄查询接口中补齐，不要把“项目级 env 缺失”直接视为阻塞。
- `FQ_BOOK_ID`、`FQ_VOLUME_NAME`、`FQ_SOURCE_FILE` 适合放在 `.env.local`，主要是为了减少重复调用或重复确认。
- `FQ_BOOK_NAME` 作为供 skill 阅读的人类可读元数据使用，便于确认“当前项目对应哪本书”；当前 TypeScript 脚本不直接消费它。
- 若 `.env.local` 里出现 `FQ_COOKIE`、`FQ_CSRF_TOKEN`、`FQ_MS_TOKEN`、`FQ_A_BOGUS_*`，视为旧布局，优先建议迁回 `~/.ssh/fanqie/*.env`。

## 隐私与路径索引

- 所有 Cookie、CSRF、`msToken`、`a_bogus` 一律放在 `~/.ssh/fanqie`，不要写回仓库。
- 先读 [references/privacy-path-index.md](references/privacy-path-index.md)。
- 默认只展示“路径 + 变量名”，不要在聊天、提交、文档、日志里回显真实值。
- 只有在排查失败请求时，才读取敏感文件；对外输出必须打码。
- 允许并推荐 repo 内 `.env.local` 保存非敏感项目上下文，但不要把认证信息写进去。

## 默认 env 布局

- 当前项目根目录 `.env.local`：可选缓存当前仓库绑定的业务上下文，如 `FQ_BOOK_ID`、`FQ_BOOK_NAME`、`FQ_VOLUME_NAME`、`FQ_SOURCE_FILE`；没有这些值时，skill 应继续通过仓库上下文或番茄接口自行补齐。
- `~/.ssh/fanqie/default.env`：通用认证与签名字段，不放项目私有书籍说明。
- `~/.ssh/fanqie/*.env`：可按书或场景拆分认证，但仍只做“路径索引”，不在 skill 中硬编码真实值。
- 若需要模板，使用 `~/.ssh/fanqie/default.env.example` 复制为 `default.env`。

若当前仓库已有旧版 `.env.local` 且里面带认证字段，处理顺序：

1. 保留 `FQ_BOOK_ID`、`FQ_VOLUME_NAME`、`FQ_SOURCE_FILE` 等项目缓存变量在 `.env.local`；若这些变量不存在，也不视为错误。
2. 把 `FQ_COOKIE`、`FQ_CSRF_TOKEN`、`FQ_MS_TOKEN`、`FQ_A_BOGUS_*` 迁到 `~/.ssh/fanqie/default.env`。
3. 后续命令改为先 source 私密 env，再 source 项目 `.env.local`。

## 快速路由

- 书籍、分卷、草稿、已发布章节查询：`scripts/fanqie-api.ts`
- 分卷改名：`scripts/fanqie-api.ts volume-modify`
- 一次性草稿保存、自动保存、cron 示例：`scripts/fanqie-autosave.ts`
- 文档已知但当前脚本未封装：`publish_article/v0`、`add_volume/v0`、`stats/chapter_list_v1/v0`

## 常用命令

推荐统一用“先 source 私密 env，再 source 项目 `.env.local`”的方式执行。这样既兼容当前仓库脚本默认读 `.env.local`，又不会把认证写回仓库。

基础模板：

```bash
set -a
source "$HOME/.ssh/fanqie/default.env"
[ -f ./.env.local ] && source ./.env.local
set +a
node --experimental-strip-types scripts/fanqie-api.ts book-list
```

说明：

- 不默认使用 `npm run autosave:*`，因为它只传 `--env-file=.env.local`，适合“所有变量都已放在 repo env” 的旧布局。
- 若用户明确采用旧布局，才继续沿用 `node --env-file=.env.local ...` 或 npm scripts。

查询作品列表：

```bash
set -a
source "$HOME/.ssh/fanqie/default.env"
[ -f ./.env.local ] && source ./.env.local
set +a
node --experimental-strip-types scripts/fanqie-api.ts book-list
```

查询卷列表：

```bash
set -a
source "$HOME/.ssh/fanqie/default.env"
[ -f ./.env.local ] && source ./.env.local
set +a
node --experimental-strip-types scripts/fanqie-api.ts volume-list --book-id "<BOOK_ID>"
```

修改分卷名：

```bash
set -a
source "$HOME/.ssh/fanqie/default.env"
[ -f ./.env.local ] && source ./.env.local
set +a
node --experimental-strip-types scripts/fanqie-api.ts volume-modify \
  --book-id "<BOOK_ID>" \
  --volume-id "<VOLUME_ID>" \
  --volume-name "第一卷：血囚入阙" \
  --ms-token "<MS_TOKEN>" \
  --a-bogus "<A_BOGUS>"
```

查询草稿列表：

```bash
set -a
source "$HOME/.ssh/fanqie/default.env"
[ -f ./.env.local ] && source ./.env.local
set +a
node --experimental-strip-types scripts/fanqie-api.ts draft-list --book-id "<BOOK_ID>" --page-count 50
```

新建草稿并上传正文：

```bash
set -a
source "$HOME/.ssh/fanqie/default.env"
[ -f ./.env.local ] && source ./.env.local
set +a
node --experimental-strip-types scripts/fanqie-autosave.ts run \
  --source "正文/第014章_董事会里的临时动议.md" \
  --book-id "<BOOK_ID>" \
  --volume-name "<卷名>" \
  --create-new
```

按标题查已有草稿并覆盖：

```bash
set -a
source "$HOME/.ssh/fanqie/default.env"
[ -f ./.env.local ] && source ./.env.local
set +a
node --experimental-strip-types scripts/fanqie-autosave.ts run \
  --source "正文/第014章_董事会里的临时动议.md" \
  --book-id "<BOOK_ID>" \
  --lookup-draft
```

## 工作流

1. 先读 [references/current-api-map.md](references/current-api-map.md)，确认本次目标接口是否已被脚本封装。
2. 先确认配置来源：优先看 CLI flags；项目根 `.env.local` 里的 `FQ_BOOK_ID`、`FQ_BOOK_NAME`、`FQ_VOLUME_NAME`、`FQ_SOURCE_FILE` 只当作快捷缓存；若缺失，则继续用私密 env 提供认证，并从仓库上下文、最近请求或番茄查询接口补齐业务参数。
3. 变更远端内容前，先确认 `source`、标题、`book_id`、`volume_id`/`volume_name`。
4. Markdown 上传优先走脚本，让脚本负责转成 `<p>` + `<br>` HTML。
5. 若是草稿写入，优先走：
   - `new_article/v0` -> `cover_article/v0` -> `save_doc_history/v0`
   - 或 `draft_list/v1` -> `cover_article/v0` -> `save_doc_history/v0`
6. 若是修改已发布章节：
   - 先用 `chapter_list/v1` 找到正式文章 `item_id`
   - 再按文档调用 `publish_article/v0`
   - 不要把草稿 `item_id` 和正式文章 `item_id` 混用
7. 若是查询章节统计：
   - 当前优先按文档调用原始 `stats/chapter_list_v1/v0`
   - `stats_type=3` 重点看 `read_completion_rate`（章节读完率）与 `loss_rate`（章节流失率）
   - `stats_type=4` 重点看 `follow_read_rate`（章节跟读率）
   - 这些统计字段当前都按字符串返回，落库优先保留原始字符串
8. 若是修改分卷名：
   - 先用 `volume_list/v1` 确认目标 `volume_id`
   - 再优先用 `scripts/fanqie-api.ts volume-modify`
   - `volume_data` 必须按 JSON 字符串传，不能拆成多个表单字段
9. 若是新建分卷：
   - 按文档调用 `add_volume/v0`
   - 若返回 `code = -4054`，先给现有空分卷创建至少 1 个章节，再重试

## 失败排查

- HTTP 非 2xx 或 `code != 0`，优先怀疑：
  - `FQ_COOKIE`
  - `FQ_CSRF_TOKEN`
  - `FQ_MS_TOKEN`
  - `FQ_A_BOGUS_*`
- 需要刷新时，从浏览器开发者工具重新抓：
  - `cover_article/v0`
  - `save_doc_history/v0`
  - `new_article/v0`
  - `draft_list/v1`
  - `volume/modify/v0`
- 若只是查询失败，先验证同一份 env 能否跑通 `book-list`，再缩小到具体接口。

## 注意事项

- `content` 提交的是 HTML，不是 Markdown。
- 若脚本可用，不要手写 HTML 转换逻辑。
- 标题要保持文件名、文内标题、平台标题一致。
- 不要把缺少项目级 `FQ_BOOK_ID` / `FQ_VOLUME_NAME` 视为硬阻塞；这些值优先当作缓存，不在时应继续推导或查询。
- 书籍 ID 与书名优先从项目根 `.env.local` 快速命中当前上下文；未命中时，再由 skill 主动查询，不要把仓库绑死在 env 上。
- 若用户要做重复任务，优先在现有 TypeScript 脚本里补封装，而不是每次手写 `curl`。
