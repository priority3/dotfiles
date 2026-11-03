# 视觉验证：截图，不要凭感觉

改完 UI 必须拍真图。凭想象判断"这样应该更好看"是这套流程里最容易翻车的一步——
尤其是字号、行高、留白这三样，差 1px 的观感差异只有看了才知道。

## 一、最快路径：headless shell 直拍

macOS 上 playwright 装的二进制，实测唯一能跑通的是 `chrome-headless-shell`：

```bash
HS=~/Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell
"$HS" --no-sandbox --disable-gpu --hide-scrollbars \
  --window-size=390,844 --force-device-scale-factor=2 \
  --virtual-time-budget=9000 \
  --screenshot=/tmp/shot.png "http://localhost:5173/"
```

参数含义：

| 参数 | 作用 |
| --- | --- |
| `--window-size=390,844` | iPhone 14 逻辑分辨率，手机端界面一律用这个 |
| `--force-device-scale-factor=2` | 2x 截图，文字边缘细节看得清 |
| `--virtual-time-budget=9000` | 等 9 秒虚拟时间，够 SSE/字体/动画首帧稳定 |
| `--hide-scrollbars` | 避免截图里出现滚动条 |
| `--no-sandbox` | 沙箱初始化在这个环境会失败，必须加 |

**不要用 `Google Chrome for Testing.app`**：会因沙箱初始化失败直接退出，且不报明显错误。

## 二、本地组件预览（没有可跑的路由时）

真实组件要在真实渲染环境里看。临时起一个 vite，把组件 import 进来，拍完删掉：

```bash
mkdir -p .preview/public && cp client/public/*.png .preview/public/
```

```ts
// .preview/vite.config.ts
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  root: import.meta.dirname,
  plugins: [react(), tailwindcss()],
  server: { port: 5199 },
})
```

```css
/* .preview/preview.css —— 关键:告诉 Tailwind 去扫真实源码,否则工具类全失效 */
@import "../client/globals.css";
@source "../client";
```

三个坑：

1. **`.preview` 必须放在仓库内**，放 `/tmp` 解析不到 `node_modules`（React 会 import 失败）。
2. **Tailwind v4 必须写 `@source`**，否则组件里的 `text-[13.5px]` 这类任意值全都不生成，截出来是一堆裸 HTML。
3. 静态资源要拷到 `.preview/public`，否则 logo 是裂图。

拍完 `rm -rf .preview`。

## 三、看完图之后逐项对一遍

- [ ] 屏幕上数得出几处彩色？超过 2 处（1 状态 + 1 品牌）就是多了
- [ ] 面积最大的色块是内容还是容器？
- [ ] 正文有没有被裁切（尤其是输入框上方的最后一行）？
- [ ] 数字是否等宽（改一个数字看整行会不会左右抖）？
- [ ] 有没有横向溢出、右边缘被切半个字？
- [ ] 深色模式单独拍一张（`--force-dark-mode` 或直接改系统偏好）

## 四、别过度验证

定稿前拍 2–3 张就够（手机宽度、深色、异常态）。反复截图微调 0.5px 是浪费时间——
观感差异来自结构，不来自 1px。
