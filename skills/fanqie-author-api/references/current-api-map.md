# 当前 API 映射

本技能的事实源优先级：

1. 当前工作区 `fanqie/api-doc.md`
2. 当前工作区 `scripts/fanqie-api.ts`
3. 当前工作区 `scripts/fanqie-autosave.ts`

如果路径不存在，先在当前工作区用 `rg --files | rg 'fanqie|autosave'` 重找，不要直接假设仓库结构。

## 已封装到脚本

`scripts/fanqie-api.ts` 目前支持：

- `new-article` -> `new_article/v0`
- `cover-article` -> `cover_article/v0`
- `save-history` -> `save_doc_history/v0`
- `draft-list` -> `chapter/draft_list/v1`
- `chapter-list` -> `chapter/chapter_list/v1`
- `book-detail` -> `book/book_detail/v0`
- `book-list` -> `book/book_list/v0`
- `volume-list` -> `volume/volume_list/v1`

`scripts/fanqie-autosave.ts` 目前支持：

- `run`
- `schedule`
- `print-cron`

它会把 Markdown 正文转换成番茄需要的 HTML 段落格式，并串起草稿保存流程。

## 文档已知、脚本尚未封装

以下接口在 `fanqie/api-doc.md` 中已有说明，但当前仓库脚本尚未暴露独立命令：

- `add_volume/v0`
- `publish_article/v0`

处理原则：

- 单次任务：按本地文档拼原始请求。
- 反复任务：优先补 TypeScript 封装，再执行。

## 认证最小集合

最小可用：

- `FQ_COOKIE`
- `FQ_CSRF_TOKEN`
- `FQ_MS_TOKEN`
- `FQ_A_BOGUS`

常见补充：

- `FQ_REFERER`
- `FQ_USER_AGENT`

只在通用签名失效时再补分接口变量：

- `FQ_A_BOGUS_COVER`
- `FQ_A_BOGUS_HISTORY`
- `FQ_NEW_ARTICLE_MS_TOKEN`
- `FQ_NEW_ARTICLE_A_BOGUS`
- `FQ_DRAFT_LIST_MS_TOKEN`
- `FQ_DRAFT_LIST_A_BOGUS`

默认业务参数：

- `FQ_AID=2503`
- `FQ_APP_NAME=muye_novel`

## 当前脚本直接消费的项目级变量

当前 TypeScript 脚本会直接读取这些变量：

- `FQ_BOOK_ID`
- `FQ_VOLUME_ID`
- `FQ_VOLUME_NAME`
- `FQ_SOURCE_FILE`
- `FQ_TITLE_FROM`
- `FQ_TITLE_OVERRIDE`
- `FQ_STRIP_FIRST_HEADING`
- `FQ_CREATE_NEW`
- `FQ_LOOKUP_DRAFT`
- `FQ_DRAFT_LIST_PAGE_INDEX`
- `FQ_DRAFT_LIST_PAGE_COUNT`
- `FQ_INTERVAL_MINUTES`
- `FQ_RUN_IMMEDIATELY`

当前 skill 额外建议在项目根 `.env.local` 中维护：

- `FQ_BOOK_NAME`

它用于帮助判断“当前仓库绑定的是哪本书”，但当前脚本不会直接消费它。

说明：

- 这些项目级变量是“可选缓存”，不是 skill 的硬前置条件。
- 若 `.env.local` 缺失其中一部分，skill 应优先继续从仓库上下文、发布记录、卷纲、最近请求或番茄查询接口中补齐。
- 维护这些变量的主要价值是减少重复调用、减少重复确认，而不是把 skill 绑死在 env 上。

## 典型判断

- 查书：`book-list` / `book-detail`
- 查卷：`volume-list`
- 查草稿：`draft-list`
- 查已发布章节：`chapter-list`
- 新草稿：`new-article`
- 覆盖草稿：`cover-article`
- 生成历史：`save-history`
- 自动化落草稿：`fanqie-autosave.ts run`
