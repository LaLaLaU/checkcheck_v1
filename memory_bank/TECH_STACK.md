## 技术栈与框架

- 语言：Python 3.8+
- GUI：PyQt5 5.15.x
- 视觉：OpenCV-Python
- OCR：PaddleOCR 2.10.0（PaddlePaddle 3.0.0）
- 数据库：SQLite
- 音频：QSoundEffect
- 多线程：QThread（相机）
- 打包/部署：conda、conda-pack（离线），PyInstaller（可选）

### 结构与模块
- `ui/`：`main_window.py`、`history_window.py`
- `core/`：`ocr_engine.py`、`region_detector.py`（保留 `text_comparator.py` 文件但主流程不再使用）
- `processing/`：`ocr_processor.py`
- `utils/`：`database_manager.py`
- `workers/`：`camera_worker.py`

### 说明
- 已移除文本比对功能与相关依赖（Difflib 仅作为标准库存在，不在主流程中使用）
- Paddle 模型路径改为相对路径，存在自定义模型则优先，否则回退默认模型