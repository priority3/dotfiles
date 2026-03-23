# 隐私路径索引

本技能只做“路径索引”，不在 skill 内容里保存任何真实敏感值。

## 约定目录

- `~/.ssh/fanqie/`
- `<repo>/.env.local`

推荐文件：

- `~/.ssh/fanqie/default.env`
- `~/.ssh/fanqie/default.env.example`
- `<repo>/.env.local`

可选拆分：

- `~/.ssh/fanqie/<book-or-scene>.env`

## 分层规则

`~/.ssh/fanqie/*.env` 只放敏感认证。

`<repo>/.env.local` 只放当前项目上下文缓存，例如：

- `FQ_BOOK_ID`
- `FQ_BOOK_NAME`
- `FQ_VOLUME_NAME`
- `FQ_SOURCE_FILE`
- `FQ_TITLE_FROM`
- `FQ_TITLE_OVERRIDE`

不要把以下变量长期放进仓库：

- `FQ_COOKIE`
- `FQ_CSRF_TOKEN`
- `FQ_MS_TOKEN`
- `FQ_A_BOGUS_*`
- `FQ_NEW_ARTICLE_MS_TOKEN`
- `FQ_NEW_ARTICLE_A_BOGUS`
- `FQ_DRAFT_LIST_MS_TOKEN`
- `FQ_DRAFT_LIST_A_BOGUS`

## 输出规则

允许：

- “读取 `~/.ssh/fanqie/default.env` 中的 `FQ_COOKIE`、`FQ_CSRF_TOKEN`”
- “读取项目 `.env.local` 中的 `FQ_BOOK_ID`、`FQ_BOOK_NAME` 以确认当前仓库绑定哪本书”
- “缺少 `FQ_DRAFT_LIST_A_BOGUS`，需要去最新抓包补齐”

不允许：

- 直接粘贴完整 Cookie
- 直接粘贴完整 `msToken`
- 把敏感 env 回写进仓库
- 在日志或截图里暴露全量 header
- 把 `FQ_COOKIE`、`FQ_CSRF_TOKEN` 之类复制进项目 `.env.local`

## 调试规则

- 先确认文件是否存在，再确认变量名是否存在，最后才在本地读取值。
- 若必须展示错误上下文，只显示：
  - 文件路径
  - 变量名
  - 打码后的前后几位
- 示例：`FQ_MS_TOKEN=abc...xyz`

## 文件权限

推荐权限：

```bash
chmod 700 ~/.ssh/fanqie
chmod 600 ~/.ssh/fanqie/*.env
```

## 变量建议

认证：

- `FQ_COOKIE`
- `FQ_CSRF_TOKEN`
- `FQ_MS_TOKEN`
- `FQ_A_BOGUS`
- `FQ_A_BOGUS_COVER`
- `FQ_A_BOGUS_HISTORY`
- `FQ_NEW_ARTICLE_MS_TOKEN`
- `FQ_NEW_ARTICLE_A_BOGUS`
- `FQ_DRAFT_LIST_MS_TOKEN`
- `FQ_DRAFT_LIST_A_BOGUS`

项目上下文：

- `FQ_BOOK_ID`
- `FQ_BOOK_NAME`
- `FQ_VOLUME_ID`
- `FQ_VOLUME_NAME`
- `FQ_SOURCE_FILE`
- `FQ_TITLE_FROM`
- `FQ_TITLE_OVERRIDE`

说明：

- `FQ_BOOK_ID` 是项目级默认书籍 ID。
- `FQ_BOOK_NAME` 是给 skill 与操作者阅读的元数据，当前脚本不强依赖。
- 项目级变量默认都只是“减少重复调用”的缓存项；缺失时，skill 应继续通过上下文或接口补齐，而不是直接报缺少配置。
- 默认优先维护一份通用 `FQ_A_BOGUS`；只有确认某个接口必须单独签名时，再补对应的分接口字段。
