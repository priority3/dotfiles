---
name: trip-planner
description: "旅游攻略规划：把同程旅行的实时报价（机票/火车/汽车/酒店/景区/度假）与 anysearch 的城市调研缝合成一份可执行攻略。产出三样东西——2-3 条候选方案供比选、选定后的按天地图路线可视化（高德，Day1/Day2 不同色连线 + 按天筛选）、以及实时报价与经验估算分列的费用明细（人均/总价）。支持三种模式：跨城出行（含往返大交通与住宿）、周边游（目的地待推荐，自动挖出基地城市周边有哪些去处并按车程/主题/天数比选）、本地周末游。触发词：旅游攻略/行程规划/旅行计划/去哪玩/几日游/自由行/周边游/近郊/短途/自驾游/出差顺便玩/路线规划/带我玩/周末去哪/行程地图/旅游预算/花多少钱/机票酒店门票/XX到XX怎么玩/XX周边/XX附近玩/trip plan/itinerary。用户说「帮我规划去成都玩三天」「国庆想去重庆」「成都周边周末游」「杭州附近有什么好玩的」「下周末广州去哪」时都应触发。"
---

# 旅游攻略规划 Skill

把两个已装好的能力缝起来，补上它们各自缺的部分：

| 上游 | 提供 | ��� |
| --- | --- | --- |
| 同程程心 `tc-chengxin` | 七类资源的**实时报价 + 预订入口** | 无地图、无行程编排、无总预算 |
| `weekend-city-trip` | anysearch 调研 + 地图 + 报告模板 | 只覆盖本地、无费用、地图只有散点 |

本 skill 的增量是三样：**路线方案比选**、**按天地图路线**、**费用分列明细**。

> 设计原则：不改上游任何文件。上游由 skillhub 安装，升级会覆盖本地改动。
> 本 skill 按绝对路径复用它们的脚本，只 fork 了地图模板（因为要加连线）。

---

## Phase 0 · 参数与自检

### 0.1 依赖自检（每次开工先跑）

```bash
SKILL_DIR=~/.claude/skills/trip-planner        # 或 WorkBuddy 下的对应路径
bash "$SKILL_DIR/scripts/paths.sh" --check
```

阻断性缺失（node / python3 / 同程 CLI / token）必须先解决。
缺高德 key 只影响地图那一步，其余流程照常。

后续命令依赖 `paths.sh` 导出的变量，**每个新 shell 会话先 source 一次**：

```bash
. "$SKILL_DIR/scripts/paths.sh" ""    # 末尾空串必须有，否则位置参数会被误当子命令
TP="$SKILL_DIR/scripts"               # 本 skill 的脚本
# $WCT 由 paths.sh 给出，指向 weekend-city-trip（anysearch / known_coords 在里面）
```

### 0.2 判定模式

**三种模式，先判定再收集参数** —— 它们缺的东西不一样。

| 模式 | 用户怎么说 | 目的地 | 大交通 | 住宿 |
| --- | --- | --- | --- | --- |
| **跨城** | 「上海到成都」「从北京去重庆玩三天」 | 已知 | 机票/高铁，往返 | 需要 |
| **周边游** | 「成都**周边**周末游」「杭州**附近**两日游」「北京**近郊**」 | **待推荐** | 短途城际/大巴/自驾 | 可选 |
| **本地** | 「成都周末去哪」「广州有什么好玩的」 | 市内 | 无 | 无 |

判定顺序：

1. 出现 **周边 / 附近 / 近郊 / 短途 / 自驾游 / 郊区** → **周边游**
   （此时那个城市名是**出发基地**，不是目的地）
2. 出现 **A 到 B / 从 A 去 B / A 出发** 两个地名 → **跨城**
3. 只有一个城市名 → 问一次出发地；答「本地/不用/就在本地」→ **本地**，
   给了别的城市 → **跨城**

### 0.3 收集参数

