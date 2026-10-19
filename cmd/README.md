# cmd

随手可跑的一键脚本。脚本都放在这里，另一台电脑 clone 完 dotfiles 直接执行。

## tokscale-join.sh

把当前电脑接入自建的 AI 用量统计面板 <https://token.razet.me>，作为一个**新用户**上报。

```bash
./tokscale-join.sh                 # 主机名当用户名，SSH 自动发 token
./tokscale-join.sh --user alice    # 指定面板上的用户名
./tokscale-join.sh --token tt_xxx  # 已有 token，跳过发号
```

执行完会做四件事：

1. 在服务端注册用户并拿到 API token（或复用已有的）
2. 在 `~/.tokscale-hub/pkg` 里装一份独立的 tokscale CLI（不污染全局 node_modules）
3. 写 `~/.tokscale-hub/env` 和 `sync.sh`，并往 `~/.zshrc` 挂一个开终端时的兜底同步钩子
4. 立刻上报一次

之后：

- 开终端会自动同步（距上次超过 6 小时才触发，不会拖慢启动）
- 想要系统级每 4 小时定时，执行一次 `bash ~/.tokscale-hub/activate-timer.command`
  （macOS 走 launchd，Linux 走 crontab）

### token 从哪来

按优先级依次尝试，前三条都不需要人工介入：

1. `--token` 参数
2. 本机 `~/.tokscale-hub/env` 里已有的（重复执行直接复用，不会重复建号）
3. `ssh tencent-cvm` 到服务器跑 `/opt/tokscale-ops/bootstrap-user.sh` 自动建号发号
4. 都不通，就交互提示粘贴管理员发的 token

> 本仓库是公开的，脚本里没有任何密钥。token 只存在本地 `~/.tokscale-hub/env`（权限 600）。

### 服务器侧

面板跑在腾讯云 150.158.131.143 的 `/opt/tokscale-hub`（Docker Compose：Next.js + Postgres），
域名经 Cloudflare Tunnel 暴露。登录面板的账号密码找管理员要。
发号脚本在服务器 `/opt/tokscale-ops/bootstrap-user.sh`。
