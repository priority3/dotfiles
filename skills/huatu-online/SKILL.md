---
name: huatu-online
description: "读取华图在线（v.huatu.com）账号的刷题数据：累计做题量与正确率、做题速度、练习天数、各模块已做进度（含资料分析细分题型）、答题记录、错题本分布。Use when the user asks about 华图/华图在线/v.huatu.com 的刷题进度、做题记录、正确率、错题、评估报告，或要把华图刷题数据导入自己的看板/数据库。Read-only：只读取，绝不提交答案、不改账号数据。"
---

# 华图在线刷题数据读取

复用本机 Chrome 里已登录的会话，读取 v.huatu.com 的做题数据并输出 JSON。**全程只读**。

## 前置条件

- macOS，已安装 Google Chrome，且**在 Chrome 里登录着华图在线**（cookie 带 `UserName`/`ht_token`）
- `node`、`python3`、`openssl` 可用

## 快速开始

```bash
~/.workbuddy/skills/huatu-online/scripts/run.sh all        # 全量
~/.workbuddy/skills/huatu-online/scripts/run.sh report     # 只要累计数据
~/.workbuddy/skills/huatu-online/scripts/run.sh progress   # 只要各模块进度
~/.workbuddy/skills/huatu-online/scripts/run.sh records    # 只要答题记录
~/.workbuddy/skills/huatu-online/scripts/run.sh errors     # 只要错题分布
```

stdout 是纯 JSON，诊断信息走 stderr，可直接 `| jq` 或 `| python3 -c`。

## 输出结构

```jsonc
{
  "fetchedAt": "2026-10-30T06:59:11.386Z",
  "cookiesInjected": 33,
  "account": { "name": "app_ztk…", "uid": "0" },
  "progress": {
    "rows": [{ "name": "资料分析", "done": 20, "total": 6548 }, …],  // 含细分题型
    "sumDone": 0,          // ⚠ 父子模块重复计数，别当总数用
    "rowCount": 70
  },
  "report": {
    "totalQuestions": "22", "accuracy": "59.09",
    "secPerQuestion": "150.23", "rank": "0名",
    "duration": "55′05″", "practiceDays": "1", "hasWeekly": true
  },
  "records": { "count": 11, "items": [{ "title": "智能刷题--202610301347",
               "type": "智能刷题", "submitted": true,
               "at": "2026年10月30日 14:10", "correct": 6, "total": 10 }, …] },
  "errors":  { "total": 22, "list": [{ "module": "资料分析", "count": 7 }, …] }
}
```

## 工作流

1. `run.sh` 先跑 `huatu_cookies.py`：从 Chrome 的 Cookies 库解密 huatu 域 cookie，写到 `/tmp/huatu_cookies.json`
2. 启动一个**独立 profile 的无头 Chrome**（端口 9231，`/tmp/huatu-skill-profile`），通过 CDP 注入 cookie
3. 依次访问题库页 / 评估报告 / 答题记录 / 错题重练，用正则从 `document.body.innerText` 提取
4. 退出时自动关闭浏览器

## 细节与坑（改脚本前必读）

- **cookie 解密**：Keychain 里的 `Chrome Safe Storage` 作口令，PBKDF2-SHA1(`saltysalt`, 1003 轮, 16 字节) → AES-128-CBC，IV 是 16 个空格；**Chrome 130+ 会在明文前加 32 字节域摘要，必须去掉**，否则值里带乱码。二进制 cookie（如 `_nb_ioWEgULi`）跳过。
- **CDP `Network.setCookie`**：`domain` 不能带前导点（要用 `v.huatu.com` 而不是 `.v.huatu.com`），否则报 `Invalid cookie fields`。
- **stdout 必须干净**：脚本里任何 `print` 都要重定向到 stderr，否则混进 JSON 会让下游解析失败（踩过）。
- **数据是懒加载的**：错题本初始只渲染 2–3 个模块，等 4 秒以上才全；答题记录只给最近约 11 条，翻页需要额外点击。
- **`sumDone` 不可信**：题库页把"资料分析/综合分析"这类父节点和下面的题型子节点都列了 `已做 X/Y`，直接求和会重复。要总数请用 `report.totalQuestions`。
- **评估报告**：`rank` 在样本少时是"0名"；`hasWeekly` 为 true 时周报通常还是上周区间，别当成本周数据。

## 只读原则

- 不调用任何交卷、提交答案、修改设置、购买接口
- 不写 cookie、不改浏览器 profile（用的是临时 profile 副本）
- 需要"继续做题"时，把链接给人，由本人操作

## 已知限制

- 华图在线**没有公开的会员权益页**（`/vip`、`/member` 均 404），无法用接口判断 VIP 具体解锁了哪些功能；只能从页面是否出现"开通会员"提示来推断
- 单次抓取需要约 30–40 秒（每个页面等 4 秒渲染）
- 账号数据变化后需重跑；无增量机制

## 每日日报（huatu_daily.py）