| 参数 | 跨城 | 周边游 | 本地 | 缺失时 |
| --- | :-: | :-: | :-: | --- |
| 目的地 | ✅ | — | ✅ | 周边游不需要，那正是要推荐的 |
| 出发地/基地 | ✅ | ✅ | — | 跨城必问；周边游即用户说的那个城市 |
| 日期 | ✅ | ✅ | ✅ | 「国庆」「下周末」按今天推算具体日期并复述确认 |
| 天数 | ✅ | ✅ | — | 周边游默认按「1天往返」和「2天1晚」各出一个方案 |
| 人数 | — | — | — | 默认 2 人，报告里写明假设 |
| 偏好 | — | — | — | 有则影响候选方案设计 |
| 预算档次 | — | — | — | 默认中等（见 `references/cost_model.md`） |

用 `AskUserQuestion` 一次问完缺失项，不要来回追问。
**周边游不要问「想去哪」** —— 用户就是因为不知道去哪才这么问的。

---

## Phase 1 · 并行取数

同程查询与 anysearch 搜索之间没有依赖，**并行发起**。

### 1.1 同程（实时报价）

```bash
TP="$SKILL_DIR/scripts"

# 【跨城】交通 + 住宿 + 门票
bash "$TP/tc_query.sh" traffic  --departure 上海 --destination 成都 \
     --extra "10月1日出发 2人" --save ./work/traffic
bash "$TP/tc_query.sh" hotel    --destination 成都 \
     --extra "春熙路附近 10月1日入住 2晚 2人" --save ./work/hotel
bash "$TP/tc_query.sh" scenery  --destination 成都 \
     --extra "10月1日 亲子" --save ./work/scenery

# 【周边游】一次 travel-query 就够 —— 同程直接吃「XX周边」这种模糊目的地
bash "$TP/tc_query.sh" travel --departure 成都 --destination "成都周边" \
     --extra "周末 2天1晚 2人 自驾或高铁" --save ./work/around

# 【本地】只查门票
bash "$TP/tc_query.sh" scenery --destination 广州 --extra "本周末" --save ./work/scenery
```

`--save` 会同时落盘 `.raw.txt` / `.md` / `.prices.json` 三个文件：
- `.md` 是同程 markdown 原文，最后原样进报告的「资源与预订」节
- `.prices.json` 是结构化报价，供 Phase 2 算钱

**参数要点**：用户的修饰性需求（日期、人数、星级、位置、亲子、直飞…）
全部塞进 `--extra`，不要丢。

**路由**：用户说「规划行程/几日游/自由行/周边游」时，用一次 `travel-query` 拿到
交通+酒店+景点+行程建议，**不要**拆成多个脚本分别调用。

### 1.1b 周边游：从结果里认出候选目的地

`travel-query --destination "{基地}周边"` 会返回一批散落在各区县的酒店/景点/度假产品。
按区县把它们聚起来，每个区县就是一个候选目的地：

```bash
python3 "$TP/extract_visual_json.py" --input work/around.raw.txt --prices \
  | python3 "$TP/group_by_area.py" --base 成都
```

输出形如：

```
■ 大邑县    （6 条 · 景点1 酒店5 · ¥0-587）
    - 西岭雪山 | 08:30-17:00；半天-1天
    - 西岭雪山老猎人酒栈 | ¥138
■ 都江堰市  （6 条 · 景点1 酒店5 · ¥80-349）
    - 都江堰景区 | ¥80 | 08:00-18:00；半天
```

> 别自己写正则分组：同程各业务的位置字段层级是相反的
> （酒店 `都江堰市 · 幸福路88号`，景点 `成都 · 都江堰市`），
> 按位置取段必错，`group_by_area.py` 已处理这个差异。

拿到候选区县后，**按需**再补短途交通（看用户是否自驾）：

```bash
bash "$TP/tc_query.sh" traffic --departure 成都 --destination 都江堰 \
     --extra "周六上午出发 2人" --save ./work/to_dujiangyan
```

景点表的「开放/游玩」列会给出建议时长（`08:00-18:00；半天`），
**用它决定一天塞得下几个点** —— 两个「半天」的景点就是一天的上限。

