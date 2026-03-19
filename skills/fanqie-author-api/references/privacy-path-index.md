# Privacy Path Index

本文件定义 Fanqie skill 的敏感信息存放与输出规则。

## 存放规则

- 项目上下文（非敏感）：
  - 仓库根 `.env.local`
  - 可放：`FQ_BOOK_ID`、`FQ_BOOK_NAME`、`FQ_VOLUME_NAME`、`FQ_SOURCE_FILE` 等
- 认证与签名（敏感）：
  - `~/.ssh/fanqie/default.env`
  - `~/.ssh/fanqie/*.env`
  - 可放：`FQ_COOKIE`、`FQ_CSRF_TOKEN`、`FQ_MS_TOKEN`、`FQ_A_BOGUS_*`

## 输出规则

- 默认只输出“路径 + 变量名”，不输出变量值。
- 仅在故障排查时读取敏感值，且对外必须打码。
- 聊天、提交、文档、日志中禁止回显完整 Cookie、Token、签名串。

## 迁移规则（旧布局）

如果仓库 `.env.local` 里已有敏感字段：

1. 保留项目上下文变量在 `.env.local`。
2. 把认证字段迁到 `~/.ssh/fanqie/default.env`。
3. 运行命令时先 `source ~/.ssh/fanqie/default.env`，再 `source ./.env.local`。

## 最小检查清单

- 检查命令是否使用了私密 env：`source "$HOME/.ssh/fanqie/default.env"`
- 检查仓库是否未提交敏感字段：`git diff -- .env.local`
- 对外回复是否无明文凭据
