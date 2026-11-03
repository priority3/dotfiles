# pr-agent 落地对照（已上线验证）

对象：`pr-agent/client/pr/` 对话页。改前是"工具后台"观感，改后是"内容前置"。
只动了结构与尺寸，**没有动品牌绿 `#a3e635`，也没有换配色方案**——这点很重要，说明观感差距八成来自结构而不是配色。

## 改了什么

| 文件 | 改前 | 改后 | 为什么 |
| --- | --- | --- | --- |
| `MessageList.tsx` | AI 回复套灰底气泡（占屏 60% 面积） | 裸文本 + 一行 11px 元信息（`PR · 已思考 4 秒`） | 面积最大的色块是容器，主角就被压下去了 |
| `MessageList.tsx` | 用户消息纯黑大胶囊 | `--pr-user-card` 浅灰小卡，12px 圆角 | 黑白对撞的强对比会把视线拉到"我"身上，而不是回复上 |
| `MessageList.tsx` | 正文 15px / 行高 1.62 | 14px / 1.78 | 小一档、松一档：同屏更多，但更从容 |
| `Composer.tsx` | 26px 胶囊 | 14px 纸条 | 26px 以上是"聊天 App 拟态"，界面显得比内容重 |
| `Composer.tsx` | 聚焦时荧光绿发光 `0 0 0 3px rgba(163,230,53,.18)` | `border-color` 压到 `--pr-text-2` | 彩色只表状态，不当焦点装饰 |
| `Composer.tsx` | 36px 荧光绿圆形发送钮 | 28px 黑色方块 | 视觉重量原来压在"发送"上，这是全屏最重的元素 |
| `theme.tsx` | `prIn` 含 `scale(.96)` | 只留 `translateY(8px)` | 长列表里每条都缩放弹跳会很吵 |
| `theme.tsx` | — | 新增 `--pr-user-card`、`.pr-tick`、`.pr-check`、`.pr-meta` | 勾选条目与元信息需要 token |
| `PrChat.tsx` | 顶栏 logo 32px 圆形 | 26px 圆角方块；标题 15→14 | 顶栏是"界面"，不该比标题更抢眼 |
| `PrChat.tsx` | 消息区 padding 16px | 18px | 留白是这套规范里唯一"加法"的层级手段 |
| `tasklist.ts`（新） | — | GFM task list 切段 | 见 `checklist-pattern.md` |
| `Checklist.tsx`（新） | — | 可点条目 + localStorage 记忆 | 把"建议"变成"可执行的条目" |
| `prompts-chat.ts` | `别写小作文，别分点罗列（除非他明确要清单）` | `…真要给他几个具体动作时，用 - [ ] 一行一条（2~4 条，每条一句话）` | 不改 prompt，清单永远等不到 |

## 效果

- 屏幕上只剩两处彩色：在线状态点、已勾选的勾选圈。两处都在"该被注意"的位置。
- 同屏消息量增加约 30%，但阅读节奏变慢（行高 1.78）——体感是"更从容"，不是"更挤"。
- 建议从"一段散文"变成"3 条可勾条目 + 底部计数"，产品功能是新增的，不只是外观。

## 回滚

```bash
git checkout client/pr/ server/lib/pr/prompts-chat.ts
rm client/pr/Checklist.tsx client/pr/tasklist.ts
```

## 没做但值得做

- **消息时间戳**：`ServerMsg` 没有 `createdAt`，元信息行只能显示"已思考 4 秒"。要做需服务端 `messages` 表加字段 + 接口回传，属于另一个量级。
- **勾选状态上云**：现在存 localStorage，换设备不跟随。要做就是给 `pr_checks` 一个后端表。

## 一个容易误判的判断

改之前我以为"现有 UI 落后"。实际读 `theme.tsx` 后发现 token 已经很有设计（spring 曲线、毛玻璃、safe-area 变量兜底、`prefers-reduced-motion` 降级都在）。
**所以审查界面时先读 token 文件，再下结论**——很多时候缺的不是设计系统，是结构上让谁当主角。
