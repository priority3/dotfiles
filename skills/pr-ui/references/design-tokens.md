# 设计令牌

## A. ryugi.innei.dev 画布页实测值

出处：`npx ryugi-artifacts get "https://ryugi.innei.dev/a/f9X6xjti9ibMFzJ3p037m"` → `pages/cursor/roster.html`。
全部为 CSS 原文摘抄，不是估算。

**画布**
```css
background: #f4f4f5 radial-gradient(#d4d4d8 1px, transparent 1px) 0 0 / 16px 16px;
```
点阵 16px 一格、1px 点、比底色深两档。作用不是装饰，是给"可以摊开的桌面"一个触感基准。

**板（board）**
```css
background: #fff;
border-radius: 2px 6px 6px 6px;                       /* 左上角留尖:气泡指向 */
box-shadow: 0 2px 5px rgba(0, 0, 0, .14);             /* 常态 */
box-shadow: 0 0 0 1px #d4d4d8, 0 2px 5px rgba(0, 0, 0, .14);  /* 选中/强调 */
```

**字号**：只有 11px、12px、12.5px、13px 四档；标签 11px / 600。数字 `font-variant-numeric: tabular-nums`。

**顶栏**：44px 高。整页只有一条栏，没有侧边栏、没有标签页、没有二级工具条。

**仅有的彩色**：便签的暖黄。其余 21 个 agent 的品牌色属于"内容"（logo），不属于装饰——
这是全篇最重要的分界线：**装饰用色 = 花，内容用色 = 专业。**

## B. 完整 token 表

亮色为默认，暗色同变量换值（`@media (prefers-color-scheme: dark)`）。

| 变量 | 亮色 | 暗色 | 用途 |
| --- | --- | --- | --- |
| `--pr-bg` | `#ffffff` | `#0b0b0d` | 页面/卡片底 |
| `--pr-text` | `#111114` | `#f2f2f4` | 正文 |
| `--pr-text-2` | `#6b6b72` | `#a0a0a8` | 次级文字、标签 |
| `--pr-muted` | `#a3a3ac` | `#6b6b73` | 元信息、占位符、已勾选 |
| `--pr-line` | `#ececee` | `#232327` | 分隔线、卡片描边 |
| `--pr-line-strong` | `#e0e0e3` | `#2c2c31` | 控件描边（勾选圈、按钮边） |
| `--pr-user-card` | `#f4f4f5` | `#1e1e23` | 用户消息小卡 |
| `--pr-sel` | `#f0f0f2` | `#1c1c20` | 按下态、hover 底 |
| `--pr-accent` | `#a3e635` | `#a3e635` | **唯一强调色**，只表状态 |
| `--pr-accent-ink` | `#1a2e05` | `#16240a` | 强调色上的字/图标 |
| `--pr-danger` | `#d92d20` | `#ff6b63` | 错误 |
| `--pr-glass` | `rgba(255,255,255,.78)` | `rgba(11,11,13,.72)` | 顶栏毛玻璃 |

**曲线**
```css
--pr-spring: cubic-bezier(.34, 1.56, .64, 1);  /* 有轻微过冲:按压、入场 */
--pr-ease:   cubic-bezier(.16, 1, .3, 1);      /* expo-out:位移、抽屉 */
```

**圆角**：卡片 8–10px，输入区 14px，小控件 8px，勾选圈/状态点 `9999px`。
不要出现 26px 以上的胶囊——那是"聊天 App 拟态"，会让界面显得比内容重。

**毛玻璃**：`backdrop-filter: blur(16px) saturate(1.5)`。`saturate` 是关键，
不加会让模糊后的背景发灰发脏。

## C. 用色算法：品牌色配什么字

手工挑 20 组前景/背景必然翻车。让代码挑：

```ts
// WCAG 相对亮度
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map(i => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

const ink    = luminance(brand) > 0.4 ? '#000' : '#fff'          // 字色
const border = luminance(brand) > 0.8 ? 'rgba(0,0,0,.12)' : 'rgba(255,255,255,.24)'  // 描边
```

阈值 0.4 / 0.8 是实测出来的分界：低于 0.4 用黑字会糊，高于 0.8（近白底）用白描边看不见。
放一排黑白混杂的 logo 也不花，靠的就是这个。
