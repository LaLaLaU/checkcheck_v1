# Charfile Generator

文本转字符文件（16 点阵列）工具。

## GUI（推荐）

双击启动：

```text
start_charfile_gen.bat
```

或命令行启动：

```powershell
env\python.exe tools\charfile_gen\gui.py
```

## 默认规则

- 头1：`09X07/16/100/5`
- 头2：`XXXXXX/XXXXXX/XXXXXX/XXXXXX`
- 单行排版
- 间距：
  - 汉字与图号之间：`9` 列
  - 图号普通字符之间：`2` 列
  - 点号 `.` 与相邻字符之间：`3` 列

## CLI（可选）

```powershell
env\python.exe tools\charfile_gen\gen_charfile.py `
  --cn 燃油 `
  --code J11B.6130.B.505.919 `
  --out-dir "打码机管子汇总\_生成"
```

可选参数：

- `--font C:\Windows\Fonts\msyh.ttc`
- `--preview D:\tmp\preview.png`
- `--output D:\tmp\J11B.6130.B.505.919`

## 输出内容

- 文件名默认等于图号（`--code`）。
- 文件格式：
  - 第 1/2 行为头信息
  - 后续每行一个列点阵，固定 16 位 `0/1`

