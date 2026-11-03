# 动效

原则：**只做两件——入场轻位移、静止极轻呼吸。** 其余一律不做。

90% 的界面动效问题是同一个：`transition: all .3s ease`。它同时意味着"我没想过动什么"和"我没想过怎么动"。

## 一、两条曲线

```css
--pr-spring: cubic-bezier(.34, 1.56, .64, 1);  /* 有轻微过冲 → 按压、入场、弹出 */
--pr-ease:   cubic-bezier(.16, 1, .3, 1);      /* expo-out,快出慢停 → 位移、抽屉、淡入 */
```

分工要一致：**带"弹"感的用 spring，带"滑"感的用 expo-out**。混用会显得没纪律。

## 二、入场

```css
@keyframes prIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.msg { animation: prIn .5s var(--pr-spring) both; }
```

- 位移 **6–10px**，不要 20px（会像翻页）。
- **不要再叠 `scale(.96)`**。单条看起来不错，一屏 8 条同时缩放弹跳就变吵。
- 列表错峰 40–60ms 足够，超过 80ms 用户会感到"卡"。

## 三、静止呼吸

只给"活着的东西"：在线点、生成中的指示、头像。

```css
@keyframes prBreath { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }
animation: prBreath 4.5s ease-in-out infinite;
```

幅度 **≤ 1.05**。再大就从"呼吸"变成"心跳"，很廉价。
状态点的脉冲可以到 `opacity .4 + scale .7`（`prPulse 1.1s`），因为它的职责是吸引注意；装饰元素不行。

## 四、带物理的位移（squash & stretch）

只在"一个物体真的移动了"时用。实测一套可以直接抄的关键帧（ryugi 里那个跳过格子的小人）：

```css
@keyframes hop {
  0%   { transform: translateY(0)     scale(1, 1); }      /* 站定 */
  8%   { transform: translateY(0)     scale(1.14, .82); } /* 起跳前蹲:横向撑开、纵向压扁 */
  22%  { transform: translateY(-8px)  scale(.94, 1.08); } /* 腾空:拉长 */
  34%  { transform: translateY(0)     scale(1.16, .8); }  /* 落地:再次压扁 */
  42%  { transform: translateY(0)     scale(.98, 1.03); } /* 回弹 */
  100% { transform: translateY(0)     scale(1, 1); }
}
animation: hop 2.4s infinite;
```

要点：**面积守恒**。横向压扁必须配纵向拉长（1.14 / .82 ≈ 互为倒数），否则读起来像"被挤扁的气球"而不是"有重量的物体"。
落地必须比起跳压得更狠（1.16 > 1.14）——这是"重量"的来源。

另外两个可用的小动作：
```css
/* 眨眼:3.2 秒里只有 7% 时间闭眼 */
@keyframes blink { 0%, 93% { transform: scaleY(1); } 97% { transform: scaleY(.1); } 100% { transform: scaleY(1); } }
/* 焦虑/待办:1.5px 的轻微挪动,几乎看不见但能感到"不安" */
@keyframes nudge { 0%, 100% { transform: translate(0, 0); } 50% { transform: translate(1.5px, 1.5px); } }
```

## 五、按压反馈

```css
.tap { transition: transform .25s var(--pr-spring), opacity .18s; }
.tap:active { transform: scale(.9); }
```

0.86–0.92 之间。小于 .86 像"没点到"，大于 .95 感觉不到。**用 `:active` 不用 hover**——手机没有 hover，hover 在触屏上会"粘住"。

## 六、必须有的降级

```css
@media (prefers-reduced-motion: reduce) {
  .pr-ui *, .backdrop, .drawer { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
```

用 `.01ms` 而不是 `none`：`none` 会让依赖 `animationend` 的逻辑永远等不到事件。

## 七、动画里最容易错的三个数

| 参数 | 错 | 对 | 为什么 |
| --- | --- | --- | --- |
| 入场位移 | 20–24px | 6–10px | 20px 读作"翻页",不是"出现" |
| 呼吸幅度 | 1.1 | 1.03–1.05 | 超过 1.05 变成心跳 |
| 列表错峰 | 120ms | 40–60ms | 超过 80ms 感觉在加载 |