判读要点：
- 归到**基地城市市辖区**的条目（如成都的龙泉驿区）不是「周边」，剔除
- 同一片区域的不同叫法要合并（青城山在都江堰市境内，算一个目的地）
- `(未识别)` 里多是「XX自由行」这类无明确目的地的打包产品，一般可忽略

### 1.2 anysearch（玩什么）

复用上游 CLI，路径由 `paths.sh` 提供的 `$WCT` 给出：

```bash
python3 "$WCT/scripts/anysearch_cli.py" batch_search --queries '[
  {"query":"成都 10月 展览 演出 市集 2026","max_results":10},
  {"query":"成都 美食街 推荐 本地人 2026","max_results":10},
  {"query":"成都 city walk 路线 老城区","max_results":10}
]' > ./work/search.json
```

query 模板见 `$WCT/references/query_templates.md`（11 个方向）。
batch_search 一次上限 5 路。没有 `ANYSEARCH_API_KEY` 时走匿名，QPS 很低，
必要时减少查询数量。

---

## Phase 2 · 路线方案比选 ★ 本 skill 的核心

**不要直接给一份行程。** 先给 2-3 条风格不同的候选，让用户挑。

详细规则见 `references/plan_compare.md`。要点：

1. 方案之间必须真的不同（节奏、花费、内容、移动方式至少两个维度有差异）
2. 每条方案跑一次 `cost_table.py` 算出人均价 —— 对比表里的价格不能拍脑袋
3. 用 `AskUserQuestion` 让用户选，推荐项放第一个
4. 最省的那条应比最贵的低 25% 以上，否则没有选择意义

```bash
python3 "$TP/cost_table.py" --example > work/cost_A.json   # 看输入格式
# 按方案 A 填好 quoted[]（来自 .prices.json）与 estimated[]
python3 "$TP/cost_table.py" work/cost_A.json --format json  # 取人均价填进对比表
```

---

## Phase 3 · 落地选定方案

只对选中的那条做后续开销。

### 3.1 抽取地点

读 Phase 1 的搜索结果与同程结果，**你自己判断**哪些是真实地理位置
（这一步不调任何外部 LLM）。写 `work/places.json`：

```json
{"city": "成都", "places": [
  {"id": "5001", "name": "大熊猫繁育研究基地", "type": "5", "note": "¥55，建议 8:00 前到"},
  {"id": "A001", "name": "全季酒店成都春熙路店", "type": "A", "note": "¥389/晚"}
]}
```

分类字母（前 11 类与上游一致，本 skill 加了两类）：

| 字母 | 类别 | 字母 | 类别 | 字母 | 类别 |
| --- | --- | --- | --- | --- | --- |
| C | 演唱会 | H | 喜茶 | D | 地铁站 |
| S | 球赛 | F | 美食街 | T | 优惠门票 |
| M | 集市 | W | City Walk | **A** | **住宿** |
| U | 博物馆 | L | 购物中心 | **X** | **交通枢纽** |
| 5 | 5A景区 | | | | |

判断要点：
- **能上地图的**：景点、商场、餐厅、公园、地铁站、场馆、酒店、机场车站
- **不能上地图的**：食物名（钵钵鸡）、活动名（灯光秀）、票价、车次号、出口编号
- **同名消歧**：开元寺在泉州/潮州/福州都有，按上下文选对
- `$WCT/scripts/known_coords.json` 有预置坐标可直接复用

### 3.2 写路线

`work/routes.json`，`stops` 按当天实际游览顺序排列：

```json
[
  {"day": 1, "name": "抵达与市中心", "stops": ["X001", "A001", "F001"],
   "transport": "地铁1号线 → 步行", "cost": 1804, "note": "傍晚到，先安顿"},
  {"day": 2, "name": "熊猫与古迹", "stops": ["5001", "U001", "F002"],
   "transport": "打车 → 地铁3号线", "cost": 410}
]
```

`cost` 用 `cost_table.py --format routes-cost` 的输出填。
一个地点被多天引用（酒店、换乘站）没问题，归属首次出现的那天。

### 3.3 生成地图

