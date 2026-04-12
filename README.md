# CheckCheck 标牌图号识别与喷码联动工具

CheckCheck 用于离线识别标牌中的图号和架次号，并与喷码软件联动，完成字符文件匹配、载入、插入架次号、传输信息等流程。

当前项目包含两部分能力：

- 主应用：相机预览、OCR 识别、字符文件检索、喷码软件联动

- 字符文件生成器：将“汉字前缀 + 图号”生成为喷码字符文件。

## 主应用功能

- 相机实时预览与单次识别

- 基于 PaddleOCR 的图号 / 架次号识别

- 基于字符文件索引的精确 / 模糊匹配，并显示匹配分数

- 当分数不足以直接放行时，弹出候选列表，由人工确认图号

- 识别成功后，可自动唤起已打开的喷码软件窗口，并载入匹配到的字符文件

- 精确插入模式默认开启：自动滚动到字符文件尾部附近，在目标位置打点并插入架次号

- 插入后可自动点击“传输信息”两次；也支持“手动传输信息”模式，只把鼠标移到传输按钮上

- 支持“仅喷图号模式”：跳过架次号插入，但仍完成字符文件载入、滚动定位和传输准备

- 支持“固定架次号模式”：界面可输入固定架次号，若与识别结果冲突，会弹窗要求人工选择

- 未识别到架次号时，可选择“重新识别”或“只打图号”

- 传输成功后语音播报“末三位 + 已传输”

- 历史记录、截图留存、字符文件索引重建


## 典型使用流程

1. 启动 `start_app.bat`。
2. 在“设置”里配置字符文件根目录，并重建索引。
3. 保持喷码软件已打开，或在设置中配置 `vendor_exe` / `vendor_title_re`。
4. 点击“开始识别”。
5. 系统识别图号并匹配字符文件。
6. 若匹配需要人工确认，弹出候选列表。
7. 若有有效架次号，则自动插入架次号；否则按当前模式或弹窗选择继续。
8. 完成传输，并语音播报结果。

## 启动方式

### 主应用

```text
start_app.bat
```

说明：

- 启动脚本会自动申请管理员权限。
- 会设置本地 OCR 模型目录和精确插入补偿参数。

### 演示脚本

```text
start_demo.bat
```

或：

```powershell
env\python.exe tools\demo_vendor_automation.py --help
```

当前演示脚本默认使用：

- `--viewport-cols 124`
- `--precise-insert`
- `--precise-comp 10`

### 字符文件生成器

```text
start_charfile_gen.bat
```

或：

```powershell
env\python.exe tools\charfile_gen\gui.py
```

## 运行时配置

配置文件：`data/config.json`

主要配置项：

- `char_root`：字符文件根目录。
- `char_match_threshold`：字符文件匹配阈值。
- `vendor_exe`：喷码软件 EXE 路径。
- `vendor_title_re`：喷码软件窗口标题正则。

可选环境变量覆盖：

- `CHECKCHECK_CHAR_ROOT`
- `CHECKCHECK_VENDOR_EXE`
- `CHECKCHECK_VENDOR_TITLE_RE`
- `CHECKCHECK_CHAR_MATCH_THRESHOLD`
- `CHECKCHECK_OCR_MODELS`
- `CHECKCHECK_PRECISE_COMP`

## 目录说明

- `src/`：主应用代码。
- `tools/demo_vendor_automation.py`：喷码软件联动演示脚本。
- `tools/charfile_gen/`：字符文件生成器。
- `data/config.json`：运行时配置。
- `data/char_index.json`：字符文件索引。
- `data/history.db`：历史记录数据库。
- `captures/`：识别截图。
- `assets/`：提示音等静态资源。
- `env/`：项目自带 Python 运行环境，不建议手动改动。
- `ch_PP-OCRv4_*` 和 `_cls_dummy_infer/`：OCR 模型目录，不要改动。

## 本地开发

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src\main.py
```

重建字符文件索引：

```powershell
env\python.exe tools\build_char_index.py --root D:\Vendor\App\Chars
```

## 生产机同步建议

如果只是同步当前应用功能，优先复制这些内容：

- `src/`
- `tools/`
- `assets/`
- `start_app.bat`
- `start_demo.bat`
- `start_charfile_gen.bat`

不要覆盖这些内容：

- `env/`
- `data/history.db`
- OCR 模型目录
