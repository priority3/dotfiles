# 华图在线页面与数据来源

| 用途 | URL | 关键文本特征 |
|---|---|---|
| 题库首页（各模块进度） | `https://v.huatu.com/tiku/` | `模块名 已做 N/M 题`，父子节点都会出现 |
| 评估报告（累计数据） | `https://v.huatu.com/tiku/myreport` | 标签在前、数值在后两行的顺序：`22题` / `做题数量` |
| 答题记录 | `https://v.huatu.com/tiku/myxlist` | 每条以 `智能刷题--202610301347` 这类标题开头 |
| 错题重练 | `https://v.huatu.com/tiku/myerror` | `模块名（共 N 道错题）` |
| 收藏夹 | `https://v.huatu.com/tiku/mycollect` | 手动收藏，通常为空 |

## 登录态 cookie（v.huatu.com）

必需：`UserName`、`UserID`、`ht_token`、`ht_id`、`jtoken`
有其一即可判定已登录；`synlogin`、`ucId`、`userCode` 提供辅助身份信息。

## 接口（仅供参考，未使用）

站内 API 基座是 `api.huatu.com/lumenapi/v4/…`、`ns.huatu.com/…`，直接调需要签名参数，
因此本技能走"渲染后读 DOM"的路子，稳定、不用逆向签名。

## 评估报告数值顺序

页面是「数值 → 标签」的布局，抓取时要用 `数值\n标签` 的正则反推：

```
22题        做题数量
59.09%      正确率
150.23秒/题  做题速度
0名          全站排名
55′05″      累计做题时长
1天          练习天数
```
