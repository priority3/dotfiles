# Current API Map

本文件用于快速判断“目标动作是否已有脚本封装”，减少手写 `curl`。

## 已封装（优先走脚本）

- `book_list/v1`：`scripts/fanqie-api.ts book-list`
- `book_detail/v1`：`scripts/fanqie-api.ts book-detail`
- `volume_list/v1`：`scripts/fanqie-api.ts volume-list`
- `volume/modify/v0`：`scripts/fanqie-api.ts volume-modify`
- `draft_list/v1`：`scripts/fanqie-api.ts draft-list`
- `chapter_list/v1`：`scripts/fanqie-api.ts chapter-list`
- `new_article/v0`：`scripts/fanqie-autosave.ts run --create-new`
- `cover_article/v0`：`scripts/fanqie-autosave.ts run`（新建或覆盖流）
- `save_doc_history/v0`：`scripts/fanqie-autosave.ts run`（写入后保存历史）

## 未封装（按文档原始请求）

- `publish_article/v0`：修改已发布章节时按 `fanqie/api-doc.md` 手工请求
- `add_volume/v0`：新建分卷时按 `fanqie/api-doc.md` 手工请求

## 执行准则

1. 先看脚本真实行为，再看文档描述。
2. 同名能力若脚本和文档冲突，以脚本为准。
3. 原始请求必须标注“当前走原始请求，不走脚本封装”。
