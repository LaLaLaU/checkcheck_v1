## CheckCheck 标牌图号识别与联动工具

CheckCheck 基于 PaddleOCR（内置 PP‑OCRv4）识别标牌“图号”（MAIN）与“架次号”（HEAD），并支持与喷码软件联动：自动匹配并打开对应的字符文件。

### 功能概览
- 相机实时预览；单次/实时识别；快捷键（Enter、鼠标中键）。
- 图号自动复制；架次号一键复制；结果图右侧预览（标注框 + 左上角 ASCII 结果）。
- 字符文件匹配：标准化图号后，基于索引精确/模糊匹配；一键“打开字符文件”。
- 设置界面：可视化配置“字符文件路径”“匹配阈值（默认 0.80）”“喷码软件 exe”“窗口标题正则”，并支持“重建字符文件索引”。
- 历史记录：支持多选删除；可选择同时删除本地图片；成功/失败提示音。

### 识别与校验规则
- 仅允许字符集：A‑Z、0‑9、英文点号“.”；自动转大写，移除空格与尾部点号。
- HEAD：`^[A-Z]{1,3}\d{2,4}$`
- MAIN（优先严格）：`^[A-Z][A-Z0-9]{2,4}\.[0-9]{4}\.[A-Z]\.\d{3}\.\d{3}$`；否则采用宽松匹配 `^[A-Z0-9]+(\.[A-Z0-9]+){2,4}$`。

### 快速开始（离线包）
1) 双击 `start_app.bat` 启动。
2) 点击底部“设置”，在“字符文件路径”选择生产机字符文件根目录；点击“重建字符文件索引”。
3) 勾选“实时识别”或点击“开始识别”。识别出图号后会显示“字符文件: … (score=…)”，点击“打开字符文件”在喷码软件中加载（需先运行喷码软件或在设置中指定 exe）。

### 自动化演示（可选）
- 双击 `start_demo.bat` 或执行：
  - `env\python.exe tools\demo_vendor_automation.py --exe "D:\\Vendor\\App\\VendorApp.exe"`
- 常用参数：`--title-re` 窗口标题正则；`--charfile` 指定字符文件；`--sortie/--serial/--height/--timeout` 见脚本 `--help`。

### 目录与数据
- 识别历史：`data/history.db`；标注截图：`captures/`。
- 字符文件索引：`data/char_index.json`；应用设置：`data/config.json`（可复制到生产机复用）。
- 模型目录：`ch_PP-OCRv4_*`、`_cls_dummy_infer/`（勿修改）；运行时：`env/`（勿改动）。

### 本地开发
- Python 3.8+：`python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && python src\main.py`
- 手动构建索引：`env\python.exe tools\build_char_index.py --root D:\\Vendor\\App\\Chars`

### 许可证
待定

