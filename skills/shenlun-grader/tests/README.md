# 答题卡回归测试

```bash
# 需要先起一个带 CDP 的 Chrome（端口 9241）
/tmp/cdp-run.sh tests/answer-sheet-qa.js
```

覆盖：打字（中文/数字合并/空格换格/标点）、移动（←→↑↓ Home，按格不跳行）、
点击定位（含空白格）、删除（退格/Delete）、多行与折行。

测试用线上部署的 `?id=qa-grid` 临时文档，跑完需从 `sheets` 表删掉该行：
`DELETE FROM sheets WHERE id='qa-grid'`
