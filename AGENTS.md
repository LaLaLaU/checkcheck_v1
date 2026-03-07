# Repository Guidelines

## 项目结构与模块组织
- `src/`：应用主代码。
  - `ui/`（PyQt 界面与交互）、`core/`（检测/OCR 核心逻辑）、`processing/`（PaddleOCR 管线）、`utils/`（数据库/相机/通用工具）、`workers/`（线程）、`data/`（数据/模型黏合层）。
- `assets/`：静态资源与提示音。
- `tools/`：辅助脚本，如 `tools/demo_vendor_automation.py`。
- 模型目录：`ch_PP-OCRv4_*`、`_cls_dummy_infer/`（请勿修改）。
- 本地数据库：`data/history.db`（勿提交到版本库）。
- 运行时：`env/` 打包的 Windows Python 运行环境（勿改动）。
- 启动入口：`start_app.bat`（应用），`start_demo.bat`（演示）。

## 构建、测试与开发命令
- 使用打包环境运行（Windows）：双击 `start_app.bat`。
- 本地开发（推荐）：
  - `python -m venv .venv && .venv\Scripts\activate`
  - `pip install -r requirements.txt`
  - 启动：`python src\main.py`
- 演示脚本：`start_demo.bat`（调用 `tools/demo_vendor_automation.py`）。
- 模型路径：`CHECKCHECK_OCR_MODELS=%CD%`（`start_app.bat` 已设置）。

## 配置与索引（重要）
- 运行时配置：`data/config.json`（UI“设置”自动写入），支持：
  - `char_root`（字符文件根目录）
  - `char_match_threshold`（匹配阈值，默认 0.8）
  - `vendor_exe`、`vendor_title_re`（喷码软件连接）
- 字符文件索引：`tools/build_char_index.py` 扫描 `char_root` 并生成 `data/char_index.json`；UI 中可一键重建。
- 环境变量可覆盖同名配置（可选）：`CHECKCHECK_CHAR_ROOT`、`CHECKCHECK_VENDOR_EXE`、`CHECKCHECK_VENDOR_TITLE_RE`、`CHECKCHECK_CHAR_MATCH_THRESHOLD`。

## 代码风格与命名
- Python 3.8+，缩进 4 空格，UTF-8。
- 命名：模块/函数用 `snake_case`，类用 `PascalCase`，常量用 `UPPER_SNAKE`。
- 分层：UI 置于 `src/ui`；领域与算法置于 `src/core`、`src/processing`；通用放 `src/utils`。
- 使用 docstring 与 `logging` 记录，保持与 `src/main.py` 一致的格式。
- 未强制格式化，若需要可用 `black`、`ruff`/`flake8`。

## 测试规范
- 当前无正式测试。建议新增 `tests/` 并使用 `pytest`。
- 测试命名：`test_*.py`；尽量测试 `core/`、`processing/`、`utils/` 的纯逻辑，避开 UI。
- 运行：`pytest -q`。优先覆盖解析、OCR 后处理、数据库工具函数。

## 提交与 Pull Request
- 建议遵循 Conventional Commits：如 `feat:`、`fix:`、`docs:`。
- PR 需包含：变更说明、复现/验证步骤；如涉及 UI，请附截图；说明对模型/配置的影响。
- 不要提交/修改：`env/`、`data/history.db`、模型目录（`ch_PP-OCRv4_*`、`_cls_dummy_infer/`）。
- 若 `data/config.json` 含机器路径/私有信息，请勿提交（可提供示例）。

## 安全与配置提示
- 代码中不要硬编码敏感信息；不要提交 `history.db` 变更。
- 模型目录建议只读；若需自定义，使用 `CHECKCHECK_OCR_MODELS` 覆盖。
- DPI 问题：`start_app.bat` 中已设置 `QT_FONT_DPI`。

## 代理/自动化贡献者说明
- 本指南适用于整个仓库范围。
- 请勿改动 `env/` 与模型资产；优先做小而清晰的改动，并匹配现有日志与结构风格。
