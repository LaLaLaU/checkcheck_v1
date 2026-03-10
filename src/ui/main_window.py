#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CheckCheck 导管喷码自动核对系统 - 主窗口

此模块实现应用程序的主窗口，包括UI布局和基本功能。
"""

import os
import sys
import html
import difflib
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QMessageBox, QDialog,
    QSplitter, QFrame, QGroupBox, QProgressDialog,
    QApplication, QFormLayout, QStyle, QComboBox, QTableWidgetItem, QTableWidget, QCheckBox, QSizePolicy, QShortcut,
    QHeaderView, QAbstractItemView, QLineEdit
)
from PyQt5.QtGui import QPixmap, QImage, QFont, QIcon, QImageReader, QPalette, QColor, QKeySequence
from PyQt5.QtCore import Qt, QSize, QMimeData, pyqtSignal, pyqtSlot, QObject, QThread, QTimer, QUrl, QEvent
from PyQt5.QtMultimedia import QSoundEffect
from src.utils.database_manager import init_db
from src.ui.history_window import HistoryWindow
from src.workers.camera_worker import CameraWorker
from src.utils.camera_utils import detect_available_cameras
from src.core.text_comparator import TextComparator # 导入 TextComparator
import logging
import re # Added for preprocessing
import unicodedata

# Attempt to import the OCR processor
try:
    from src.processing.ocr_processor import PaddleOcrProcessor # Adjust path if needed
except ImportError as e:
    logging.error(f"Could not import PaddleOcrProcessor: {e}. OCR functionality will be disabled.")
    PaddleOcrProcessor = None # Set to None if import fails

logger = logging.getLogger(__name__)

# --- Custom Widget for Drag and Drop --- 

class ImageDropLabel(QLabel):
    """A QLabel subclass that accepts image file drops."""
    fileDropped = pyqtSignal(str) # Signal emitted when a valid image file is dropped

    def __init__(self, parent=None):
        super().__init__(parent)
        # 静态图片识别已移除：禁用拖拽加载。
        self.setAcceptDrops(False)
        self.setAlignment(Qt.AlignCenter)
        # 禁止控件自行拉伸内容，始终按等比例显示
        try:
            self.setScaledContents(False)
        except Exception:
            pass
        self.setText("等待识别结果...")
        self.setFrameShape(QFrame.Box)
        self.setMinimumHeight(400)
        self.setStyleSheet("background-color: #f0f0f0; color: gray;")
        self.setObjectName("image_label") # Keep object name

    def dragEnterEvent(self, event):
        """Handles drag entering the widget."""
        mime_data = event.mimeData()
        if mime_data.hasUrls() and all(url.isLocalFile() for url in mime_data.urls()):
            # Check if any dropped file is a supported image format
            supported_formats = [fmt.data().decode().lower() for fmt in QImageReader.supportedImageFormats()]
            for url in mime_data.urls():
                file_ext = os.path.splitext(url.toLocalFile())[1].lower().lstrip('.')
                if file_ext in supported_formats:
                    event.acceptProposedAction()
                    self.setStyleSheet("background-color: #e0e0e0; border: 2px dashed #aaaaaa; color: black;") # Indicate droppable
                    return
        event.ignore()

    def dragMoveEvent(self, event):
        """Handles drag moving over the widget."""
        mime_data = event.mimeData()
        if mime_data.hasUrls() and all(url.isLocalFile() for url in mime_data.urls()):
             # Check if any dropped file is a supported image format (optional, but good practice)
            supported_formats = [fmt.data().decode().lower() for fmt in QImageReader.supportedImageFormats()]
            for url in mime_data.urls():
                file_ext = os.path.splitext(url.toLocalFile())[1].lower().lstrip('.')
                if file_ext in supported_formats:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        """Reset background when drag leaves."""
        self.setStyleSheet("background-color: #f0f0f0; color: gray;") # Reset style
        event.accept()

    def dropEvent(self, event):
        """Handles the drop event."""
        self.setStyleSheet("background-color: #f0f0f0; color: gray;") # Reset style on drop
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            supported_formats = [fmt.data().decode().lower() for fmt in QImageReader.supportedImageFormats()]
            valid_image_path = None
            for url in mime_data.urls():
                file_path = url.toLocalFile()
                file_ext = os.path.splitext(file_path)[1].lower().lstrip('.')
                if os.path.isfile(file_path) and file_ext in supported_formats:
                    valid_image_path = file_path
                    break # Process the first valid image
            
            if valid_image_path:
                self.fileDropped.emit(valid_image_path) # Emit signal with path
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()


class VendorPushWorker(QObject):
    """后台串行执行喷码软件唤起/载入/填入，避免阻塞主线程 UI。"""
    finished = pyqtSignal(str, str)  # (level: success|warning|error, message)

    @pyqtSlot(str, str, str, str, bool)
    def run_push(self, char_file: str, norm_head: str, exe_path: str, title_re: str, main_only_no_head: bool):
        try:
            from src.utils.vendor_ui_driver import VendorUIDriver, UIDriverConfig
        except Exception as ie:
            self.finished.emit("warning", f"状态: 自动唤起失败（驱动导入）: {ie}")
            return

        try:
            from src.utils.config import get_precise_insert_compensation_cols
            precise_comp = int(get_precise_insert_compensation_cols())
        except Exception:
            precise_comp = 0

        cfg = UIDriverConfig(
            exe_path=(exe_path or None),
            title_re=(title_re or r'.*(VJ-RT1|WH-VJ1000).*'),
            monitor_timeout_s=3.0,
            precise_insert_compensation_cols=precise_comp,
        )
        drv = VendorUIDriver(cfg)

        try:
            drv.ensure_app()
        except RuntimeError as e:
            msg = str(e)
            if "exe_path not set, and no running window found" in msg:
                self.finished.emit("warning", "状态: 已匹配字符文件；未唤起喷码软件（请配置 exe 或先手动启动）")
                return
            self.finished.emit("warning", f"状态: 自动唤起失败: {e}")
            return
        except Exception as e:
            self.finished.emit("warning", f"状态: 自动唤起失败: {e}")
            return

        try:
            drv.open_char_file(char_file)
        except Exception as e:
            self.finished.emit("warning", f"状态: 字符文件打开失败: {e}")
            return

        if main_only_no_head:
            try:
                drv.transmit()
            except Exception as e:
                self.finished.emit("warning", f"状态: 仅喷图号模式传输失败: {e}")
                return
            self.finished.emit("success", "状态: 未识别到架次号，已按“只喷图号”执行并传输")
            return

        if norm_head:
            try:
                drv.fill_sortie(norm_head)
            except Exception as e:
                self.finished.emit("warning", f"状态: 已打开字符文件，但架次号写入失败: {e}")
                return
            try:
                drv.insert_text_at_tail(char_file)
            except Exception as e:
                self.finished.emit("warning", f"状态: 架次号已写入，但插入文字失败: {e}")
                return
            try:
                drv.transmit()
            except Exception as e:
                self.finished.emit("warning", f"状态: 架次号已插入，但传输信息失败: {e}")
                return
            self.finished.emit("success", f"状态: 已写入并插入架次号 {norm_head}，已执行传输信息")
        else:
            self.finished.emit("success", "状态: 已在喷码软件中打开字符文件")


class MainWindow(QMainWindow):
    """
    应用程序主窗口类
    """
    # 自动唤起/填入任务：char_file, normalized_head_code, exe_path, title_re, main_only_no_head
    vendor_push_requested = pyqtSignal(str, str, str, str, bool)
    
    def __init__(self):
        """
        初始化主窗口
        """
        super().__init__()
        
        # 设置窗口属性
        self.setWindowTitle("CheckCheck - 导管喷码自动核对系统")
        self.setMinimumSize(1024, 768)
        # 默认高度放大50%，使相机与结果区初始显示更大
        self.resize(1024, 1152)
        
        # 初始化成员变量
        self.image_path = None
        self.current_image = None # QPixmap from loaded file
        self.cv_image = None      # OpenCV format image (from file or camera)
        self.processing_result = None  # 处理结果
        self.camera_thread = None      # Thread for camera worker
        self.camera_worker = None      # Worker for camera capture
        self.camera_running = False    # Flag for camera state
        self.camera_index = 1 # TODO: Make configurable
        self.ocr_processor = None # OCR 处理器
        self.pause_camera_updates = False
        self.available_cameras = [] # List to store available camera indices
        self.selected_camera_index = 1 # Default/selected camera index
        self.current_mode = "相机识别" # Default mode

        # 最近一次识别到的架次号/图号
        self.detected_head_code = None
        self.detected_main_code = None
        self.last_frame_aspect_ratio = None  # 记录相机帧宽高比
        # 字符文件匹配状态
        self.matched_char_file = None
        self.matched_char_score = 0.0
        # 识别命中后自动唤起喷码软件（同一图号+文件仅触发一次）
        self.auto_open_charfile_on_match = True
        self._last_auto_open_signature = None
        self.vendor_push_thread = None
        self.vendor_push_worker = None
        self.manual_confirmed_main_code = None
        self._last_recog_snapshot = None
        self._last_recog_text_with_positions = None
        self._last_recog_main_box = None
        self._last_recog_main_code = None
        self._last_recog_head_code = None

        # 编译正则：架次号与图号
        self.HEAD_REGEX_STRICT = re.compile(r'^[A-Z]{1,3}\d{2,4}$')
        # 放宽一档：兼容生产中存在的 1~4 字母 + 2~6 数字
        self.HEAD_REGEX = re.compile(r'^[A-Z]{1,4}\d{2,6}$')
        # 图号严格规范：(3|4|5)-4-1-3-3，首段首字符为大写字母
        self.MAIN_STRICT = re.compile(r'^[A-Z][A-Z0-9]{2,4}\.\d{4}\.[A-Z]\.\d{3}\.\d{3}$')
        # 宽松匹配：用于候选评分（黄色提示），不作为成功标准
        self.MAIN_FALLBACK = re.compile(r'^[A-Z0-9]+(\.[A-Z0-9]+){2,4}$')

        # 定义颜色常量
        self.pass_background_color = "#e0ffe0" # Light green for pass
        self.fail_background_color = "#ffcccc" # Light red for fail
        self.default_groupbox_background = "transparent"

        # 初始化数据库
        from src.utils.database_manager import init_db
        try:
            init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}", exc_info=True)
        
        # 设置UI
        self._setup_ui()
        
        # 初始化OCR处理器
        self._init_ocr_processor()
        # 初始化相机（但不启动）
        self._init_camera()
        # 自动启动摄像头
        self.start_camera()

        # 移除比较逻辑

        # 初始化音效
        self._init_sounds()
        # 初始化后台喷码任务线程（识别后异步执行）
        self._init_vendor_push_worker()

    def _setup_ui(self):
        """
        设置UI布局和组件
        """
        # 主窗口和中心控件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建垂直分割器
        splitter = QSplitter(Qt.Vertical) # Revert to Vertical
        main_layout.addWidget(splitter)
        
        # 上方区域 - 图像显示
        image_widget = QWidget()
        image_layout = QVBoxLayout(image_widget)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)
        self.image_label = ImageDropLabel(self) # Use the custom label
        # 不拉伸内容，容器自适应但保持等比显示
        self.image_label.setScaledContents(False)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        image_layout.addWidget(self.image_label)
        splitter.addWidget(image_widget)
        
        # --- Bottom Panel (Controls and Results) - Reverted Structure ---
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        # 左右适当留白 12px，上下保持紧凑
        bottom_layout.setContentsMargins(12, 0, 12, 0)
        bottom_layout.setSpacing(8)

        # 结果显示区：左侧文字结果 + 右侧识别结果图
        self.results_groupbox = QGroupBox("识别结果")
        results_container = QHBoxLayout(self.results_groupbox)
        results_container.setContentsMargins(4, 4, 4, 4)
        results_container.setSpacing(6)

        left_widget = QWidget()
        results_layout = QFormLayout(left_widget) 
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(8)
        results_layout.setLabelAlignment(Qt.AlignRight)

        font = QFont()
        font.setPointSize(12) # Increase font size

        # 复制架次号按钮：提前创建，供结果容器使用
        self.copy_head_button = QPushButton(" 复制架次号")
        self.copy_head_button.setToolTip("复制最近一次识别到的架次号")
        self.copy_head_button.setEnabled(False)
        self.copy_head_button.clicked.connect(self.copy_head_to_clipboard)

        # 先放“架次号”行（上方）
        # 将“喷码文字”替换为“架次号”，并把复制按钮放入同一容器
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        self.print_text_result = QLabel("架次号: 等待识别...")
        self.print_text_result.setFont(font)
        self.print_text_result.setTextInteractionFlags(Qt.TextSelectableByMouse) # Allow text selection
        row_layout.addWidget(self.print_text_result)
        row_layout.addWidget(self.copy_head_button)
        row_layout.addStretch(1)
        results_layout.addRow(row_widget)

        # 固定架次号模式：可输入固定架次号并启用
        fixed_widget = QWidget()
        fixed_layout = QHBoxLayout(fixed_widget)
        fixed_layout.setContentsMargins(0, 0, 0, 0)
        fixed_layout.setSpacing(8)
        self.fixed_head_mode_checkbox = QCheckBox("固定架次号模式")
        self.fixed_head_input = QLineEdit()
        self.fixed_head_input.setPlaceholderText("输入固定架次号（如 SG100）")
        self.fixed_head_input.setMaximumWidth(260)
        fixed_layout.addWidget(self.fixed_head_mode_checkbox)
        fixed_layout.addWidget(self.fixed_head_input)
        fixed_layout.addStretch(1)
        results_layout.addRow(fixed_widget)

        # 再放“图号”行（下方）
        self.label_text_result = QLabel("图号: 等待识别...")
        self.label_text_result.setFont(font)
        self.label_text_result.setTextInteractionFlags(Qt.TextSelectableByMouse) # Allow text selection
        results_layout.addRow(self.label_text_result)

        # 字符文件匹配信息与操作
        self.charfile_label = QLabel("字符文件: <未匹配>")
        self.charfile_label.setFont(font)
        self.charfile_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        results_layout.addRow(self.charfile_label)

        self.open_charfile_button = QPushButton("打开字符文件")
        self.open_charfile_button.setEnabled(False)
        self.open_charfile_button.clicked.connect(self.on_open_charfile)
        results_layout.addRow(self.open_charfile_button)

        # 状态容器：用于显示复制结果，并通过背景色辅助提示
        self.comparison_result = QLabel("状态: 等待识别...")
        self.comparison_result.setFont(font)
        self.comparison_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        results_layout.addRow(self.comparison_result)

        # 左侧加入容器
        results_container.addWidget(left_widget, 1)

        # 右侧识别结果图
        self.result_preview_label = QLabel("实时画面")
        self.result_preview_label.setAlignment(Qt.AlignCenter)
        # 右下角小窗：实时画面（进一步增大占比，减少留白）
        self.result_preview_label.setMinimumSize(360, 230)
        self.result_preview_label.setMaximumSize(900, 560)
        self.result_preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.result_preview_label.setStyleSheet("border: 1px solid #cccccc; background-color: #ffffff;")
        results_container.addWidget(self.result_preview_label, 3)

        # 状态颜色常量
        self.status_success_bg = "#e0ffe0"   # 绿色淡色
        self.status_warning_bg = "#fff4e5"   # 橙色淡色
        self.status_error_bg   = "#ffecec"   # 红色淡色

        # 初始化状态样式
        self._set_status("状态: 等待识别...", self.status_warning_bg)
        
        bottom_layout.addWidget(self.results_groupbox) # Add results groupbox to bottom layout

        # 控制按钮区域 (Horizontal Layout)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # 获取标准图标
        upload_icon = self.style().standardIcon(QStyle.SP_DialogOpenButton)
        recognize_icon = self.style().standardIcon(QStyle.SP_MediaPlay) 
        history_icon = self.style().standardIcon(QStyle.SP_FileDialogListView) # Matching screenshot's likely icon
        settings_icon = self.style().standardIcon(QStyle.SP_FileDialogDetailedView)
        resume_icon = self.style().standardIcon(QStyle.SP_MediaPlay) # Icon for resume button

        # 移除上传图像功能：隐藏按钮且不加入布局
        self.upload_button = QPushButton(upload_icon, " 上传图像")
        self.upload_button.setVisible(False)
        self.upload_button.setEnabled(False)

        self.recognize_button = QPushButton(recognize_icon, " 开始识别") 
        self.recognize_button.setToolTip("对当前显示的图像或摄像头画面进行识别")
        self.recognize_button.clicked.connect(self._recognize_current_frame)
        self.recognize_button.setEnabled(False) # Initially disabled
        button_layout.addWidget(self.recognize_button)

        # 实时识别开关
        self.realtime_checkbox = QCheckBox(" 实时识别")
        self.realtime_checkbox.setToolTip("开启后自动识别相机画面，有新标牌时自动输出结果")
        self.realtime_checkbox.setChecked(False)
        self.realtime_checkbox.toggled.connect(self.on_toggle_realtime)
        button_layout.addWidget(self.realtime_checkbox)

        # 已移到结果容器

        # --- Resume Camera Button (Re-added) ---
        # 移除“恢复相机”按钮（相机始终实时）
        self.resume_camera_button = QPushButton(resume_icon, " 恢复相机")
        self.resume_camera_button.setVisible(False)
        self.resume_camera_button.setEnabled(False)
        # --- End Resume Camera Button ---

        # 移除切换到图片功能：隐藏切换按钮
        self.switch_mode_button = QPushButton(" 切换模式")
        self.switch_mode_button.setVisible(False)
        self.switch_mode_button.setEnabled(False)

        self.history_button = QPushButton(history_icon, " 历史记录") # Match screenshot text
        self.history_button.setToolTip("查看历史识别记录")
        self.history_button.clicked.connect(self._show_history_window)
        button_layout.addWidget(self.history_button)

        # 设置按钮
        self.settings_button = QPushButton(settings_icon, " 设置")
        self.settings_button.setToolTip("配置字符文件路径与匹配阈值")
        self.settings_button.clicked.connect(self.on_open_settings)
        button_layout.addWidget(self.settings_button)
        
        # 添加相机选择下拉框
        self.camera_selection_combo = QComboBox()
        self.camera_selection_combo.setToolTip("选择要使用的摄像头")
        self.camera_selection_combo.setMinimumWidth(100)
        # Connect signal later in _init_camera if multiple cameras detected
        button_layout.addWidget(QLabel("相机选择:"))
        button_layout.addWidget(self.camera_selection_combo)
        button_layout.addSpacing(20) # Add space after combo box
        
        # 将按钮布局添加到下方布局
        bottom_layout.addLayout(button_layout)
        
        # 添加下方控件到分割器
        splitter.addWidget(bottom_widget)
        
        # 设置分割器初始比例 (approximate from screenshot)
        # Adjust these values as needed
        splitter.setHandleWidth(0)
        # 调整为上56% / 下44%：
        # 识别结果大图区相对缩小，底部（含实时小窗）相对放大。
        splitter.setSizes([int(self.height() * 0.56), int(self.height() * 0.44)])

        # 设置结果文本样式
        self.result_style = """
        QLabel {
            border: 1px solid #cccccc;
            border-radius: 4px;
            padding: 8px;
            background-color: #f8f8f8;
            margin: 2px;
            font-size: 12pt;
        }
        """
        
        # 用于控制结果框背景颜色的基础样式
        self.base_groupbox_style = "QGroupBox {{ border: 1px solid gray; border-radius: 5px; margin-top: 0.5em; background-color: {background_color}; }} QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }}"
        
        # 应用样式
        self.label_text_result.setStyleSheet(self.result_style)
        self.print_text_result.setStyleSheet(self.result_style)
        # comparison_result 的背景由 _set_status 动态控制，不用 result_style 的统一背景
        self.comparison_result.setStyleSheet("")
        # 结果区整体不再根据识别结果上色，只保留容器边框与透明背景
        self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=self.default_groupbox_background))
        
        # 应用简单的 QSS 样式 (Keep existing styles)
        self.setStyleSheet("""
            QMainWindow { background-color: #ffffff; }
            QGroupBox { font-size: 12pt; border: 1px solid #cccccc; border-radius: 5px; margin-top: 1.5ex; padding-top: 12px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; left: 10px; }
            QPushButton { padding: 8px 15px; border: 1px solid #cccccc; border-radius: 4px; background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f6f7fa, stop:1 #dadbde); min-width: 80px; font-size: 10pt; }
            QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e6e7ea, stop:1 #ced0d4); }
            QPushButton:pressed { background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #dadbde, stop:1 #f6f7fa); }
            QPushButton:disabled { background-color: #e0e0e0; color: #a0a0a0; }
            QLabel#image_label { background-color: #f0f0f0; border: 1px solid #cccccc; }
        """)
        
        # 静态图片识别已移除：不连接拖拽加载信号。

        # 全局快捷键：Enter 和小键盘 Enter 触发开始识别
        shortcut_return = QShortcut(QKeySequence(Qt.Key_Return), self)
        shortcut_return.setContext(Qt.ApplicationShortcut)
        shortcut_return.activated.connect(self._recognize_current_frame)

        shortcut_enter = QShortcut(QKeySequence(Qt.Key_Enter), self)
        shortcut_enter.setContext(Qt.ApplicationShortcut)
        shortcut_enter.activated.connect(self._recognize_current_frame)

        # 绑定鼠标中键：在主窗口任意位置按下鼠标中键，触发开始识别
        self.installEventFilter(self)

    def _init_ocr_processor(self):
        """Initialize the OCR processor."""
        if PaddleOcrProcessor:
            try:
                self.ocr_processor = PaddleOcrProcessor()
                logger.info("OCR Processor initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize OCR Processor: {e}")
                QMessageBox.critical(self, "初始化错误", f"初始化 OCR 处理器失败: {e}")
        else:
             logger.warning("PaddleOcrProcessor not available. OCR functionality disabled.")
             # Optionally show a warning to the user
             # QMessageBox.warning(self, "警告", "OCR 模块未找到或加载失败，识别功能将不可用。")

    def _init_camera(self):
        """
        Initialize camera settings and detect available cameras.
        优先检查索引1，如果可用则快速启动，并提供扫描其他摄像头的选项。
        """
        logger.info("Initializing camera system (prioritizing index 1)...")
        self.available_cameras = []
        self.camera_selection_combo.clear() # Clear previous items
        scan_option_added = False
        
        # 1. 优先检查索引1
        logger.debug("Checking camera index 1...")
        try:
            cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
            if cap is not None and cap.isOpened():
                # 索引1可用
                logger.info("Camera index 1 is available. Setting as default.")
                self.available_cameras.append(1)
                self.selected_camera_index = 1
                # 只添加索引1和扫描选项到下拉框
                self.camera_selection_combo.blockSignals(True)
                self.camera_selection_combo.addItem(f"相机 1", 1)
                self.camera_selection_combo.addItem("扫描其他摄像头", -99)  # 特殊值用于扫描选项
                self.camera_selection_combo.setCurrentIndex(0)  # 选择相机1
                self.camera_selection_combo.blockSignals(False)
                scan_option_added = True
                cap.release()
                logger.debug("Released camera index 1 after check.")
            else:
                logger.info("Camera index 1 not available or failed to open.")
                if cap is not None:
                    cap.release()
                # 如果索引1不可用，扫描其他摄像头
                self._scan_other_cameras(update_combo=True, initial_scan=True)
        except Exception as e:
            logger.error(f"Error checking camera index 1: {e}", exc_info=True)
            # 出错时扫描其他摄像头
            self._scan_other_cameras(update_combo=True, initial_scan=True)

        # 3. 最终UI设置和摄像头启动（如果可用）
        if self.available_cameras:
            if self.selected_camera_index != -1:
                # 确保下拉框选择正确的摄像头
                if not scan_option_added:  # 只有在执行了_scan_other_cameras时才需要
                    current_index_in_combo = -1
                    for i in range(self.camera_selection_combo.count()):
                        if self.camera_selection_combo.itemData(i) == self.selected_camera_index:
                            current_index_in_combo = i
                            break
                    if current_index_in_combo != -1:
                        self.camera_selection_combo.setCurrentIndex(current_index_in_combo)
                    else:
                        logger.error(f"Selected camera {self.selected_camera_index} not found in combo after scan!")
            
            # 在初始填充和选择后连接信号
            try:  # 先断开连接，避免多次连接
                self.camera_selection_combo.currentIndexChanged.disconnect(self.on_camera_selection_changed)
            except TypeError:
                pass  # 如果未连接则忽略错误
            self.camera_selection_combo.currentIndexChanged.connect(self.on_camera_selection_changed)
            self.camera_selection_combo.setEnabled(True)
            
            # 启用相关按钮
            self.recognize_button.setEnabled(True) 
            self.switch_mode_button.setEnabled(True)
            self.statusBar().showMessage(f'使用相机 {self.selected_camera_index}')
        else:
            # 未检测到摄像头
            logger.warning("No cameras detected.")
            self.camera_selection_combo.addItem("未检测到相机")
            self.camera_selection_combo.setEnabled(False)
            self.recognize_button.setEnabled(False) 
            self.switch_mode_button.setEnabled(False)
            self.statusBar().showMessage('未检测到可用摄像头')
        
        logger.info("Camera system initialized.")

    def _scan_other_cameras(self, update_combo=True, initial_scan=False):
        """扫描其他摄像头（0, 2, 3, 4）并更新可用摄像头列表"""
        indices_to_check = [0, 2, 3, 4]  # 索引1已在_init_camera中检查
        newly_found = []
        
        logger.info(f"Scanning camera indices: {indices_to_check}")
        
        # 使用QProgressDialog提供视觉反馈
        progress = QProgressDialog("正在扫描摄像头...", "取消", 0, len(indices_to_check), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(500)  # 只有当扫描时间较长时才显示
        progress.setValue(0)
        
        for i, index in enumerate(indices_to_check):
            progress.setValue(i)
            if progress.wasCanceled():
                logger.warning("Camera scan cancelled by user.")
                break
            
            # 跳过已经找到的摄像头
            if index in self.available_cameras:
                continue
                
            logger.debug(f"Checking camera index {index}...")
            try:
                cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                if cap is not None and cap.isOpened():
                    logger.info(f"Camera index {index} found.")
                    self.available_cameras.append(index)
                    newly_found.append(index)
                    cap.release()
                    logger.debug(f"Released camera index {index} after check.")
                elif cap is not None:
                    cap.release()
            except Exception as e:
                logger.error(f"Error checking camera index {index}: {e}", exc_info=True)
            QApplication.processEvents()  # 保持UI响应
        
        progress.setValue(len(indices_to_check))
        progress.close()
        
        # 更新可用摄像头列表
        self.available_cameras.sort()
        
        # 如果之前没有选择摄像头，选择第一个可用的
        if initial_scan and self.available_cameras and self.selected_camera_index == -1:
            self.selected_camera_index = self.available_cameras[0]
            logger.info(f"Setting camera index {self.selected_camera_index} as default after scan.")
        
        # 更新下拉框
        if update_combo:
            self.camera_selection_combo.blockSignals(True)  # 阻止触发处理程序
            self.camera_selection_combo.clear()
            
            if self.available_cameras:
                for cam_index in self.available_cameras:
                    self.camera_selection_combo.addItem(f"相机 {cam_index}", cam_index)
                
                # 如果不是初始扫描，添加"扫描其他摄像头"选项
                if not initial_scan:
                    self.camera_selection_combo.addItem("扫描其他摄像头", -99)
                
                # 重新选择当前摄像头
                if self.selected_camera_index != -1:
                    current_index_in_combo = -1
                    for i in range(self.camera_selection_combo.count()):
                        if self.camera_selection_combo.itemData(i) == self.selected_camera_index:
                            current_index_in_combo = i
                            break
                    if current_index_in_combo != -1:
                        self.camera_selection_combo.setCurrentIndex(current_index_in_combo)
                    else:  # 如果选择的摄像头不在列表中，选择第一个
                        if self.available_cameras:
                            self.selected_camera_index = self.available_cameras[0]
                            first_cam_idx = 0  # 第一个项目就是第一个摄像头
                            self.camera_selection_combo.setCurrentIndex(first_cam_idx)
                        else:
                            self.selected_camera_index = -1
                self.camera_selection_combo.setEnabled(True)
            else:
                self.camera_selection_combo.addItem("未检测到相机")
                self.camera_selection_combo.setEnabled(False)
                self.selected_camera_index = -1
            
            self.camera_selection_combo.blockSignals(False)
        
        return newly_found

    def on_camera_selection_changed(self, index):
        """Handle camera selection change from the dropdown."""
        if index < 0 or not self.available_cameras: 
            return 
        
        selected_data = self.camera_selection_combo.itemData(index)
        
        if selected_data == -99:  # 用户选择了"扫描其他摄像头"
            logger.info("User requested scan for other cameras.")
            
            # 保存当前有效选择
            previous_selection = self.selected_camera_index
            
            # 停止当前摄像头
            if self.camera_running:
                self.stop_camera()
            
            # 执行扫描并更新下拉框
            newly_found = self._scan_other_cameras(update_combo=True, initial_scan=False)
            
            # 尝试恢复之前的选择，否则选择第一个可用的
            restored = False
            if previous_selection != -1 and previous_selection in self.available_cameras:
                new_combo_index = -1
                for i in range(self.camera_selection_combo.count()):
                    if self.camera_selection_combo.itemData(i) == previous_selection:
                        new_combo_index = i
                        break
                if new_combo_index != -1:
                    self.camera_selection_combo.setCurrentIndex(new_combo_index)  # 这会触发信号
                    restored = True
            
            if not restored and self.available_cameras:
                first_cam_index = self.available_cameras[0]
                new_combo_index = -1
                for i in range(self.camera_selection_combo.count()):
                    if self.camera_selection_combo.itemData(i) == first_cam_index:
                        new_combo_index = i
                        break
                if new_combo_index != -1:
                    self.camera_selection_combo.setCurrentIndex(new_combo_index)  # 触发信号
            elif not self.available_cameras:
                # 处理扫描未找到摄像头的情况
                logger.warning("Scan completed, but no cameras available.")
                self.selected_camera_index = -1
                self.image_label.setText("扫描后无可用摄像头")
                self.recognize_button.setEnabled(False)
            
            # 注意：启动摄像头由setCurrentIndex触发的信号处理
        
        elif isinstance(selected_data, int) and selected_data >= 0:
            # 用户选择了特定摄像头
            new_camera_index = selected_data
            if new_camera_index != self.selected_camera_index or not self.camera_running:
                logger.info(f"Camera selection changed to index {new_camera_index}. Current state running: {self.camera_running}")
                self.selected_camera_index = new_camera_index # Update the index first
                if self.camera_running:
                    logger.info("Camera is running, stopping it first...")
                    self.stop_camera()  # Stop the current camera
                    # Start the new camera after the old one has fully stopped.
                    # Use a small delay to ensure the stop process completes in the event loop.
                    QTimer.singleShot(100, self.start_camera)
                else:
                    logger.info("Camera is not running, starting the selected camera directly.")
                    # Camera is already stopped (e.g., after scanning or initial state), start directly
                    self.start_camera() # Start the new camera immediately

    def on_upload_image(self):
        """静态图片识别已移除：保留方法仅作提示。"""
        QMessageBox.information(self, "提示", "静态图片识别功能已移除，请使用相机识别。")

    def load_image(self, image_path):
        """静态图片识别已移除：保留接口避免外部调用崩溃。"""
        _ = image_path
        logger.warning("load_image called, but static image recognition has been removed.")

    def _load_image(self, image_path):
        """静态图片识别已移除：保留方法仅作兼容。"""
        _ = image_path
        logger.warning("_load_image called, but static image recognition has been removed.")

    def switch_to_camera_mode(self):
        """切换到相机识别模式"""
        if self.camera_running: return # Already in camera mode
        self.clear_recognition_results()
        # Clear image display and variables
        self.image_label.clear()
        self.image_label.setText("等待识别结果...")
        self.result_preview_label.clear()
        self.result_preview_label.setText("正在启动相机...")
        self.current_image = None
        self.cv_image = None
        self.image_path = None 
        QApplication.processEvents() 
        self.start_camera() # This will update buttons via update_camera_status

    def switch_to_image_mode(self):
        """静态图片识别已移除：保留方法仅作兼容。"""
        QMessageBox.information(self, "提示", "静态图片识别功能已移除，请使用相机识别。")

    def resume_camera(self):
        """恢复相机实时画面"""
        logger.info("Resuming camera updates.")
        self.pause_camera_updates = False
        self.resume_camera_button.setEnabled(False) # Disable itself
        # Re-enable recognition button if camera is running
        if self.camera_running:
            self.recognize_button.setEnabled(True)
            self.recognize_button.setText(" 开始识别")
            
        # Optionally clear results/marked image display?
        # self.clear_recognition_results() # Maybe confusing?
        # update_frame will now take over displaying live feed
        
        # Ensure mode switch button is correct for camera mode
        if self.camera_running:
             self.switch_mode_button.setText(" 切换到图片") # Corrected text
             # Assuming default icon is camera, set to image icon
             try: 
                 icon_path = os.path.join("resources", "icons", "image_mode.png")
                 if os.path.exists(icon_path):
                     self.switch_mode_button.setIcon(QIcon(icon_path))
                 else: # Fallback if icon missing
                     self.switch_mode_button.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
             except Exception as e:
                 logger.warning(f"Could not set image mode icon: {e}")
                 self.switch_mode_button.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
             
             try: self.switch_mode_button.clicked.disconnect()
             except TypeError: pass
        self.switch_mode_button.clicked.connect(self.switch_to_image_mode)

    def clear_recognition_results(self):
        """清空识别结果框"""
        self.label_text_result.setText("图号: 等待识别...")
        self.print_text_result.setText("架次号: 等待识别...")
        self._set_status("状态: 等待识别...", self.status_warning_bg)
        # 结果区整体背景保持透明
        self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=self.default_groupbox_background))
        # 清除处理结果
        self.processing_result = None
        # 清除字符文件匹配
        self.matched_char_file = None
        self.matched_char_score = 0.0
        self.charfile_label.setText("字符文件: <未匹配>")
        self.open_charfile_button.setEnabled(False)

    def _recognize_current_frame(self):
        """点击开始识别：仅支持相机识别。"""
        if not self.ocr_processor:
            QMessageBox.critical(self, "错误", "OCR 处理器未初始化或加载失败。")
            return

        if self.camera_running and self.cv_image is not None:
            # 相机始终实时，直接触发一次识别（不暂停）
            QTimer.singleShot(100, self._perform_camera_recognition)
        else:
            QMessageBox.warning(self, "无相机画面", "请先启动摄像头并确保有实时画面。")

    def on_start_recognition(self):
        """静态图片识别已移除：保留方法仅作兼容。"""
        QMessageBox.information(self, "提示", "静态图片识别功能已移除，请使用相机识别。")

    def _perform_camera_recognition(self):
        """执行相机画面识别，与_recognize_current_frame分离以允许短暂延时获取最新画面"""
        logger.info("Recognizing current camera frame...")
        # Disable button during processing to prevent multiple clicks
        self.recognize_button.setEnabled(False)
        self.recognize_button.setText("识别中...")
        QApplication.processEvents() # Update UI
        
        try:
            if self.cv_image is None:
                raise RuntimeError("当前无可用相机帧")
            # 固定快照：后续 OCR/预览/保存均基于同一帧，避免“前端与保存图不一致”
            frame_snapshot = self.cv_image.copy()
            # Perform OCR on the current frame
            results = self._perform_ocr(frame_snapshot)
            
            if results is None:
                 raise RuntimeError("OCR 处理返回失败 (None)")
            
            # 提取文本和位置信息
            text_with_positions = []
            if results and results[0]:
                for line in results[0]:
                    if len(line) >= 2 and isinstance(line[1], tuple) and len(line[1]) >= 2:
                        box = line[0]  # 文本框坐标
                        text = line[1][0]  # 文本内容
                        confidence = line[1][1]  # 置信度
                        
                        # 计算文本框中心点y坐标，用于判断上下位置
                        center_y = sum(point[1] for point in box) / len(box)
                        
                        text_with_positions.append((box, text, confidence, center_y))
            
            # 如果没有识别到文本
            if not text_with_positions:
                self.label_text_result.setText("图号: <未识别到文本>")
                self.print_text_result.setText("架次号: <未识别到文本>")
                # 未识别到有效文本
                self._set_status("状态: 未识别到文本", self.status_error_bg)
                # 结果区保持透明
                self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=self.default_groupbox_background))
                return
            
            # 右下角小窗显示实时相机画面
            if self.cv_image is not None:
                h2, w2, ch2 = self.cv_image.shape
                bytes_per_line2 = ch2 * w2
                qt_image2 = QImage(self.cv_image.data, w2, h2, bytes_per_line2, QImage.Format_RGB888).rgbSwapped()
                pixmap_frame = QPixmap.fromImage(qt_image2)
                preview_live = pixmap_frame.scaled(self.result_preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.result_preview_label.setPixmap(preview_live)
            self.current_image = None # Ensure static image is cleared

            # 相机永远实时：根据复选框决定是否自动轮询识别，但不暂停画面
            if self.realtime_checkbox.isChecked():
                QTimer.singleShot(800, self._maybe_realtime_recognize)
            
            # 按y坐标排序，区分上下文本
            text_with_positions.sort(key=lambda x: x[3])
            
            # 假设上半部分是标牌文字，下半部分是喷码文字
            # 计算中间分界线
            height = frame_snapshot.shape[0]
            middle_y = height / 2
            
            label_texts = []
            print_texts = []
            
            for item in text_with_positions:
                box, text, confidence, center_y = item
                if center_y < middle_y:
                    label_texts.append(text)
                else:
                    print_texts.append(text)
            
            # 如果某一部分没有识别到文本，可能是图像问题或识别问题
            if not label_texts:
                label_text = "<未识别到图号>"
            else:
                label_text = " ".join(label_texts)
            
            if not print_texts:
                print_text = "<未识别到架次号>"
            else:
                print_text = " ".join(print_texts)
            
            # 直接解析为图号/架次号
            main_code, head_code_raw, main_box = self._extract_codes(text_with_positions)
            head_code, head_decision_tag = self._resolve_head_code_with_fixed_mode(head_code_raw)
            self.detected_main_code = main_code
            self.detected_head_code = head_code

            # 大图显示识别结果；保存图与大图统一：同一快照、同一渲染函数
            self.manual_confirmed_main_code = None
            self._last_recog_snapshot = frame_snapshot.copy()
            self._last_recog_text_with_positions = list(text_with_positions or [])
            self._last_recog_main_box = main_box
            self._last_recog_main_code = main_code
            self._last_recog_head_code = head_code

            image_to_save = self._build_captured_image(
                frame_snapshot,
                text_with_positions,
                main_code,
                head_code,
                main_box,
                manual_main_code=None,
            )
            try:
                h, w, ch = image_to_save.shape
                bytes_per_line = ch * w
                qt_image = QImage(image_to_save.data, w, h, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
                pixmap_marked = QPixmap.fromImage(qt_image)
                pixmap_marked = self._resize_pixmap(pixmap_marked)
                self.image_label.setPixmap(pixmap_marked)
            except Exception:
                pass

            # 更新UI显示与复制（离线包加入违规段高亮）
            try:
                self.label_text_result.setText(self._generate_main_highlight_html(main_code) if main_code else "图号: <未检测到>")
            except Exception:
                self.label_text_result.setText(f"图号: {main_code or '<未检测到>'}")
            if head_decision_tag == "fixed_equal" and head_code:
                self.print_text_result.setText(f"架次号: {head_code}（识别=固定）")
            elif head_decision_tag == "fixed_only" and head_code:
                self.print_text_result.setText(f"架次号: {head_code}（固定）")
            elif head_decision_tag == "fixed_chosen" and head_code:
                rec_show = self._normalize_head_code(head_code_raw) if head_code_raw else "<未检测到>"
                self.print_text_result.setText(f"架次号: {head_code}（固定优先，识别:{rec_show}）")
            elif head_decision_tag == "recognized_chosen" and head_code:
                fixed_show = self._normalize_head_code(self.fixed_head_input.text()) if hasattr(self, "fixed_head_input") else ""
                self.print_text_result.setText(f"架次号: {head_code}（识别优先，固定:{fixed_show or '<无>'}）")
            else:
                self.print_text_result.setText(f"架次号: {head_code or '<未检测到>'}")
            if main_code:
                QApplication.clipboard().setText(main_code)
                if self.MAIN_STRICT.fullmatch(main_code):
                    self._set_status("状态: 已自动复制图号到剪贴板", self.status_success_bg)
                else:
                    self._set_status("状态: 图号位数与规范不一致，已复制", self.status_warning_bg)
                if self.pass_sound.source().isValid():
                    self.pass_sound.play()
            else:
                self._set_status("状态: 未检测到图号，未复制", self.status_error_bg)
            if head_decision_tag == "fixed_invalid":
                self._set_status("状态: 固定架次号格式无效，已按识别值处理", self.status_warning_bg)

            # 图号 → 匹配字符文件（相机路径），并自动写入架次号
            self._try_match_charfile(main_code, head_code)

            # 若发生人工确认，刷新保存图内容，确保“人工确认图号”被落图并持久化
            if self.manual_confirmed_main_code:
                try:
                    image_to_save = self._build_captured_image(
                        frame_snapshot,
                        text_with_positions,
                        main_code,
                        head_code,
                        main_box,
                        manual_main_code=self.manual_confirmed_main_code,
                    )
                except Exception:
                    pass

            self.copy_head_button.setEnabled(bool(head_code))

            # 保存记录到数据库（保存带标注的图像）
            try:
                from datetime import datetime
                capture_dir = self._ensure_capture_dir()
                filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
                save_path = os.path.join(capture_dir, filename)
                cv2.imwrite(save_path, image_to_save)
                from src.utils.database_manager import add_history_record
                main_code_to_save = main_code or ""
                if self.manual_confirmed_main_code:
                    if main_code_to_save:
                        main_code_to_save = f"{main_code_to_save} | 人工确认:{self.manual_confirmed_main_code}"
                    else:
                        main_code_to_save = f"人工确认:{self.manual_confirmed_main_code}"
                add_history_record(save_path, main_code_to_save, head_code or "")
            except Exception as e:
                logger.error(f"Failed to save simplified camera record: {e}", exc_info=True)

        except Exception as e:
             logger.error(f"Error during camera frame recognition: {e}", exc_info=True)
             QMessageBox.critical(self, "识别错误", f"处理摄像头帧时出错: {e}")
             self.label_text_result.setText("图号: 错误")
             self.print_text_result.setText("架次号: 错误")
             self._set_status("状态: 错误", self.status_error_bg)
             self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=self.default_groupbox_background))
        finally:
             # Re-enable button only if camera is still running AND not paused
             if self.camera_running and not self.pause_camera_updates:
                 self.recognize_button.setEnabled(True)
                 self.recognize_button.setText(" 开始识别")
             elif not self.camera_running: # If camera stopped during processing
                  self.recognize_button.setEnabled(False) # Keep disabled if static img not loaded
                  self.recognize_button.setText(" 开始识别")
             # Resume button state is handled when pausing/resuming

    def _maybe_realtime_recognize(self):
        # 若处于实时识别且相机运行，则再触发一次识别（不检查暂停状态）
        if self.realtime_checkbox.isChecked() and self.camera_running:
            self._perform_camera_recognition()

    def on_toggle_realtime(self, checked: bool):
        # 切换实时识别：如果开启且相机运行，立即启动一次识别循环
        if checked:
            # 开启实时识别：开始自动识别（相机本就实时）
            if self.camera_running:
                QTimer.singleShot(200, self._maybe_realtime_recognize)
        else:
            # 关闭实时识别，不做额外动作
            pass

    def _resize_pixmap(self, pixmap):
        """
        调整图像大小以适应标签
        
        Args:
            pixmap (QPixmap): 原始图像
            
        Returns:
            QPixmap: 调整大小后的图像
        """
        # 获取标签可用内容区大小（扣除边框等），防止被布局压缩时误判
        label_size = self.image_label.contentsRect().size()
        if label_size.width() <= 0 or label_size.height() <= 0:
            label_size = self.image_label.size()
        # 不裁剪画面：等比缩放，完整显示，并考虑屏幕缩放(DPI)
        try:
            dpr = float(self.devicePixelRatioF()) if hasattr(self, 'devicePixelRatioF') else 1.0
        except Exception:
            dpr = 1.0
        target_w = max(1, int(label_size.width() * dpr))
        target_h = max(1, int(label_size.height() * dpr))
        scaled = pixmap.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        try:
            scaled.setDevicePixelRatio(dpr)
        except Exception:
            pass
        return scaled

    def _fit_image_container_to_aspect(self, aspect_w_over_h: float):
        """根据帧宽高比，调整图片容器高度使其与画面匹配（不裁剪）。"""
        try:
            parent_widget = self.image_label.parent() or self.image_label
            available_width = max(1, parent_widget.width())
            available_height = max(1, parent_widget.height())
            # 先按宽度算出理想高度
            ideal_height = int(available_width / max(0.0001, aspect_w_over_h))
            # 最终高度受父容器高度上限约束，避免超出导致下方看起来被“裁切”
            target_height = min(ideal_height, available_height)
            # 设一个较小的下限，避免过矮
            target_height = max(240, target_height)
            if self.image_label.height() != target_height:
                self.image_label.setMinimumHeight(target_height)
                self.image_label.setMaximumHeight(target_height)
        except Exception as e:
            logger.debug(f"_fit_image_container_to_aspect failed: {e}")

    def resizeEvent(self, event):
        try:
            if hasattr(self, 'last_frame_aspect_ratio') and self.last_frame_aspect_ratio:
                self._fit_image_container_to_aspect(self.last_frame_aspect_ratio)
        except Exception:
            pass
        return super().resizeEvent(event)

    def _perform_ocr(self, image_data):
        """Performs OCR using the initialized processor.

        Args:
            image_data (np.ndarray): The image data (OpenCV format, BGR).

        Returns:
            list: The OCR results from PaddleOCR, or None if error.
                  Format assumption: [[box, (text, confidence)], ...]
        """
        if not self.ocr_processor:
            logger.error("Attempted to perform OCR, but processor is not initialized.")
            return None
        if image_data is None:
            logger.error("Attempted to perform OCR on None image data.")
            return None

        try:
            logger.info("Calling OCR processor...")
            # 使用OCR处理器进行识别（禁用逐块角度分类）
            results = self.ocr_processor.ocr(image_data, cls=False)

            # 若结果为空或质量差，进行整图 180° 重试
            def _is_result_meaningful(res):
                try:
                    if not res or not res[0]:
                        return False
                    for line in res[0]:
                        if len(line) >= 2 and isinstance(line[1], tuple) and len(line[1]) >= 2:
                            if float(line[1][1]) > 0:
                                return True
                    return False
                except Exception:
                    return False

            def _remap_boxes_from_rot180(res, w: int, h: int):
                """将“对180°旋转图像识别得到的框”映射回原图坐标系。"""
                if not res:
                    return res

                def _map_point(pt):
                    x = float(pt[0])
                    y = float(pt[1])
                    return [w - 1 - x, h - 1 - y]

                def _replace_box(line, new_box):
                    if isinstance(line, tuple):
                        return (new_box, *line[1:])
                    if isinstance(line, list):
                        return [new_box, *line[1:]]
                    return line

                mapped = []
                for page in res:
                    if not isinstance(page, list):
                        mapped.append(page)
                        continue
                    new_page = []
                    for line in page:
                        try:
                            if not isinstance(line, (list, tuple)) or len(line) < 1:
                                new_page.append(line)
                                continue
                            box = line[0]
                            # 多边形点框 [[x,y], ...]
                            if isinstance(box, list) and len(box) == 4 and isinstance(box[0], (list, tuple)) and len(box[0]) == 2:
                                new_box = [_map_point(pt) for pt in box]
                                new_page.append(_replace_box(line, new_box))
                                continue
                            # 矩形框 [x1,y1,x2,y2]
                            if isinstance(box, (list, tuple)) and len(box) == 4:
                                x1, y1, x2, y2 = [float(v) for v in box]
                                p1 = _map_point([x1, y1])
                                p2 = _map_point([x2, y2])
                                nx1 = min(p1[0], p2[0])
                                ny1 = min(p1[1], p2[1])
                                nx2 = max(p1[0], p2[0])
                                ny2 = max(p1[1], p2[1])
                                new_box = [nx1, ny1, nx2, ny2]
                                new_page.append(_replace_box(line, new_box))
                                continue
                            new_page.append(line)
                        except Exception:
                            new_page.append(line)
                    mapped.append(new_page)
                return mapped

            if not _is_result_meaningful(results):
                try:
                    import cv2 as _cv2
                    h, w = image_data.shape[:2]
                    rotated = _cv2.rotate(image_data, _cv2.ROTATE_180)
                    results_rot = self.ocr_processor.ocr(rotated, cls=False)
                    if _is_result_meaningful(results_rot):
                        results = _remap_boxes_from_rot180(results_rot, w, h)
                        logger.info("Used 180° rotated OCR result as it was better.")
                except Exception as _e:
                    logger.warning(f"180° retry failed: {_e}")
            
            # 基本验证结果格式
            if results is None: 
                logger.warning("OCR processor returned None.")
                return None
                
            return results
        except Exception as e:
            logger.error(f"Exception during OCR processing: {e}", exc_info=True)
            return None

    def _draw_text_boxes(self, image, text_boxes):
        """
        在图像上绘制文本框
        
        Args:
            image: OpenCV格式的图像
            text_boxes: 文本框列表，每个元素包含 (box, text, confidence)
        
        Returns:
            带有文本框标记的图像
        """
        if image is None or not text_boxes:
            return image
            
        # 创建图像副本，避免修改原图
        marked_image = image.copy()
        
        # 为不同类型的文本设置不同颜色
        colors = [
            (0, 255, 0),    # 绿色 - 图号
            (0, 0, 255),    # 红色 - 架次号
            (255, 0, 0)     # 蓝色 - 其他文字
        ]
        
        # 计算字体大小，根据图像尺寸调整
        height, width = image.shape[:2]
        font_scale = min(width, height) / 500  # 增大字体大小1倍（从1000改为500）
        font_scale = max(0.5, min(font_scale, 2.0))  # 调整上限从1.5到2.0
        
        # 绘制每个文本框
        for i, (box, text, confidence, _) in enumerate(text_boxes):
            # 确定颜色索引
            color_idx = i % len(colors) if i < 2 else 2
            color = colors[color_idx]
            
            # Initialize coordinates and extraction flag
            coordinates_extracted = False
            x1, y1, x2, y2 = 0, 0, 0, 0 # Default values

            # Check box format and extract coordinates
            if isinstance(box, list) and len(box) == 4 and isinstance(box[0], list) and len(box[0]) == 2:
                try: # Handle potential errors during point processing
                    pts = np.array(box, dtype=np.int32)
                    # Draw the polygon bounding box first
                    cv2.polylines(marked_image, [pts], isClosed=True, color=color, thickness=2)
                    # Extract top-left (x1, y1) for text positioning reference
                    x1, y1 = pts[0] 
                    # x2, y2 = pts[2] # Bottom-right might not be needed for text
                    coordinates_extracted = True
                except Exception as e:
                     self.logger.warning(f"Error processing polygon box points {box}: {e}")
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                try: # Handle potential errors during point processing
                     # Assuming [x1, y1, x2, y2] format
                    x1, y1, x2, y2 = map(int, box)
                     # Draw rectangle bounding box first
                    cv2.rectangle(marked_image, (x1, y1), (x2, y2), color, 2)
                    coordinates_extracted = True
                except Exception as e:
                     self.logger.warning(f"Error processing rectangle box points {box}: {e}")
            else:
                self.logger.warning(f"Unsupported box format received: {box}. Cannot draw text for this box.")
                # coordinates_extracted remains False

            # --- Draw text only if coordinates were successfully extracted --- 
            if coordinates_extracted:
                # Filter text to keep only ASCII characters and remove spaces
                ascii_text = ''.join(char for char in text if ord(char) < 128 and char != ' ').strip()
                
                # Draw text only if there's something left after filtering
                if ascii_text:
                    try: # Add try-except for robustness in text drawing
                        font_face = cv2.FONT_HERSHEY_SIMPLEX
                        font_scale = 0.6
                        text_thickness = 1
                        (text_width, text_height), baseline = cv2.getTextSize(ascii_text, font_face, font_scale, text_thickness)

                        # --- Calculate text placement --- 
                        # Check if there's enough space above the box
                        required_space_above = text_height + baseline + 4
                        place_above = (y1 >= required_space_above)

                        if place_above:
                            # Place label above the box
                            text_bg_y1 = y1 - required_space_above
                            text_y = y1 - baseline - 2
                        else:
                            # Place label inside the box (top-left corner)
                            text_bg_y1 = y1 + 2
                            text_y = y1 + text_height + 2
                            # Ensure text_y is not below the image
                            text_y = min(text_y, height - baseline - 1) 
                            text_bg_y1 = max(0, min(text_bg_y1, height - text_height - baseline - 4 -1)) # Clamp bg y1

                        # Calculate horizontal placement (common for both above/below)
                        text_x = x1 + 2
                        text_bg_x1 = x1
                        text_bg_x2 = x1 + text_width + 4
                        text_bg_y2 = text_bg_y1 + text_height + baseline + 4

                        # --- Clamp coordinates within image boundaries --- 
                        text_bg_x1 = max(0, min(text_bg_x1, width - 1))
                        text_bg_y1 = max(0, min(text_bg_y1, height - 1))
                        text_bg_x2 = max(0, min(text_bg_x2, width - 1))
                        text_bg_y2 = max(0, min(text_bg_y2, height - 1))
                        text_x = max(0, min(text_x, width - text_width - 1)) # Ensure text start is within bounds
                        text_y = max(text_height, min(text_y, height - baseline - 1)) # Ensure text baseline is within bounds
                    
                        # Ensure coordinates are integers for drawing
                        text_bg_x1, text_bg_y1, text_bg_x2, text_bg_y2 = map(int, [text_bg_x1, text_bg_y1, text_bg_x2, text_bg_y2])
                        text_x, text_y = map(int, [text_x, text_y])

                        # --- Draw background and text --- 
                        # Draw background rectangle if coordinates are valid
                        if text_bg_x2 > text_bg_x1 and text_bg_y2 > text_bg_y1:
                            cv2.rectangle(marked_image, (text_bg_x1, text_bg_y1), (text_bg_x2, text_bg_y2), (255, 255, 255), cv2.FILLED)
                            # Draw the ASCII text using standard cv2.putText
                            cv2.putText(marked_image, ascii_text, (text_x, text_y), font_face, font_scale, color, text_thickness, cv2.LINE_AA)
                        else:
                             self.logger.warning(f"Skipping drawing text background/text for '{ascii_text}' due to invalid coordinates after clamping.")

                    except Exception as e:
                        self.logger.error(f"Error drawing text '{ascii_text}' for box {box}: {e}")
            # else: Coordinates were not extracted, skipping text drawing

        return marked_image

    def _set_status(self, text: str, bg_color: str):
        try:
            self.comparison_result.setText(text)
            self.comparison_result.setStyleSheet(
                f"QLabel {{ background-color: {bg_color}; border: 1px solid #cccccc; border-radius: 4px; padding: 8px; }}"
            )
        except Exception as e:
            logger.warning(f"Failed to set status style: {e}")

    def _generate_main_highlight_html(self, code: str) -> str:
        try:
            if not code:
                return "图号: <未检测到>"
            orange = "#d97a00"
            if self.MAIN_STRICT.fullmatch(code):
                return f"图号: {code}"
            parts = (code or "").split('.')
            def wrap(seg: str) -> str:
                return f'<span style="color:{orange}; font-weight:bold;">{seg}</span>'
            def first_bad_index(parts_list):
                if len(parts_list) < 1:
                    return -1
                seg0 = parts_list[0]
                if not (3 <= len(seg0) <= 5 and len(seg0) >= 1 and seg0[0].isalpha() and seg0.upper() == seg0 and seg0.isalnum()):
                    return 0
                if len(parts_list) < 2:
                    return len(parts_list) - 1
                seg1 = parts_list[1]
                if not (len(seg1) == 4 and seg1.isdigit()):
                    return 1
                if len(parts_list) < 3:
                    return len(parts_list) - 1
                seg2 = parts_list[2]
                if not (len(seg2) == 1 and seg2.isalpha() and seg2.upper() == seg2):
                    return 2
                if len(parts_list) < 4:
                    return len(parts_list) - 1
                seg3 = parts_list[3]
                if not (len(seg3) == 3 and seg3.isdigit()):
                    return 3
                if len(parts_list) < 5:
                    return len(parts_list) - 1
                seg4 = parts_list[4]
                if not (len(seg4) == 3 and seg4.isdigit()):
                    return 4
                if len(parts_list) > 5:
                    return 5
                return -1
            bad_idx = first_bad_index(parts)
            if bad_idx == -1:
                return f"图号: {code}"
            highlighted_parts = []
            for i, seg in enumerate(parts):
                highlighted_parts.append(wrap(seg) if i == bad_idx else seg)
            html = '.'.join(highlighted_parts)
            return f"图号: {html}"
        except Exception:
            return f"图号: {code}"

    def _build_captured_image(self, base_frame, text_with_positions, main_code, head_code, main_box, manual_main_code=None):
        """构建用于保存的带标注图像：
        - 叠加所有文本框标注
        - 高亮图号框
        - 左上角绘制图号/架次号与时间信息
        """
        try:
            image_to_save = base_frame.copy()
            # 仅绘制绿色框，不在框边标注文字
            try:
                for item in text_with_positions or []:
                    box = item[0]
                    if isinstance(box, list) and len(box) == 4 and isinstance(box[0], list):
                        pts = np.array(box, dtype=np.int32)
                        cv2.polylines(image_to_save, [pts], isClosed=True, color=(0, 255, 0), thickness=2)
                    elif isinstance(box, (list, tuple)) and len(box) == 4:
                        x1, y1, x2, y2 = map(int, box)
                        cv2.rectangle(image_to_save, (x1, y1), (x2, y2), (0, 255, 0), 2)
            except Exception:
                pass

            # 高亮图号框（绿色）
            if main_box and isinstance(main_box, (list, tuple)):
                try:
                    if isinstance(main_box, list) and len(main_box) == 4 and isinstance(main_box[0], list):
                        pts = np.array(main_box, dtype=np.int32)
                        cv2.polylines(image_to_save, [pts], isClosed=True, color=(0, 255, 0), thickness=3)
                    elif len(main_box) == 4:
                        x1, y1, x2, y2 = map(int, main_box)
                        cv2.rectangle(image_to_save, (x1, y1), (x2, y2), (0, 255, 0), 3)
                except Exception:
                    pass

            # 在左上角绘制结果信息
            try:
                # 使用 ASCII 标签，避免 OpenCV 字体无法渲染中文导致的问号
                overlay_lines = [f"TUHAO: {main_code or '<NONE>'}"]
                if manual_main_code:
                    overlay_lines.append(f"MANUAL: {manual_main_code}")
                overlay_lines.append(f"JIACI: {head_code or '<NONE>'}")
                from datetime import datetime
                overlay_lines.append(f"TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                font = cv2.FONT_HERSHEY_SIMPLEX
                # 字体缩小约 30%，线条更细
                scale = 0.42
                thickness = 1
                margin = 10
                line_gap = 6

                # 计算背景框大小
                text_sizes = [cv2.getTextSize(t, font, scale, thickness)[0] for t in overlay_lines]
                box_width = max(w for w, h in text_sizes) + margin * 2
                box_height = sum(h for w, h in text_sizes) + margin * 2 + line_gap * (len(text_sizes) - 1)

                # 背景与边框
                cv2.rectangle(image_to_save, (5, 5), (5 + box_width, 5 + box_height), (255, 255, 255), cv2.FILLED)
                cv2.rectangle(image_to_save, (5, 5), (5 + box_width, 5 + box_height), (0, 0, 0), 1)

                # 绘制文字
                x = 5 + margin
                y = 5 + margin + text_sizes[0][1]
                for idx, line in enumerate(overlay_lines):
                    cv2.putText(image_to_save, line, (x, y), font, scale, (0, 0, 0), thickness, cv2.LINE_AA)
                    if idx < len(overlay_lines) - 1:
                        y += text_sizes[idx + 1][1] + line_gap
            except Exception:
                pass

            return image_to_save
        except Exception:
            return base_frame

    def _normalize_and_validate(self, s: str) -> str:
        # 仅允许大写/数字/英文点，删除空格；去除尾点
        if s is None:
            return ""
        s = s.strip().replace(' ', '').upper()
        if s.endswith('.'):
            s = s[:-1]
        # 验证字符集合
        for ch in s:
            if not (ch.isupper() or ch.isdigit() or ch == '.'):
                return ""  # 非法行
        return s

    def _normalize_head_code(self, s: str) -> str:
        """将 OCR 文本归一化为架次号候选（容错 O/0、I/1、连字符等）。"""
        if s is None:
            return ""
        t = unicodedata.normalize("NFKC", str(s)).upper().strip()
        if not t:
            return ""
        # 去掉常见分隔符，仅保留字母数字
        t = re.sub(r"[\s\-\_\.\,\:\;\|]+", "", t)
        t = "".join(ch for ch in t if ch.isalnum())
        if len(t) < 3:
            return ""

        # 尝试在行中抽取连续候选段
        m = re.search(r"[A-Z]{1,4}[A-Z0-9]{2,6}", t)
        if m:
            t = m.group(0)

        m2 = re.fullmatch(r"([A-Z]{1,4})([A-Z0-9]{2,6})", t)
        if not m2:
            return ""

        prefix, tail = m2.groups()
        tail = tail.translate(str.maketrans({
            "O": "0", "Q": "0", "D": "0",
            "I": "1", "L": "1",
            "Z": "2",
            "S": "5",
            "G": "6",
            "B": "8",
        }))
        code = f"{prefix}{tail}"
        if self.HEAD_REGEX.fullmatch(code):
            return code

        # 回退规则：短码（<=7）也可作为架次号候选。
        # 例如 S2-F19 -> S2F19，这类在生产中常见，但不满足“字母+纯数字”严格格式。
        short = t[:7]
        if 2 <= len(short) <= 7 and any(ch.isdigit() for ch in short):
            return short
        return ""

    def _prompt_head_source_choice(self, recognized_head: str, fixed_head: str) -> str:
        """固定架次号与识别架次号不一致时，选择使用哪一个。"""
        dlg = QDialog(self)
        dlg.setModal(True)
        dlg.setWindowTitle("架次号不一致")
        dlg.setMinimumWidth(520)

        layout = QVBoxLayout(dlg)
        title = QLabel("识别到的架次号与固定架次号不一致，请选择使用哪一个：", dlg)
        title.setWordWrap(True)
        info = QLabel(f"识别到: {recognized_head}    固定值: {fixed_head}", dlg)
        info.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        use_fixed_btn = QPushButton(f"使用固定架次号（{fixed_head}）", dlg)
        use_rec_btn = QPushButton(f"使用识别架次号（{recognized_head}）", dlg)
        for b in (use_fixed_btn, use_rec_btn):
            b.setMinimumHeight(40)
            b.setAutoDefault(True)
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        result = {"choice": "fixed"}

        def _choose_fixed():
            result["choice"] = "fixed"
            dlg.accept()

        def _choose_rec():
            result["choice"] = "recognized"
            dlg.accept()

        use_fixed_btn.clicked.connect(_choose_fixed)
        use_rec_btn.clicked.connect(_choose_rec)
        dlg.rejected.connect(_choose_fixed)
        use_fixed_btn.setDefault(True)
        use_fixed_btn.setFocus()
        dlg.exec_()
        return result["choice"]

    def _resolve_head_code_with_fixed_mode(self, recognized_head: str):
        """根据固定架次号模式决定最终用于流程的架次号。

        Returns: (effective_head_code, tag)
          tag in {'normal','fixed_equal','fixed_only','fixed_chosen','recognized_chosen','fixed_invalid'}
        """
        rec_norm = self._normalize_head_code(recognized_head) if recognized_head else ""
        mode_on = bool(getattr(self, "fixed_head_mode_checkbox", None) and self.fixed_head_mode_checkbox.isChecked())
        if not mode_on:
            return rec_norm, "normal"

        fixed_raw = (self.fixed_head_input.text() if getattr(self, "fixed_head_input", None) else "") or ""
        fixed_norm = self._normalize_head_code(fixed_raw)
        if not fixed_norm:
            return rec_norm, "fixed_invalid"

        if rec_norm and rec_norm != fixed_norm:
            choice = self._prompt_head_source_choice(rec_norm, fixed_norm)
            if choice == "recognized":
                return rec_norm, "recognized_chosen"
            return fixed_norm, "fixed_chosen"

        if rec_norm == fixed_norm and rec_norm:
            return fixed_norm, "fixed_equal"

        return fixed_norm, "fixed_only"

    def _extract_codes(self, text_with_positions):
        """从OCR行中提取图号与架次号。
        Returns: (main_code, head_code, main_box)
        """
        main_candidates = []  # (score, text, box)
        head_candidates = []  # (score, text)
        mid_y = (self.cv_image.shape[0] / 2.0) if self.cv_image is not None else None
        for item in text_with_positions or []:
            box, text, confidence, _cy = item
            norm = self._normalize_and_validate(text)
            if not norm:
                # 即便该行不满足图号字符集，也尝试按架次号规则提取
                head_norm = self._normalize_head_code(text)
                if head_norm:
                    h_score = float(confidence or 0.0)
                    if self.HEAD_REGEX_STRICT.fullmatch(head_norm):
                        h_score += 0.15
                    if len(head_norm) <= 7:
                        h_score += 0.10
                    head_candidates.append((h_score, head_norm))
                continue

            # 架次号（容错归一化）
            looks_like_main = bool(self.MAIN_FALLBACK.fullmatch(norm))
            if not looks_like_main:
                head_norm = self._normalize_head_code(norm)
                if head_norm:
                    h_score = float(confidence or 0.0)
                    if self.HEAD_REGEX_STRICT.fullmatch(head_norm):
                        h_score += 0.15
                    if len(head_norm) <= 7:
                        h_score += 0.10
                    head_candidates.append((h_score, head_norm))

            # 图号评分
            score = 0.0
            if self.MAIN_STRICT.fullmatch(norm):
                score = 2.0
            elif self.MAIN_FALLBACK.fullmatch(norm):
                score = 1.5
            if score > 0:
                # 融合置信度
                score += 0.5 * float(confidence or 0)
                main_candidates.append((score, norm, box))
        head_candidate = None
        if head_candidates:
            head_candidates.sort(key=lambda x: x[0], reverse=True)
            head_candidate = head_candidates[0][1]
        if main_candidates:
            main_candidates.sort(key=lambda x: x[0], reverse=True)
            best = main_candidates[0]
            return best[1], head_candidate, best[2]
        return None, head_candidate, None

    def copy_head_to_clipboard(self):
        """复制最近一次识别到的架次号到剪贴板。"""
        if self.detected_head_code:
            QApplication.clipboard().setText(self.detected_head_code)
            self.statusBar().showMessage(f"架次号已复制: {self.detected_head_code}", 3000)
        else:
            self.statusBar().showMessage("当前无可复制的架次号", 3000)

    def add_record(self, image_path: str, main_code: str, head_code: str) -> bool:
        """将识别结果保存到数据库（新结构：main_code/head_code）。"""
        try:
            from src.utils.database_manager import add_history_record
            add_history_record(image_path, main_code, head_code)
            logger.info(f"Record saved: {image_path}, {main_code}, {head_code}")
            return True
        except Exception as e:
            logger.error(f"Failed to save record: {e}")
            return False

    def _ensure_capture_dir(self):
        """确保捕获图像的保存目录存在"""
        capture_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'captures')
        os.makedirs(capture_dir, exist_ok=True)
        return capture_dir

    def _show_history_window(self):
        """Opens the history window dialog."""
        # Check if an instance already exists to avoid multiple windows (optional)
        # Or simply create a new modal dialog each time
        history_dialog = HistoryWindow(self) # Pass parent for modality if desired
        history_dialog.exec_() # Show as a modal dialog

    def on_open_settings(self):
        """打开设置对话框并在保存后尝试刷新匹配。"""
        try:
            from src.ui.settings_dialog import SettingsDialog
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开设置对话框：{e}")
            return
        dlg = SettingsDialog(self)
        if dlg.exec_() == dlg.Accepted:
            # 配置变化后，尝试基于最近图号刷新一次匹配
            try:
                from src.utils.charfile_matcher import clear_runtime_cache
                clear_runtime_cache()
            except Exception:
                pass
            try:
                self._last_auto_open_signature = None
                self._try_match_charfile(self.detected_main_code, self.detected_head_code, auto_push=False)
            except Exception:
                pass

    def start_camera(self):
        """启动摄像头捕获线程"""
        if self.camera_running:
            logger.warning("Camera already running.")
            return
        
        # Check if cameras were detected during init
        if not self.available_cameras:
             logger.error("Cannot start camera: No cameras available.")
             QMessageBox.warning(self, "相机错误", "未检测到可用摄像头，无法启动。")
             return

        # Ensure selected index is valid 
        if self.selected_camera_index not in self.available_cameras:
             logger.error(f"Cannot start camera: Selected index {self.selected_camera_index} is not available in {self.available_cameras}.")
             # Reset selection to the first available one if possible
             if self.available_cameras:
                 self.selected_camera_index = self.available_cameras[0]
                 # Find the corresponding text in the combo box to update UI
                 for i in range(self.camera_selection_combo.count()):
                     if self.camera_selection_combo.itemData(i) == self.selected_camera_index:
                         self.camera_selection_combo.setCurrentIndex(i)
                         break
                 logger.warning(f"Resetting selected camera index to {self.selected_camera_index}")
                 self.statusBar().showMessage(f'重置为相机 {self.selected_camera_index}')
             else: # Should have been caught by the first check
                 return 

        logger.info(f"Starting camera with index: {self.selected_camera_index}")
        self.statusBar().showMessage(f'正在启动相机 {self.selected_camera_index}...')
        QApplication.processEvents() # Update UI immediately
        
        # Clear any existing image display
        if self.current_image:
            self.current_image = None
            self.cv_image = None
            self.image_label.clear()
            self.image_label.setText("等待识别结果...")
            self.result_preview_label.clear()
            self.result_preview_label.setText("启动摄像头...") 
        
        self.camera_thread = QThread(self) # Parent to main window
        # Pass the selected camera index to the worker
        self.camera_worker = CameraWorker(camera_index=self.selected_camera_index) 
        self.camera_worker.moveToThread(self.camera_thread)

        # Connect signals
        self.camera_thread.started.connect(self.camera_worker.run)
        self.camera_worker.frame_ready.connect(self.update_frame)
        self.camera_worker.error_occurred.connect(self.handle_camera_error)
        self.camera_worker.camera_opened.connect(self.update_camera_status)
        
        # Ensure cleanup using finished signals
        # Disconnect previous connections first to be safe if restarting
        try: self.camera_worker.finished.disconnect() 
        except TypeError: pass
        try: self.camera_thread.finished.disconnect() 
        except TypeError: pass
        
        self.camera_worker.finished.connect(self.camera_thread.quit) 
        self.camera_worker.finished.connect(self.camera_worker.deleteLater) 
        self.camera_thread.finished.connect(self.camera_thread.deleteLater)

        # Start the thread
        self.camera_thread.start()
        logger.info("Camera thread started.")
        # self.camera_running state will be set by update_camera_status signal

    def stop_camera(self):
        """停止摄像头捕获线程"""
        logger.info("Entering stop_camera...")
        if self.camera_thread and self.camera_worker:
            logger.info("Signaling CameraWorker to stop...")
            self.camera_worker.stop()
            logger.info("Signal sent. Quitting camera_thread...")
            self.camera_thread.quit()
            logger.info("Waiting for camera_thread to finish...")
            # Wait for 5 seconds max, otherwise force termination? 
            # wait() can block indefinitely if the thread doesn't terminate.
            finished = self.camera_thread.wait(5000) # Wait up to 5000ms (5 seconds)
            if finished:
                logger.info("Camera thread finished gracefully.")
            else:
                logger.warning("Camera thread did not finish within 5 seconds. It might be stuck.")
                # Optionally, you could try termination here, but it's risky:
                # logger.warning("Forcing thread termination...")
                # self.camera_thread.terminate() # Use with caution!
                # self.camera_thread.wait() # Wait again after terminate
        else:
            logger.warning("stop_camera called but thread or worker was None.")

        # Explicitly set running state false *after* confirming thread stop (or timeout)
        self.camera_running = False
        logger.info("Camera thread stopped and resources potentially released.") # Adjusted message

        # Clear references to the old thread and worker after stopping
        # Let deleteLater handle the actual deletion by Qt's event loop
        self.camera_thread = None
        self.camera_worker = None
        logger.info("Cleared references to camera_thread and camera_worker.")

        # Reset image label
        self.image_label.clear() # Clear pixmap first
        self.image_label.setText("等待识别结果...")
        self.image_label.setStyleSheet("background-color: #f0f0f0; color: gray;")
        self.result_preview_label.clear()
        self.result_preview_label.setText("实时画面")
        self.cv_image = None 

        # Re-enable camera selection if multiple cameras are available
        if self.available_cameras and len(self.available_cameras) > 1:
             self.camera_selection_combo.setEnabled(True) 

        # Update mode switch button
        self.switch_mode_button.setText(" 切换到相机")
        self.switch_mode_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        try:
            self.switch_mode_button.clicked.disconnect()
        except TypeError: pass 
        self.switch_mode_button.clicked.connect(self.switch_to_camera_mode)
        
        logger.info("stop_camera finished.")

    def update_frame(self, frame: np.ndarray):
        """接收摄像头帧并更新UI"""
        if not self.camera_running:
            return
            
        try:
            self.cv_image = frame.copy() # Save frame
            h, w, ch = frame.shape
            # 恢复之前的容器高度自适应 + _resize_pixmap 统一缩放
            if h > 0:
                self.last_frame_aspect_ratio = w / float(h)
                self._fit_image_container_to_aspect(self.last_frame_aspect_ratio)
            bytes_per_line = ch * w
            qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
            pixmap = QPixmap.fromImage(qt_image)
            preview = pixmap.scaled(self.result_preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.result_preview_label.setPixmap(preview) # Display live frame in small window
            self.current_image = None # Ensure static image is cleared
        except Exception as e:
            logger.error(f"Error in update_frame: {e}", exc_info=True)

    def handle_camera_error(self, error_message: str):
        """处理来自CameraWorker的错误信号"""
        logger.error(f"Camera Error: {error_message}")
        QMessageBox.critical(self, "摄像头错误", error_message)
        self.camera_running = False # Force state update
        # Re-enable camera selection if applicable
        if self.available_cameras and len(self.available_cameras) > 1:
             self.camera_selection_combo.setEnabled(True) 
        # Update UI, maybe switch back to image mode?
        # self.switch_to_image_mode() # Let's not force switch mode on error, just enable selection
        # Update button states if needed
        self.recognize_button.setEnabled(False) # Can't recognize if camera failed
        self.switch_mode_button.setText(" 切换到相机")
        self.switch_mode_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        try: self.switch_mode_button.clicked.disconnect()
        except TypeError: pass
        self.switch_mode_button.clicked.connect(self.switch_to_camera_mode)

    def update_camera_status(self, opened: bool):
        """更新摄像头状态标签和按钮"""
        self.camera_running = opened
        # Always ensure combo box is enabled if multiple cameras exist
        if self.available_cameras and len(self.available_cameras) > 1:
            self.camera_selection_combo.setEnabled(True) 

        if opened:
            logger.info(f"Camera {self.selected_camera_index} successfully opened.")
            self.statusBar().showMessage(f'相机 {self.selected_camera_index} 已连接')
            self.recognize_button.setEnabled(True) # Enable recognition button
            self.switch_mode_button.setText(" 切换到图片")
            self.switch_mode_button.setIcon(QIcon(os.path.join("resources", "icons", "image_mode.png"))) # Update icon maybe?
            try:
                self.switch_mode_button.clicked.disconnect()
            except TypeError: pass
            self.switch_mode_button.clicked.connect(self.switch_to_image_mode)
        else:
            logger.error(f"Failed to open camera {self.selected_camera_index}.")
            self.statusBar().showMessage(f'相机 {self.selected_camera_index} 打开失败')
            # Message box is now handled in handle_camera_error which is usually triggered before this
            # Ensure UI reflects image mode state as camera failed
            self.recognize_button.setEnabled(False) # Can't recognize if camera failed
            self.switch_mode_button.setText(" 切换到相机")
            self.switch_mode_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            try: self.switch_mode_button.clicked.disconnect()
            except TypeError: pass
            self.switch_mode_button.clicked.connect(self.switch_to_camera_mode)

    def _init_vendor_push_worker(self):
        """初始化后台线程：识别后自动唤起/填入改为异步排队执行。"""
        try:
            self.vendor_push_thread = QThread(self)
            self.vendor_push_worker = VendorPushWorker()
            self.vendor_push_worker.moveToThread(self.vendor_push_thread)

            self.vendor_push_requested.connect(self.vendor_push_worker.run_push, Qt.QueuedConnection)
            self.vendor_push_worker.finished.connect(self._on_vendor_push_finished, Qt.QueuedConnection)
            self.vendor_push_thread.start()
        except Exception as e:
            logger.error(f"初始化后台喷码任务线程失败: {e}", exc_info=True)
            self.vendor_push_thread = None
            self.vendor_push_worker = None

    def _shutdown_vendor_push_worker(self):
        """关闭后台线程。"""
        thread = getattr(self, "vendor_push_thread", None)
        if not thread:
            return
        try:
            thread.quit()
            thread.wait(2000)
        except Exception as e:
            logger.warning(f"关闭后台喷码任务线程失败: {e}")
        self.vendor_push_worker = None
        self.vendor_push_thread = None

    def _resolve_vendor_launch_config(self):
        """读取喷码软件连接配置（配置优先，demo bat 推断兜底）。"""
        try:
            from src.utils.config import get_vendor_exe, get_vendor_title_re
            exe_path = get_vendor_exe()
            title_re = get_vendor_title_re()
        except Exception:
            exe_path = None
            title_re = r'.*(VJ-RT1|WH-VJ1000).*'
        if not exe_path:
            exe_path = self._infer_vendor_exe_from_demo_bat()
        return (exe_path or ""), (title_re or r'.*(VJ-RT1|WH-VJ1000).*')

    def _enqueue_vendor_push(self, head_code: str = None, *, main_only_no_head: bool = False):
        """把自动唤起/填入任务放入后台队列，不阻塞当前识别 UI。"""
        if not self.matched_char_file:
            return

        norm_head = self._normalize_head_code(head_code) if head_code else ""
        exe_path, title_re = self._resolve_vendor_launch_config()

        thread = getattr(self, "vendor_push_thread", None)
        worker = getattr(self, "vendor_push_worker", None)
        if not thread or not worker or not thread.isRunning():
            logger.warning("后台喷码线程不可用，降级为同步执行。")
            self._open_matched_charfile(interactive=False, head_code=norm_head, main_only_no_head=main_only_no_head)
            return

        if main_only_no_head:
            self._set_status("状态: 未识别到架次号，后台按“只喷图号”执行中...", self.status_warning_bg)
        else:
            self._set_status("状态: 已匹配字符文件，后台正在唤起并写入...", self.status_warning_bg)
        self.vendor_push_requested.emit(self.matched_char_file, norm_head, exe_path, title_re, bool(main_only_no_head))

    @pyqtSlot(str, str)
    def _on_vendor_push_finished(self, level: str, message: str):
        if level == "success":
            self._set_status(message, self.status_success_bg)
        elif level == "warning":
            self._set_status(message, self.status_warning_bg)
        else:
            self._set_status(message, self.status_error_bg)

    def _candidate_code_for_display(self, full_path: str, target_norm: str) -> str:
        """从候选文件路径推断用于展示/比对的图号文本。"""
        from pathlib import Path
        from src.utils.charfile_matcher import normalize_code

        p = Path(full_path)
        cands = []
        # 业务规则：纯数字后缀属于图号正文，展示时必须保留。
        raws = [p.name]
        if p.suffix and (not p.suffix.lstrip(".").isdigit()):
            raws.append(p.stem)
        for raw in raws:
            norm = normalize_code(raw)
            if norm and norm not in cands:
                cands.append(norm)
        if not cands:
            return ""
        if not target_norm:
            return cands[0]
        return max(cands, key=lambda s: difflib.SequenceMatcher(None, target_norm, s).ratio())

    def _diff_highlight_html(self, target_norm: str, cand_norm: str) -> str:
        """将候选图号中与识别图号差异的字母/数字高亮为红色。"""
        t = target_norm or ""
        c = cand_norm or ""
        if not c:
            return "<span style='color:#8c8c8c;'>&lt;空&gt;</span>"

        out = []
        sm = difflib.SequenceMatcher(None, t, c)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            seg_c = c[j1:j2]
            seg_t = t[i1:i2]

            if tag == "equal":
                out.append(html.escape(seg_c))
                continue

            if tag in ("replace", "insert"):
                for ch in seg_c:
                    esc = html.escape(ch)
                    if ch.isalnum():
                        out.append(f"<span style='color:#cf1322;font-weight:700;'>{esc}</span>")
                    else:
                        out.append(f"<span style='color:#d46b08;font-weight:700;'>{esc}</span>")
                continue

            if tag == "delete":
                # 候选缺失而目标存在，用占位符提示缺失位数。
                miss_cnt = sum(1 for ch in seg_t if ch.isalnum())
                if miss_cnt > 0:
                    out.append("<span style='color:#cf1322;font-weight:700;'>" + ("□" * miss_cnt) + "</span>")

        return "".join(out) if out else "<span style='color:#8c8c8c;'>&lt;空&gt;</span>"

    def _apply_manual_confirmation_preview(self):
        """人工确认候选后，刷新大预览并在图号下追加一行人工确认信息。"""
        try:
            manual = (self.manual_confirmed_main_code or "").strip()
            if not manual:
                return
            if self._last_recog_snapshot is None:
                return

            img = self._build_captured_image(
                self._last_recog_snapshot,
                self._last_recog_text_with_positions,
                self._last_recog_main_code,
                self._last_recog_head_code,
                self._last_recog_main_box,
                manual_main_code=manual,
            )
            try:
                h, w, ch = img.shape
                bytes_per_line = ch * w
                qt_image = QImage(img.data, w, h, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
                pixmap_marked = QPixmap.fromImage(qt_image)
                pixmap_marked = self._resize_pixmap(pixmap_marked)
                self.image_label.setPixmap(pixmap_marked)
            except Exception:
                pass

            try:
                main_html = self._generate_main_highlight_html(self._last_recog_main_code) if self._last_recog_main_code else "图号: <未检测到>"
                self.label_text_result.setText(
                    f"{main_html}<br/><span style='color:#cf1322; font-weight:700;'>人工确认图号: {manual}</span>"
                )
            except Exception:
                self.label_text_result.setText(
                    f"图号: {self._last_recog_main_code or '<未检测到>'}\n人工确认图号: {manual}"
                )
        except Exception as e:
            logger.warning(f"刷新人工确认预览失败: {e}")

    def _prompt_pick_charfile_candidate(self, main_code: str, ranked):
        """当图号匹配非满分时，显示候选表格，支持双击即选。"""
        try:
            if not ranked:
                return None
            from pathlib import Path
            from src.utils.charfile_matcher import normalize_code

            target_norm = normalize_code(main_code)
            dlg = QDialog(self)
            dlg.setModal(True)
            dlg.setWindowTitle("候选字符文件选择")
            dlg.resize(1080, 560)

            root = QVBoxLayout(dlg)
            tip = QLabel(f"图号识别结果“{main_code}”非满分，请选择要加载的字符文件（双击可直接确认）：", dlg)
            tip.setWordWrap(True)
            root.addWidget(tip)

            table = QTableWidget(len(ranked), 4, dlg)
            table.setHorizontalHeaderLabels(["#", "分数", "文件名(差异高亮)", "完整路径"])
            table.setAlternatingRowColors(True)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setWordWrap(False)
            table.verticalHeader().setVisible(False)
            table.setSortingEnabled(False)
            table.setStyleSheet(
                "QTableWidget { font-size: 16px; }"
                "QHeaderView::section { font-size: 15px; font-weight: 700; }"
            )
            table.verticalHeader().setDefaultSectionSize(44)

            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            hdr.setSectionResizeMode(3, QHeaderView.Stretch)

            picked = {"value": None}

            for row, (path, score) in enumerate(ranked):
                p = Path(path)
                score_f = float(score)
                cand_norm = self._candidate_code_for_display(str(p), target_norm)

                table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
                table.setItem(row, 1, QTableWidgetItem(f"{score_f:.2f}"))
                table.setItem(row, 3, QTableWidgetItem(str(p)))

                lbl = QLabel(dlg)
                lbl.setTextFormat(Qt.RichText)
                lbl.setText(self._diff_highlight_html(target_norm, cand_norm))
                lbl.setStyleSheet("font-size: 20px; font-weight: 800;")
                lbl.setToolTip(f"文件名: {p.name}\n识别图号: {target_norm}\n候选图号: {cand_norm}")
                table.setCellWidget(row, 2, lbl)

            root.addWidget(table)

            btn_row = QHBoxLayout()
            btn_row.addStretch(1)
            ok_btn = QPushButton("确定（Enter）", dlg)
            cancel_btn = QPushButton("取消（Esc）", dlg)
            ok_btn.setDefault(True)
            ok_btn.setAutoDefault(True)
            btn_row.addWidget(ok_btn)
            btn_row.addWidget(cancel_btn)
            root.addLayout(btn_row)

            def _accept_selected():
                row = table.currentRow()
                if row < 0 and table.rowCount() > 0:
                    row = 0
                if row < 0:
                    picked["value"] = None
                else:
                    path, score = ranked[row]
                    picked["value"] = (str(path), float(score))
                dlg.accept()

            ok_btn.clicked.connect(_accept_selected)
            cancel_btn.clicked.connect(dlg.reject)
            table.cellDoubleClicked.connect(lambda _r, _c: _accept_selected())

            if table.rowCount() > 0:
                table.selectRow(0)
                table.setCurrentCell(0, 0)
                table.setFocus()

            if dlg.exec_() == QDialog.Accepted:
                return picked["value"]
        except Exception as e:
            logger.warning(f"候选字符文件选择弹窗失败: {e}")
        return None

    def _confirm_candidate_for_main_code(self, main_code: str, *, force: bool = False) -> bool:
        """按需要弹出候选列表并应用人工确认结果。"""
        try:
            if not main_code:
                return False
            if (not force) and self.matched_char_file and float(self.matched_char_score or 0.0) >= 1.0:
                return True

            from src.utils.charfile_matcher import find_top_charfiles, normalize_code
            ranked = find_top_charfiles(main_code, top_k=8)
            picked = self._prompt_pick_charfile_candidate(main_code, ranked) if ranked else None
            if picked is None:
                self._set_status("状态: 已取消候选选择，请重新识别", self.status_warning_bg)
                return False

            selected_path, selected_score = picked
            self.matched_char_file = str(selected_path)
            self.matched_char_score = float(selected_score)
            self.manual_confirmed_main_code = self._candidate_code_for_display(
                str(selected_path), normalize_code(main_code)
            ) or os.path.basename(str(selected_path))
            self._apply_manual_confirmation_preview()

            from pathlib import Path
            self.charfile_label.setText(
                f"字符文件: {Path(selected_path).name} (score={float(selected_score):.2f}) (已人工确认)"
            )
            self.open_charfile_button.setEnabled(True)
            return True
        except Exception as e:
            logger.warning(f"候选人工确认失败: {e}")
            return False

    def _try_match_charfile(self, main_code: str, head_code: str = None, *, auto_push: bool = True):
        """根据图号匹配字符文件，更新 UI 与可用操作。"""
        try:
            self.manual_confirmed_main_code = None
            if not main_code:
                self.matched_char_file = None
                self.matched_char_score = 0.0
                self.charfile_label.setText("字符文件: <未匹配>")
                self.open_charfile_button.setEnabled(False)
                return
            from src.utils.charfile_matcher import find_best_charfile
            path, score = find_best_charfile(main_code)
            if path is not None:
                self.matched_char_file = str(path)
                self.matched_char_score = float(score)
                from pathlib import Path
                self.charfile_label.setText(f"字符文件: {Path(path).name} (score={float(score):.2f})")
                self.open_charfile_button.setEnabled(True)
            else:
                self.matched_char_file = None
                self.matched_char_score = 0.0
                self.charfile_label.setText("字符文件: <未匹配>")
                self.open_charfile_button.setEnabled(False)
            if auto_push:
                self._maybe_auto_open_charfile(main_code, head_code)
        except Exception as e:
            logging.getLogger(__name__).error(f"匹配字符文件出错: {e}", exc_info=True)
            self.charfile_label.setText("字符文件: <匹配出错>")
            self.open_charfile_button.setEnabled(False)

    def _open_matched_charfile(self, *, interactive: bool, head_code: str = None, main_only_no_head: bool = False) -> bool:
        """打开匹配到的字符文件，并在提供架次号时自动写入。interactive=False 时仅记录日志，不弹窗。"""
        try:
            if not self.matched_char_file:
                if interactive:
                    QMessageBox.information(self, "未匹配", "当前没有匹配到字符文件。")
                return False
            try:
                from src.utils.vendor_ui_driver import VendorUIDriver, UIDriverConfig
            except Exception as ie:
                if interactive:
                    QMessageBox.critical(self, "依赖缺失", f"无法导入自动化驱动：{ie}")
                else:
                    logger.error(f"自动唤起失败（驱动导入）: {ie}")
                return False

            # 读取配置
            exe_path, title_re = self._resolve_vendor_launch_config()
            try:
                from src.utils.config import get_precise_insert_compensation_cols
                precise_comp = int(get_precise_insert_compensation_cols())
            except Exception:
                precise_comp = 0

            cfg = UIDriverConfig(
                exe_path=exe_path,
                title_re=title_re,
                monitor_timeout_s=3.0,
                precise_insert_compensation_cols=precise_comp,
            )
            drv = VendorUIDriver(cfg)
            try:
                drv.ensure_app()
            except RuntimeError as e:
                msg = str(e)
                if "exe_path not set, and no running window found" in msg:
                    tip = "未找到运行中的喷码软件，且未配置喷码软件 exe。请先在“设置”中配置 exe，或先手动打开喷码软件。"
                    if interactive:
                        QMessageBox.warning(self, "无法唤起喷码软件", tip)
                    else:
                        logger.warning(tip)
                        self._set_status("状态: 已匹配字符文件；未唤起喷码软件（请配置 exe 或先手动启动）", self.status_warning_bg)
                    return False
                raise
            drv.open_char_file(self.matched_char_file)
            norm_head = self._normalize_head_code(head_code) if head_code else ""
            if main_only_no_head:
                try:
                    drv.transmit()
                except Exception as e:
                    if interactive:
                        QMessageBox.warning(self, "传输失败", f"仅喷图号模式传输失败：{e}")
                    self._set_status("状态: 仅喷图号模式传输失败", self.status_warning_bg)
                    return False
                self._set_status("状态: 未识别到架次号，已按“只喷图号”执行并传输", self.status_success_bg)
                return True
            if norm_head:
                try:
                    drv.fill_sortie(norm_head)
                except Exception as e:
                    if interactive:
                        QMessageBox.warning(self, "架次号写入失败", f"字符文件已打开，但写入架次号失败：{e}")
                    self._set_status("状态: 已打开字符文件，但架次号写入失败", self.status_warning_bg)
                    return False
                try:
                    drv.insert_text_at_tail(self.matched_char_file)
                except Exception as e:
                    if interactive:
                        QMessageBox.warning(self, "插入文字失败", f"架次号已写入，但插入文字失败：{e}")
                    self._set_status("状态: 架次号已写入，但插入文字失败", self.status_warning_bg)
                    return False
                try:
                    drv.transmit()
                except Exception as e:
                    if interactive:
                        QMessageBox.warning(self, "传输失败", f"架次号已插入，但传输信息失败：{e}")
                    self._set_status("状态: 架次号已插入，但传输信息失败", self.status_warning_bg)
                    return False
                self._set_status(f"状态: 已写入并插入架次号 {norm_head}，已执行传输信息", self.status_success_bg)
            else:
                self._set_status("状态: 已在喷码软件中打开字符文件", self.status_success_bg)
            return True
        except Exception as e:
            if interactive:
                logging.getLogger(__name__).error(f"打开字符文件失败: {e}", exc_info=True)
            else:
                logging.getLogger(__name__).warning(f"自动唤起失败: {e}")
            if interactive:
                QMessageBox.critical(self, "打开失败", f"无法打开字符文件：{e}")
            return False

    def _prompt_no_head_action(self) -> str:
        """未识别到架次号时，询问是重识别还是只喷图号。"""
        dlg = QDialog(self)
        dlg.setModal(True)
        dlg.setWindowTitle("未识别到架次号")
        dlg.setMinimumWidth(460)

        layout = QVBoxLayout(dlg)
        title = QLabel("没有识别到架次号，是否继续？", dlg)
        title.setObjectName("noHeadTitle")
        title.setWordWrap(True)
        info = QLabel("默认选项为“重新识别”（按 Enter），不会自动触发识别。", dlg)
        info.setObjectName("noHeadInfo")
        info.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        retry_btn = QPushButton("重新识别（默认/回车）", dlg)
        main_only_btn = QPushButton("只喷图号", dlg)
        for b in (retry_btn, main_only_btn):
            b.setMinimumHeight(42)
            b.setAutoDefault(True)
            b.setFocusPolicy(Qt.StrongFocus)
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        dlg.setStyleSheet(
            "QLabel#noHeadTitle { font-size: 16px; font-weight: 700; color: #1f1f1f; }"
            "QLabel#noHeadInfo { color: #595959; }"
            "QPushButton {"
            "  background-color: #f5f5f5;"
            "  color: #262626;"
            "  border: 2px solid #d9d9d9;"
            "  border-radius: 6px;"
            "  padding: 8px 14px;"
            "  font-size: 14px;"
            "}"
            "QPushButton:focus {"
            "  background-color: #cf1322;"
            "  color: #ffffff;"
            "  border: 3px solid #820014;"
            "  font-weight: 700;"
            "}"
            "QPushButton:pressed {"
            "  background-color: #a8071a;"
            "  color: #ffffff;"
            "}"
        )

        result = {"choice": "retry"}

        def _choose_retry():
            result["choice"] = "retry"
            dlg.accept()

        def _choose_main_only():
            result["choice"] = "main_only"
            dlg.accept()

        retry_btn.clicked.connect(_choose_retry)
        main_only_btn.clicked.connect(_choose_main_only)
        dlg.rejected.connect(_choose_retry)  # Esc/关闭按钮都回退到“重新识别”

        retry_btn.setDefault(True)
        retry_btn.setFocus()
        dlg.exec_()
        return result["choice"]

    def _maybe_auto_open_charfile(self, main_code: str, head_code: str = None):
        """匹配成功后自动唤起喷码软件，并自动写入架次号。"""
        if not self.auto_open_charfile_on_match:
            return
        if not main_code:
            return
        norm_head = self._normalize_head_code(head_code) if head_code else ""
        if not norm_head:
            action = self._prompt_no_head_action()
            if action == "main_only":
                # 无架次号：仅在“只喷图号”分支中再进入候选确认。
                if not self._confirm_candidate_for_main_code(main_code, force=True):
                    self.matched_char_file = None
                    self.matched_char_score = 0.0
                    self.charfile_label.setText("字符文件: <候选未确认>")
                    self.open_charfile_button.setEnabled(False)
                    return
                self._enqueue_vendor_push(head_code="", main_only_no_head=True)
            else:
                self._set_status("状态: 未识别到架次号；请调整后手动点击“开始识别”", self.status_warning_bg)
            return
        # 有架次号：直接进入候选确认（仅非满分/未匹配时弹出）。
        if not self._confirm_candidate_for_main_code(main_code, force=False):
            if not self.matched_char_file:
                self.charfile_label.setText("字符文件: <候选未确认>")
                self.open_charfile_button.setEnabled(False)
            return
        if not self.matched_char_file:
            return
        self._enqueue_vendor_push(head_code=head_code)

    def _infer_vendor_exe_from_demo_bat(self):
        """从项目根目录的 start_demo.bat 推断 --exe 参数路径。"""
        try:
            import re
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            bat = os.path.join(repo_root, "start_demo.bat")
            if not os.path.exists(bat):
                return None
            text = open(bat, "r", encoding="utf-8", errors="ignore").read()
            m = re.search(r'--exe\\s+\"([^\"]+)\"', text, re.IGNORECASE)
            if not m:
                return None
            exe = m.group(1).strip()
            if exe and os.path.exists(exe):
                return exe
            return None
        except Exception:
            return None

    def on_open_charfile(self):
        """通过自动化驱动喷码软件打开匹配到的字符文件。"""
        main_code = self.detected_main_code or ""
        norm_head = self._normalize_head_code(self.detected_head_code) if self.detected_head_code else ""
        if not norm_head:
            action = self._prompt_no_head_action()
            if action == "main_only":
                if not self._confirm_candidate_for_main_code(main_code, force=True):
                    return
                self._open_matched_charfile(interactive=True, head_code="", main_only_no_head=True)
            else:
                self._set_status("状态: 未识别到架次号；请调整后手动点击“开始识别”", self.status_warning_bg)
            return
        if not self._confirm_candidate_for_main_code(main_code, force=False):
            return
        self._open_matched_charfile(interactive=True, head_code=self.detected_head_code)

    def _init_sounds(self):
        """
        初始化通过和失败的音效
        """
        self.pass_sound = QSoundEffect(self)
        # 构建相对于项目根目录的路径
        pass_sound_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'assets', 'sounds', 'pass.wav')
        if not os.path.exists(pass_sound_path):
             logger.warning(f"Pass sound file not found at: {pass_sound_path}")
             self.pass_sound.setSource(QUrl())
        else:
            self.pass_sound.setSource(QUrl.fromLocalFile(pass_sound_path))
            logger.info(f"Loaded pass sound from: {pass_sound_path}")
        self.pass_sound.setVolume(0.8)
        # 恢复预热以避免首次不响
        try:
            orig = self.pass_sound.volume()
            self.pass_sound.setVolume(0.0)
            if self.pass_sound.source().isValid():
                self.pass_sound.play()
                QTimer.singleShot(120, lambda: (self.pass_sound.stop(), self.pass_sound.setVolume(orig)))
        except Exception:
            pass

        self.fail_sound = QSoundEffect(self)
        fail_sound_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'assets', 'sounds', 'fail.wav')
        if not os.path.exists(fail_sound_path):
            logger.warning(f"Fail sound file not found at: {fail_sound_path}")
            self.fail_sound.setSource(QUrl())
        else:
            self.fail_sound.setSource(QUrl.fromLocalFile(fail_sound_path))
            logger.info(f"Loaded fail sound from: {fail_sound_path}")
        self.fail_sound.setVolume(0.8)
        try:
            origf = self.fail_sound.volume()
            self.fail_sound.setVolume(0.0)
            if self.fail_sound.source().isValid():
                self.fail_sound.play()
                QTimer.singleShot(120, lambda: (self.fail_sound.stop(), self.fail_sound.setVolume(origf)))
        except Exception:
            pass

    def eventFilter(self, obj, event):
        # 全局捕获鼠标中键按下
        try:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.MiddleButton:
                self._recognize_current_frame()
                return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        try:
            self.stop_camera()
        except Exception:
            pass
        try:
            self._shutdown_vendor_push_worker()
        except Exception:
            pass
        super().closeEvent(event)
