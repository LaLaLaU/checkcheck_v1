# 技术栈与结构（整合版）

- 语言：Python 3.8+
- GUI：PyQt5 5.15.x
- 视觉：OpenCV-Python
- OCR：PaddleOCR 2.10.0（PaddlePaddle 3.0.0）
- 数据库：SQLite（`data/history.db`）
- 多媒体提示：QSoundEffect
- 线程：QThread
- 分发：conda/conda-pack（可选），离线包 `delivery_offline/`

目录与模块：
- `src/ui/`：`main_window.py`（主窗体）、`history_window.py`（历史）
- `src/processing/`：`ocr_processor.py`（PaddleOCR 封装）
- `src/core/`：`region_detector.py`、`ocr_engine.py`、`text_comparator.py`（当前 UI 未直接使用比对）
- `src/utils/`：数据库、相机工具

说明：UI 当前仅做“图号/架次号”识别，不做比对。
