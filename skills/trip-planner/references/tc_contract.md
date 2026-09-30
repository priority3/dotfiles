# 同程程心输出契约（红线摘要）

上游 `tc-chengxin` 的 SKILL.md 对输出有强约束。本 skill 在其之上做聚合，
**不得违反这些约束**，否则同程侧视为输出失败。

完整原文见 `~/.workbuddy/connectors/skills/connector-tc-chengxin/SKILL.md`。

---

## 一、必须原样输出 `markdown`

脚本返回的 JSON 里，`markdown` 字段是最终回复正文，**逐字原样输出**。

```
responsePolicy.finalAnswerField = "markdown"
responsePolicy.mode = "verbatim"
responsePolicy.mustNotRewriteMarkdown = true
```

禁止：
- 用 `summaryMarkdown` 替代 `markdown`
- 自己写「已为你查到 N 条，详见右侧」之类的摘要替代
- 压缩、重排、改写表格
- 因为「列太宽」「手机端不好看」删列

## 二、`预订` 列不可删且必须在最后一列

机票 / 火车 / 汽车表格的 `预订` 列包含 PC 预订链接、手机打开链接、二维码，
**三者都不能删**。表头顺序也必须保持脚本原文：

| 业务 | 强制表头顺序 |
| --- | --- |
| 机票 | `序号 \| 航班 \| 出发到达 \| 日期 \| 时间 \| 时长 \| 价格 \| 预订` |
| 火车 | `序号 \| 车次 \| 出发到达 \| 日期 \| 时间 \| 历时 \| 票价/席别 \| 预订` |
| 汽车 | `序号 \| 班次 \| 出发到达 \| 日期 \| 时间 \| 车程 \| 票价 \| 预订` |

## 三、必须保留的段落

- 顶部的「推荐建议」/「行程安排建议」（脚本基于接口结果生成）
- 末尾的「客服支持」段落（同程 7×24 客服信息）
- `travel-query` 返回的 Day 1 / Day 2 / Day 3 行程安排，不得压缩成资源列表

## 四、本 skill 如何在不违约的前提下做聚合

**分层，不覆写。**

```
报告结构
├─ 「方案比选」节      ← 本 skill 新增的聚合视图
├─ 「费用明细」节      ← 本 skill 新增（cost_table.py）
├─ 「行程与地图」节    ← 本 skill 新���（route_map.html）
└─ 「资源与预订」节    ← 同程 markdown 原文，一字不动
```

关键点：
- 聚合表是**另起一节的新表**，不是把同程表格改写成另一个样子
- 聚合表里的价格只是**引用**同程报价，同程原表继续完整存在于「资源与预订」节
- `extract_visual_json.py --prices` 只**读取**不修改，产出独立的报价数据
- 如果篇幅太长，可以把同程���文放在报告末尾或折叠区，但**不能删**

## 五、宿主差异：present_files

同程 SKILL.md 要求用 `present_files` 展示 HTML。

| 宿主 | 处理 |
| --- | --- |
| WorkBuddy | 正常调用 `present_files` 展示 `htmlFilePath` |
| Claude Code | **没有该工具** → 输出 HTML 绝对路径，提示用浏览器打开 |

注意 `presentFilesIsSupplementOnly=true`：HTML 只是补充，
**对话内的 markdown 才是正文**，两个宿主下都成立。

## 六、失败降级

| 场景 | 处理 |
| --- | --- |
| token 失效 | 提示去 WorkBuddy「连应用」重连「同程旅行」，不要求用户手输 Key |
| 参数不足 | 只问缺失的关键参数 |
| 无结果 | 输出脚本的无结果提示 + 建议调整日期/城市/偏好 |
| HTML 生成失败 | 输出 `markdown`，并说明 `fallbackReason` |
| 二维码缺失 | 保留 PC / 手机链接，**不编造二维码** |
| 网关失败 | 输出脚本错误信息，**不补充未返回的价格/余票** |

## 七、路由：一次查询用一个脚本

- 用户明说机票/火车/酒店/景区/汽车/度假 → 用对应专用脚本
- 用户说「规划行程 / 玩几天 / 三日游 / 自由行」→ **一次** `travel-query`，
  不要拆成多个脚本分别调用
- 用户只问「怎么走 / 有哪些交通方式」→ `traffic-query`
- 参数不足时先补齐，不要用不匹配的脚本替代