```bash
# 地理编码（需 AMAP_KEY，Web 服务类型）
bash "$TP/geocode.sh" work/places.json 成都

# 注入路线（需 AMAP_JS_KEY + AMAP_SECURITY，Web端JS API 类型）
python3 "$TP/inject_route.py" work/places.geo.json \
        "成都行程地图.html" 成都 "2026/10/1-3" --routes work/routes.json

# 校验
python3 "$TP/validate_route_map.py" "成都行程地图.html" --verbose
```

> `geocode.sh` 是上游 `geocode.py` 的包装：上游只吃**纯数组**，
> 但它自己的文档写的是对象格式，直接按文档写会报
> `string indices must be integers`。包装同时接受两种格式并统一产物路径。

校验退出码：`0` 通过 / `1` 有警告可交付 / `2` 必须修复。

**缺高德 key 时**：跳过这三步，在报告里说明「地图未生成，缺 AMAP_* 配置」，
其余部分照常交付。不要静默跳过。

### 3.4 出费用明细

```bash
python3 "$TP/cost_table.py" work/cost_selected.json --format markdown
```

口径见 `references/cost_model.md`。红线：🟢 实时报价与 🟡 经验估算永不混列。

### 3.5 组装报告

骨架见 `references/report_template.md`（跨城/本地两套）。

**必须遵守的契约**（详见 `references/tc_contract.md`）：

- 同程的 `markdown` 原文完整放进「资源与预订」节，**一字不改**
- `预订` 列及其中的 PC/手机/二维码链接不得删除
- 末尾的客服支持段落保留
- 本 skill 的聚合表（方案比选、费用明细）**另起一节**，
  是在同程原文之上加一层，不是把它改写掉

---

## 宿主差异

| | WorkBuddy | Claude Code |
| --- | --- | --- |
| `tc-chengxin` | 在 PATH 里 | 走绝对路径（`paths.sh` 已处理） |
| 展示 HTML | `present_files` | 输出路径，提示浏览器打开 |
| 默认 shell | — | zsh（脚本已兼容 zsh/bash） |

---

## 目录与产物

```
$SKILL_DIR/
├── scripts/
│   ├── paths.sh                # 依赖解析 + 自检（其余脚本 source 它）
│   ├── tc_query.sh             # 同程七类查询封装
│   ├── extract_visual_json.py  # 解析同程输出 / 抽报价
│   ├── group_by_area.py        # 按区县分组，识别周边游候选目的地
│   ├── geocode.sh              # 上游 geocode.py 的格式适配包装
│   ├── inject_route.py         # 地点+路线 → 地图 HTML
│   ├── validate_route_map.py   # 地图质量校验（含路线检查）
│   └── cost_table.py           # 费用明细（🟢/🟡 分列）
├── templates/route_map.html    # fork 自上游，加了按天连线
└── references/                 # plan_compare / cost_model / report_template / tc_contract
```

工作目录建议用 `./work/`，产物（报告 md + 地图 html）放当前目录。

---

## 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `取不到同程令牌` | WorkBuddy 登录态失效 | 打开 WorkBuddy →「连应用」→ 重连「同程旅行」 |
| `USERKEY_PLAT_NOMATCH` | 高德 Key 类型用错了 | 地理编码要 Web 服务 Key，底图要 JS API Key，两者不通用 |
| 地图底图空白 | 缺 `AMAP_JS_KEY`/`AMAP_SECURITY` | 编辑 `$SKILL_DIR/.env` |
| 地图有底图无标记 | 缺 `AMAP_KEY`，地点没编码 | 同上 |
| 路线断开 | `stops` 里的点没定位 | 看 `validate_route_map.py --verbose` 的缺失清单 |
| anysearch 429 | 匿名 QPS 限制 | 配 `ANYSEARCH_API_KEY`，或减少并行查询 |
| 费用表报价占比很低 | 大部分靠估算 | 在报告里明确提醒用户 |

---

## 一句话

**判模式（跨城 / 周边游 / 本地）→ 并行取数（同程报价 + anysearch 调研）→
给 2-3 个候选让用户挑（跨城比风格，周边游比目的地）→
只对选中的出地图路线与费用明细 → 同程原文原样附在最后。**