```bash
python3 scripts/huatu_daily.py            # 抓取 → 存快照 → 出 Markdown 日报
python3 scripts/huatu_daily.py --json     # 机器可读指标
python3 scripts/huatu_daily.py --no-fetch --date 2026-10-30   # 用已有快照重算
```

- 快照库：`~/.workbuddy/data/huatu_daily.db`，表 `snapshots`，一天一行（主键 `date`，同日重跑覆盖）
- 当日增量 = 累计题量/正确数/时长的差值；错题变化 = `errors_total` 差值
- 建议规则会**引用讲义**：从 `~/da-code/shengkao-roadmap/notes.js` 读目录，按关键词匹配讲次（如「四步解题法」「红格纸」「点与线」），输出「看第 N 讲『标题』（时长）：为什么」
- 首日没有前一天时，用累计值判断，文案标注「（累计）」
- 阈值：正确率 <70% 提醒清错题；速度 >80 秒/题（目标 50 的 1.6 倍）提醒限时练；未交卷 ≥2 次提醒完成率

### 错题清理统计（区分"清掉"和"新增"）

- 快照存 `errors_json`（错题本按模块的分布），与上次快照做**模块级 diff**：
  `清掉 = Σ max(0, 昨日−今日)`，`新增 = Σ max(0, 今日−昨日)`。
  净变化看不出"边清边错"的情况（清 5 新增 5 会显示净 +0），必须分开显示。
- 另外从答题记录的类型里识别 `错题重练`，统计"今天专门重做错题 N 份 / M 道"。
- 建议规则：清掉 ≥5 道 → 置顶表扬；新增 > 清掉 → 警告"错题本只会越来越厚"；
  错题本 ≥20 道且当日重做为 0 → 提醒去做错题重练。

### 两个数据语义坑

- **模块增量常为 0 是正常的**：题库页的「已做 X/Y」只统计章节练习，**智能刷题不计入**。
  所以看模块分布要用错题本，不要用 progress 的差值。
- **`--no-fetch` 只重算不写库**：早期版本会回写并覆盖 `errors_json`，已修；调试时不要绕过。

## 逐题明细（huatu_detail.js）

```bash
scripts/run.sh detail [份数]      # 默认 6 份，输出 JSON 到 stdout
```

每份已交卷练习会打开 `/tiku/analysis/<paperId>`，切到「展开全部解析」，抽出每题：

| 字段 | 含义 |
|---|---|
| `topicModule` / `topicKind` / `topicDetail` | 考点三级标签，如「资料分析 / 比重 / 现期比重」 |
| `answer` / `mine` / `ok` | 正确答案、我的选择、对错 |
| `seconds` | 该题答题用时（秒）——判断"卡题"的核心指标 |
| `siteAccuracy` / `easyWrong` | 全站正确率、易错项 |
| `source` | 真题来源（年份/地区/卷别） |

**已知限制**：解析页是分段渲染的，一份 10 题的练习通常只渲染前 5 题，滚动也加载不出剩余部分。
所以覆盖率一般在 50% 左右，脚本会在日报里如实标注「取到 X/Y 题明细」，**不要把它当全量统计**。

**坑**：
- `body.innerText` 切题要用「题号+（题型）」锚点，按容器取会被嵌套包住只拿到第一题
- 模板字符串里的正则会被吞反斜杠，必须用 `String.raw`
- 「展开全部解析」的匹配要宽松（`/展开全部解析/` 且文本长度 ≤8），带 `^$` 锚定会点不到
- `答题时间` 是页面停留时间，中途离开页面会出现 500–700 秒的异常值，读数据时要当成"走开了"而非"思考了"

## 批量题型体检（huatu_batch.py）

```bash
python3 scripts/huatu_batch.py                # 抓最近 10 份，按题型聚合
python3 scripts/huatu_batch.py --papers 20
python3 scripts/huatu_batch.py --from-db      # 用库里已有明细重算（调试）
python3 scripts/huatu_batch.py --json
```

输出三段：
1. **题型体检表**：做题数、错题数、错误率、耗时中位、全站正确率对照，并打标签（重点补／偏慢／快而错／稳）
2. **反复错的题型** → 附方法卡（必记公式与判方向口诀）
3. **做得慢的题型** → 只给提速要点（同一题型不重复贴公式）

方法库在 `references/methods.json`：按 `match` 关键词命中题型，含 `must`（必须记住的公式/口诀）与 `speed`（提速做法）。
新增题型时只改这个 JSON，无需动脚本。

**统计口径**：
- 耗时中位数已剔除 >600 秒的异常值（页面停留 ≠ 思考时间）
- 少于 3 题的题型不下结论（`MIN_SAMPLE`）
- 「快而错」= 中位耗时 ≤20 秒且错误率 ≥30%，通常意味着秒选靠猜，不是会做但慢
- 样本量受「已交卷练习数」限制：未交卷的练习不生成解析页，抓不到
