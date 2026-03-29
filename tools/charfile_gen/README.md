# Charfile Generator

将“汉字前缀 + 图号”生成喷码字符文件（16 点阵列格式）。

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

## 默认规则

- 头1：`09X07/16/100/5`
- 头2：`XXXXXX/XXXXXX/XXXXXX/XXXXXX`
- 单行排版
- 间距默认：
  - 汉字与图号：`9` 列
  - 图号字符间：`2` 列
  - 点号 `.` 边界：`2` 列
  - 汉字内部：`1` 列
- 所有字符统一走固定文泉驿点阵字库
- GUI 中可通过“使用加粗字库”切换 `12pt / 12ptb`

## CLI 示例

```powershell
env\python.exe tools\charfile_gen\gen_charfile.py `
  --cn 燃油 `
  --code J11B.6130.B.505.919 `
  --out-dir "打码机管子汇总\_生成"
```

可选参数：

- `--bold`
- `--save-preview`
- `--preview D:\tmp\preview.png`
- `--output D:\tmp\J11B.6130.B.505.919`

## 输出格式

- 输出文件名默认等于 `--code`
- 文件内容：
  - 第 1/2 行：头信息
  - 第 3 行开始：每行一个列点阵，固定 16 位 `0/1`
