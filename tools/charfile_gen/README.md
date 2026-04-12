# Charfile Generator

将“汉字前缀 + 图号”生成为喷码字符文件（16 点阵列格式）。

当前生成器固定使用文泉驿点阵字库：

- 常规：`tools/charfile_gen/wqy-bitmapfont/wenquanyi_12pt.pcf`
- 加粗：`tools/charfile_gen/wqy-bitmapfont/wenquanyi_12ptb.pcf`

## GUI（推荐）

启动：

```text
start_charfile_gen.bat
```

或：

```powershell
env\python.exe tools\charfile_gen\gui.py
```

说明：

- 窗口打开时会后台预热两套点阵字库，减少首次生成等待时间。
- GUI 默认显示预览，但默认不额外保存预览图文件。

## GUI 选项

- `使用加粗字库（wenquanyi_12ptb.pcf）`
- `标点居中`
- `仅图号作为输出文件名`
- `生成预览图文件`

## 默认规则

- 头1：`09X07/16/100/5`
- 头2：`XXXXXX/XXXXXX/XXXXXX/XXXXXX`
- 单行排版
- 间距默认：
  - 汉字与图号：`9` 列
  - 图号字符间：`2` 列
  - 点号 `.` 两侧：`2` 列
  - 汉字内部：`1` 列
- 所有字符统一使用固定文泉驿点阵字库。
- 默认输出文件名为“汉字前缀 + 图号”。
- 勾选“仅图号作为输出文件名”后，输出文件名改为仅图号。
- 标点默认按视觉基线下对齐；勾选“标点居中”后改为居中样式。

## CLI 示例

```powershell
env\python.exe tools\charfile_gen\gen_charfile.py `
  --cn 燃油 `
  --code J11B.6130.B.505.919 `
  --out-dir "打码机管子汇总\_生成"
```

可选参数：

- `--bold`
- `--code-only-filename`
- `--save-preview`
- `--preview D:\tmp\preview.png`
- `--output D:\tmp\燃油J11B.6130.B.505.919`

## 输出格式

- 输出文件名默认为“汉字前缀 + 图号”。
- 若未填写汉字前缀，则退化为仅图号。
- 文件内容：
  - 第 1 / 2 行：头信息
  - 第 3 行开始：每行一个列点阵，固定 16 位 `0/1`
