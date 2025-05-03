#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CheckCheck 导管喷码自动核对系统 - 主窗口

此模块实现应用程序的主窗口，包括UI布局和基本功能。
"""

import os
import sys
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QMessageBox,
    QSplitter, QFrame, QGroupBox, QProgressDialog,
    QApplication, QFormLayout, QStyle, QComboBox
)
from PyQt5.QtGui import QPixmap, QImage, QFont, QIcon, QImageReader
from PyQt5.QtCore import Qt, QSize, QMimeData, pyqtSignal, QThread, QTimer
from src.core.processor import ImageProcessor
from src.utils.database_manager import init_db, add_history_record, check_history_exists
from src.ui.history_window import HistoryWindow
from src.workers.camera_worker import CameraWorker
from src.utils.camera_utils import detect_available_cameras
from src.core.text_comparator import TextComparator # 导入 TextComparator
import logging

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
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setText("请拖拽图片到此处或点击\"上传图像\"按钮")
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


class MainWindow(QMainWindow):
    """
    应用程序主窗口类
    """
    
    def __init__(self):
        """
        初始化主窗口
        """
        super().__init__()
        
        # 设置窗口属性
        self.setWindowTitle("CheckCheck - 导管喷码自动核对系统")
        self.setMinimumSize(1024, 768)
        
        # 初始化成员变量
        self.image_path = None
        self.current_image = None # QPixmap from loaded file
        self.cv_image = None      # OpenCV format image (from file or camera)
        self.processor = None     # 图像处理器
        self.processing_result = None  # 处理结果
        self.camera_thread = None      # Thread for camera worker
        self.camera_worker = None      # Worker for camera capture
        self.camera_running = False    # Flag for camera state
        self.camera_index = 1 # TODO: Make configurable
        self.ocr_processor = None # OCR 处理器
        self.pause_camera_updates = False
        self.available_cameras = [] # List to store available camera indices
        self.selected_camera_index = 0 # Default/selected camera index
        self.current_mode = "相机识别" # Default mode

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
        
        # 初始化图像处理器
        self._init_processor()
        # 初始化OCR处理器
        self._init_ocr_processor()
        # 初始化相机（但不启动）
        self._init_camera()
        # 自动启动摄像头
        self.start_camera()

        # 实例化 TextComparator
        self.text_comparator = TextComparator()

    def _init_processor(self):
        """
        初始化图像处理器
        """
        # 创建进度对话框
        progress = QProgressDialog("正在初始化OCR引擎...", None, 0, 0, self)
        progress.setWindowTitle("初始化中")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()
        
        # 初始化图像处理器
        try:
            self.processor = ImageProcessor(use_gpu=False)
            progress.close()
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "错误", f"初始化OCR引擎失败: {str(e)}")
        
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
        """
        logger.info("Initializing camera system and detecting available cameras...")
        self.available_cameras = detect_available_cameras()
        self.camera_selection_combo.clear() # Clear previous items

        if not self.available_cameras:
            logger.warning("No cameras detected.")
            self.camera_selection_combo.addItem("未检测到相机")
            self.camera_selection_combo.setEnabled(False)
            # Disable camera-related buttons if no camera is found
            # Use the correct button names based on _setup_ui
            self.recognize_button.setEnabled(False) 
            self.switch_mode_button.setEnabled(False)
            # self.resume_camera_button.setEnabled(False) # Resume button might not exist in this version yet
            self.statusBar().showMessage('未检测到可用摄像头')
        elif len(self.available_cameras) == 1:
            logger.info(f"Detected single camera with index: {self.available_cameras[0]}")
            self.camera_selection_combo.addItem(f"相机 {self.available_cameras[0]}")
            self.camera_selection_combo.setEnabled(False) # Disable selection if only one
            self.selected_camera_index = self.available_cameras[0] # Auto-select the only camera
            self.statusBar().showMessage(f'使用相机 {self.selected_camera_index}')
            # Ensure camera buttons are enabled
            self.recognize_button.setEnabled(True) 
            self.switch_mode_button.setEnabled(True)
        else:
            logger.info(f"Detected multiple cameras: {self.available_cameras}")
            for index in self.available_cameras:
                self.camera_selection_combo.addItem(f"相机 {index}", userData=index) # Store index in userData
            self.camera_selection_combo.setEnabled(True)
            # Set initial selection to the first detected camera
            self.camera_selection_combo.setCurrentIndex(0) 
            self.selected_camera_index = self.camera_selection_combo.currentData() # Get index from userData
            self.statusBar().showMessage(f'检测到多个相机，已选择相机 {self.selected_camera_index}')
             # Ensure camera buttons are enabled
            self.recognize_button.setEnabled(True) 
            self.switch_mode_button.setEnabled(True)
            # Connect signal for selection change
            self.camera_selection_combo.currentIndexChanged.connect(self.on_camera_selection_changed)
        
        logger.info("Camera system initialized.")

    def on_camera_selection_changed(self, index):
        """Handle camera selection change from the dropdown."""
        if index < 0 or not self.available_cameras or len(self.available_cameras) <= 1: 
            return 
        
        new_index = self.camera_selection_combo.itemData(index)
        if new_index is not None and new_index != self.selected_camera_index:
            logger.info(f"User selected camera index: {new_index}")
            self.selected_camera_index = new_index
            self.statusBar().showMessage(f'已选择相机 {self.selected_camera_index}')
            # If camera is currently running, stop and restart with the new index
            if self.camera_running:
                logger.info("Restarting camera with newly selected index...")
                self.stop_camera()
                # Short delay might be needed before restarting
                QTimer.singleShot(200, self.start_camera) 

    def _setup_ui(self):
        """
        设置UI布局和组件
        """
        # 主窗口和中心控件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 创建垂直分割器
        splitter = QSplitter(Qt.Vertical) # Revert to Vertical
        main_layout.addWidget(splitter)
        
        # 上方区域 - 图像显示
        image_widget = QWidget()
        image_layout = QVBoxLayout(image_widget)
        self.image_label = ImageDropLabel(self) # Use the custom label
        self.image_label.fileDropped.connect(self.load_image)
        image_layout.addWidget(self.image_label)
        splitter.addWidget(image_widget)
        
        # --- Bottom Panel (Controls and Results) - Reverted Structure ---
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(10, 10, 10, 10)
        bottom_layout.setSpacing(10) # Adjust spacing as needed

        # 结果显示区 (使用 QFormLayout)
        self.results_groupbox = QGroupBox("识别结果")
        results_layout = QFormLayout(self.results_groupbox) 
        results_layout.setContentsMargins(10, 10, 10, 10) # Add padding inside the groupbox
        results_layout.setSpacing(10)       # Add spacing between rows
        results_layout.setLabelAlignment(Qt.AlignRight) # Align labels to the right

        font = QFont()
        font.setPointSize(12) # Increase font size

        self.label_text_result = QLabel("标牌文字: 等待识别...")
        self.label_text_result.setFont(font)
        self.label_text_result.setTextInteractionFlags(Qt.TextSelectableByMouse) # Allow text selection
        results_layout.addRow(self.label_text_result) # Remove label for single line

        self.print_text_result = QLabel("喷码文字: 等待识别...")
        self.print_text_result.setFont(font)
        self.print_text_result.setTextInteractionFlags(Qt.TextSelectableByMouse) # Allow text selection
        results_layout.addRow(self.print_text_result) # Remove label for single line

        self.comparison_result = QLabel("比对结果: 等待比对...")
        self.comparison_result.setFont(font)
        self.comparison_result.setTextInteractionFlags(Qt.TextSelectableByMouse) # Allow text selection
        # QLabel 默认是左对齐的，通常不需要显式设置
        results_layout.addRow(self.comparison_result) # 移除标签
        
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

        self.upload_button = QPushButton(upload_icon, " 上传图像")
        self.upload_button.setToolTip("从本地文件上传图像")
        self.upload_button.clicked.connect(self.on_upload_image)
        button_layout.addWidget(self.upload_button)

        self.recognize_button = QPushButton(recognize_icon, " 开始识别") 
        self.recognize_button.setToolTip("对当前显示的图像或摄像头画面进行识别")
        self.recognize_button.clicked.connect(self._recognize_current_frame)
        self.recognize_button.setEnabled(False) # Initially disabled
        button_layout.addWidget(self.recognize_button)

        # --- Resume Camera Button (Re-added) ---
        self.resume_camera_button = QPushButton(resume_icon, " 恢复相机")
        self.resume_camera_button.setEnabled(False) # Start disabled
        self.resume_camera_button.setToolTip("恢复实时相机画面显示")
        self.resume_camera_button.clicked.connect(self.resume_camera) # Connect to method
        button_layout.addWidget(self.resume_camera_button)
        # --- End Resume Camera Button ---

        self.switch_mode_button = QPushButton(" 切换到相机")
        self.switch_mode_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.switch_mode_button.setToolTip("切换到相机识别模式")
        self.switch_mode_button.clicked.connect(self.switch_to_camera_mode)
        button_layout.addWidget(self.switch_mode_button)

        self.history_button = QPushButton(history_icon, " 历史记录") # Match screenshot text
        self.history_button.setToolTip("查看历史识别记录")
        self.history_button.clicked.connect(self._show_history_window)
        button_layout.addWidget(self.history_button)

        self.settings_button = QPushButton(settings_icon, " 设置")
        self.settings_button.setToolTip("应用程序设置")
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
        splitter.setSizes([int(self.height() * 0.7), int(self.height() * 0.3)]) 

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
        self.comparison_result.setStyleSheet(self.result_style)
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
        
        # Connect the drop signal
        self.image_label.fileDropped.connect(self._load_image)
    
    def on_upload_image(self):
        """
        处理上传图像按钮点击事件
        """
        # 打开文件对话框
        file_dialog = QFileDialog()
        image_path, _ = file_dialog.getOpenFileName(
            self, "选择图像", "", "图像文件 (*.png *.jpg *.jpeg *.bmp)"
        )
        
        # 如果用户选择了文件
        if image_path:
            self.load_image(image_path)
    
    def load_image(self, image_path):
        """
        加载并显示图像
        
        Args:
            image_path (str): 图像文件路径
        """
        # 保存图像路径
        self.image_path = image_path
        
        # 加载图像
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            QMessageBox.critical(self, "错误", "无法加载图像文件")
            return
        
        # 保存当前图像
        self.current_image = pixmap
        
        # 加载OpenCV格式的图像
        self.cv_image = cv2.imread(image_path)
        
        # 调整图像大小以适应标签
        pixmap = self._resize_pixmap(pixmap)
        
        # 显示图像
        self.image_label.setPixmap(pixmap)
        self.image_label.setAlignment(Qt.AlignCenter)
        
        # 启用识别按钮
        self.recognize_button.setEnabled(True)
        
        # 重置结果显示
        self.clear_recognition_results()
        
        # 如果摄像头在运行，停止它
        if self.camera_running:
             logger.info("Stopping camera because new image was loaded.")
             self.stop_camera()
        
        # 切换到图片模式
        self.switch_mode_button.setText(" 切换到相机")
        try:
            self.switch_mode_button.clicked.disconnect()
        except TypeError:
            pass  # 如果没有连接的信号，忽略错误
        self.switch_mode_button.clicked.connect(self.switch_to_camera_mode)

    def _resize_pixmap(self, pixmap):
        """
        调整图像大小以适应标签
        
        Args:
            pixmap (QPixmap): 原始图像
            
        Returns:
            QPixmap: 调整大小后的图像
        """
        # 获取标签大小
        label_size = self.image_label.size()
        
        # 计算缩放后的图像大小，保持纵横比
        scaled_pixmap = pixmap.scaled(
            label_size, 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        
        return scaled_pixmap
    
    def on_start_recognition(self):
        """
        处理开始识别按钮点击事件
        """
        if not self.ocr_processor:
            QMessageBox.critical(self, "错误", "OCR 处理器未初始化或加载失败。")
            return
        if not hasattr(self, 'image_path') or not self.image_path or not os.path.exists(self.image_path):
            QMessageBox.warning(self, "无图像", "请先上传有效的图像文件。")
            return

        logger.info(f"Starting recognition for static image: {self.image_path}")
        self.recognize_button.setEnabled(False)
        self.upload_button.setEnabled(False) # Disable upload during recognition
        # Update result displays with 'processing' status
        self.label_text_result.setText("标牌文字: [识别中...]")
        self.print_text_result.setText("喷码文字: [识别中...]")
        self.comparison_result.setText("比对结果: [处理中...]")
        QApplication.processEvents() # Allow UI to update

        try:
            # 使用已加载的OpenCV图像数据
            if self.cv_image is None:
                raise ValueError("无法使用已加载的图像")

            # Perform OCR using the common method
            results = self._perform_ocr(self.cv_image)

            if results is None: # Check if OCR itself failed
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
            
            # 在图像上绘制文本框
            if text_with_positions:
                marked_image = self._draw_text_boxes(self.cv_image.copy(), text_with_positions)
                
                # 将标记后的图像转换为QPixmap并显示
                h, w, ch = marked_image.shape
                bytes_per_line = ch * w
                qt_image = QImage(marked_image.data, w, h, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
                pixmap = QPixmap.fromImage(qt_image)
                pixmap = self._resize_pixmap(pixmap)
                self.image_label.setPixmap(pixmap)
                
                # 如果相机已经启动，则启用恢复相机按钮
                if self.camera_running:
                    self.pause_camera_updates = True
                    self.switch_mode_button.setText(" 恢复相机")
                    try:
                        self.switch_mode_button.clicked.disconnect()
                    except TypeError:
                        pass  # 如果没有连接的信号，忽略错误
                    self.switch_mode_button.clicked.connect(self.resume_camera)
            
            # --- Placeholder for actual result parsing --- 
            # You need to implement logic here to find the label and print text
            # based on the 'results' structure returned by your ocr_processor.ocr()
            # Example: Assuming results = [[box, (text, confidence)], ...]
            all_texts = [line[1][0] for line in results[0]] if results and results[0] else [] 
            label_text = "未识别" # Placeholder
            print_text = "未识别" # Placeholder
            if all_texts:
                 # Simple example: Assign first line to label, rest to print? Or use location?
                 label_text = all_texts[0]
                 print_text = " ".join(all_texts[1:]) if len(all_texts) > 1 else "(无)" 
            
            # --- Placeholder for comparison logic --- 
            if label_text != "未识别" and print_text != "未识别":
                # 计算相似度
                comparison_details = self.text_comparator.compare_texts(label_text, print_text)
                similarity = comparison_details['similarity'] # 从字典中提取相似度
                similarity_percent = int(similarity * 100)
                
                # 判断是否通过 (100%相似度才通过)
                if similarity_percent == 100:
                    comparison = f"<span style='color:green; font-weight:bold;'>✓ 通过</span> (相似度: {similarity_percent}%)"
                    background_color = self.pass_background_color
                else:
                    comparison = f"<span style='color:red; font-weight:bold;'>✗ 不通过</span> (相似度: {similarity_percent}%)"
                    background_color = self.fail_background_color
            else:
                comparison = "<span style='color:orange; font-weight:bold;'>? 无法比对</span>"
                background_color = self.fail_background_color
            # --------------------------------------------

            self.label_text_result.setText(f"标牌文字: {label_text}")
            self.print_text_result.setText(f"喷码文字: {print_text}")
            self.comparison_result.setText(f"比对结果: {comparison}")
            self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=background_color))
            
            # 添加记录到数据库
            if label_text != "未识别" and print_text != "未识别":
                try:
                    # 使用原始上传的图像路径保存记录
                    self.add_record(self.image_path, label_text, print_text, comparison)
                    logger.info(f"Recognition record saved to database for: {self.image_path}")
                except Exception as e:
                    logger.error(f"Failed to save record: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error during static image recognition: {e}", exc_info=True)
            QMessageBox.critical(self, "识别错误", f"处理静态图像时出错: {e}")
            self.label_text_result.setText("标牌文字: 错误")
            self.print_text_result.setText("喷码文字: 错误")
            self.comparison_result.setText("比对结果: 错误")
        finally:
            self.recognize_button.setEnabled(True) # Re-enable recognize button
            self.upload_button.setEnabled(True) # Re-enable upload button


    def _setup_database(self):
        pass

    def _recognize_current_frame(self):
        """Handles the click of the recognize button for both live and static images."""
        if not self.ocr_processor:
            QMessageBox.critical(self, "错误", "OCR 处理器未初始化或加载失败。")
            return

        if self.camera_running and self.cv_image is not None:
            # 重置暂停状态，确保获取最新的相机画面
            self.pause_camera_updates = False
            # 短暂延时，确保获取到最新的画面
            QTimer.singleShot(100, self._perform_camera_recognition)
        elif self.current_image:
            # 处理静态图像
            self.on_start_recognition()
        else:
            QMessageBox.warning(self, "无图像", "请先上传图像或启动摄像头。")
    
    def _perform_camera_recognition(self):
        """执行相机画面识别，与_recognize_current_frame分离以允许短暂延时获取最新画面"""
        logger.info("Recognizing current camera frame...")
        # Disable button during processing to prevent multiple clicks
        self.recognize_button.setEnabled(False)
        self.recognize_button.setText("识别中...")
        QApplication.processEvents() # Update UI
        
        try:
            # Perform OCR on the current frame
            results = self._perform_ocr(self.cv_image.copy()) # Use a copy to avoid race conditions
            
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
                self.label_text_result.setText("标牌文字: <未识别到文本>")
                self.print_text_result.setText("喷码文字: <未识别到文本>")
                self.comparison_result.setText("比对结果: <无法比对>")
                self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=self.fail_background_color))
                return
            
            # 在图像上绘制文本框
            marked_image = self._draw_text_boxes(self.cv_image.copy(), text_with_positions)
            
            # 将标记后的图像转换为QPixmap并显示
            h, w, ch = marked_image.shape
            bytes_per_line = ch * w
            qt_image = QImage(marked_image.data, w, h, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
            pixmap = QPixmap.fromImage(qt_image)
            pixmap = self._resize_pixmap(pixmap)
            self.image_label.setPixmap(pixmap) # Display frame
            self.current_image = None # Ensure static image is cleared

            # 暂停相机画面更新，保持显示标记后的画面
            self.pause_camera_updates = True
            self.resume_camera_button.setEnabled(True) # Enable the resume button
            # Disable recognize button while paused
            self.recognize_button.setEnabled(False)
            # Optional: Change mode switch button text/action while paused?
            # For simplicity, let's keep mode switch as is, resume is separate.
            
            # 按y坐标排序，区分上下文本
            text_with_positions.sort(key=lambda x: x[3])
            
            # 假设上半部分是标牌文字，下半部分是喷码文字
            # 计算中间分界线
            height = self.cv_image.shape[0]
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
                label_text = "<未识别到标牌文字>"
            else:
                label_text = " ".join(label_texts)
            
            if not print_texts:
                print_text = "<未识别到喷码文字>"
            else:
                print_text = " ".join(print_texts)
            
            # 比对文本相似度
            if label_text != "<未识别到标牌文字>" and print_text != "<未识别到喷码文字>":
                # 计算相似度 (使用 TextComparator)
                comparison_details = self.text_comparator.compare_texts(label_text, print_text)
                similarity = comparison_details['similarity'] # 从字典中提取相似度
                similarity_percent = int(similarity * 100)
                
                # 判断是否通过 (100%相似度才通过)
                if similarity_percent == 100:
                    result_text = f"<span style='color:green; font-weight:bold;'>✓ 通过</span> (相似度: {similarity_percent}%)"
                    background_color = self.pass_background_color
                else:
                    result_text = f"<span style='color:red; font-weight:bold;'>✗ 不通过</span> (相似度: {similarity_percent}%)"
                    background_color = self.fail_background_color
            else:
                result_text = "<span style='color:orange; font-weight:bold;'>? 无法比对</span>"
                background_color = self.fail_background_color
            
            # 更新UI显示
            self.label_text_result.setText(f"标牌文字: {label_text}")
            self.print_text_result.setText(f"喷码文字: {print_text}")
            self.comparison_result.setText(f"比对结果: {result_text}")
            self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=background_color))
            
            logger.info("Camera frame recognition complete.")
            
            # 保存记录到数据库 (可选)
            if label_text != "<未识别到标牌文字>" and print_text != "<未识别到喷码文字>":
                try:
                    # 保存当前帧
                    from datetime import datetime
                    capture_dir = self._ensure_capture_dir()
                    filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    save_path = os.path.join(capture_dir, filename)
                    cv2.imwrite(save_path, self.cv_image)
                    
                    # 保存记录
                    self.add_record(save_path, label_text, print_text, result_text)
                    logger.info(f"Camera frame recognition record saved to: {save_path}")
                except Exception as e:
                    logger.error(f"Failed to save camera record: {e}", exc_info=True)

        except Exception as e:
             logger.error(f"Error during camera frame recognition: {e}", exc_info=True)
             QMessageBox.critical(self, "识别错误", f"处理摄像头帧时出错: {e}")
             self.label_text_result.setText("标牌文字: 错误")
             self.print_text_result.setText("喷码文字: 错误")
             self.comparison_result.setText("比对结果: 错误")
             self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=self.fail_background_color))
        finally:
             # Re-enable button only if camera is still running AND not paused
             if self.camera_running and not self.pause_camera_updates:
                 self.recognize_button.setEnabled(True)
                 self.recognize_button.setText(" 开始识别")
             elif not self.camera_running: # If camera stopped during processing
                  self.recognize_button.setEnabled(False) # Keep disabled if static img not loaded
                  self.recognize_button.setText(" 开始识别")
             # Resume button state is handled when pausing/resuming
                  
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
            # 使用OCR处理器进行识别
            results = self.ocr_processor.ocr(image_data, cls=True)
            
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
            (0, 255, 0),    # 绿色 - 标牌文字
            (0, 0, 255),    # 红色 - 喷码文字
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
            
            # 绘制文本框
            points = np.array(box).astype(np.int32).reshape((-1, 1, 2))
            cv2.polylines(marked_image, [points], True, color, 2)
            
            # 计算文本框左上角坐标，用于放置文本标签
            min_x = min(point[0] for point in box)
            min_y = min(point[1] for point in box)
            
            # 分离文本和置信度
            text_part = text
            confidence_part = f"({confidence:.2f})"
            
            # 计算文本和置信度的尺寸
            (text_width, text_height), _ = cv2.getTextSize(text_part, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
            (conf_width, conf_height), _ = cv2.getTextSize(confidence_part, cv2.FONT_HERSHEY_SIMPLEX, font_scale/2, 1)
            
            # 确保文本不会超出图片边界
            text_bg_min_x = int(min_x)
            text_bg_min_y = int(min_y) - text_height - 10
            
            # 如果文本超出左边界，调整到左边界
            if text_bg_min_x < 0:
                text_bg_min_x = 0
                
            # 如果文本超出上边界，调整到文本框下方
            if text_bg_min_y < 0:
                text_bg_min_y = int(max(point[1] for point in box)) + 10
                
            text_bg_max_x = text_bg_min_x + text_width + conf_width
            text_bg_max_y = text_bg_min_y + text_height + 10
            
            # 如果文本超出右边界，调整整个文本框位置
            if text_bg_max_x > width:
                offset = text_bg_max_x - width
                text_bg_min_x = max(0, text_bg_min_x - offset)
                text_bg_max_x = text_bg_min_x + text_width + conf_width
                
            # 如果文本超出下边界，调整到文本框上方
            if text_bg_max_y > height:
                text_bg_min_y = int(min(point[1] for point in box)) - text_height - 20
                text_bg_max_y = text_bg_min_y + text_height + 10
            
            # 绘制纯白色背景（不再是半透明）
            cv2.rectangle(marked_image, (text_bg_min_x, text_bg_min_y), (text_bg_max_x, text_bg_max_y), (255, 255, 255), -1)
            
            # 绘制主文本
            cv2.putText(marked_image, text_part, (text_bg_min_x, text_bg_max_y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 2)
            
            # 绘制置信度（字体大小为主文本的一半）
            conf_x = text_bg_min_x + text_width + 5  # 在主文本后留一点间距
            cv2.putText(marked_image, confidence_part, (conf_x, text_bg_max_y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale/2, (100, 100, 100), 1)  # 使用灰色显示置信度
        
        return marked_image


# --- UI Setup and Event Handlers ---

    def on_open_settings(self):
        """
        处理打开设置按钮点击事件
        """
        QMessageBox.information(
            self, 
            "信息", 
            "设置功能将在后续阶段实现"
        )
    
    def _show_history_window(self):
        """Opens the history window dialog."""
        # Check if an instance already exists to avoid multiple windows (optional)
        # Or simply create a new modal dialog each time
        history_dialog = HistoryWindow(self) # Pass parent for modality if desired
        history_dialog.exec_() # Show as a modal dialog

    def closeEvent(self, event):
        """
        处理窗口关闭事件，确保摄像头线程停止
        """
        logger.info("Close event received. Stopping camera...")
        self.stop_camera() # Ensure camera is stopped before closing
        super().closeEvent(event)

    def resizeEvent(self, event):
        """
        处理窗口大小改变事件，重新调整图像大小
        
        Args:
            event: 大小改变事件
        """
        super().resizeEvent(event)
        
        # 如果有当前图像，则重新调整大小
        if self.current_image:
            pixmap = self._resize_pixmap(self.current_image)
            self.image_label.setPixmap(pixmap)

    def _load_image(self, image_path):
        """
        加载并显示图像
        
        Args:
            image_path (str): 图像文件路径
        """
        # 保存图像路径
        self.image_path = image_path
        
        # 加载图像
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            QMessageBox.critical(self, "错误", "无法加载图像文件")
            return
        
        # 保存当前图像
        self.current_image = pixmap
        
        # 加载OpenCV格式的图像
        self.cv_image = cv2.imread(image_path)
        
        # 调整图像大小以适应标签
        pixmap = self._resize_pixmap(pixmap)
        
        # 显示图像
        self.image_label.setPixmap(pixmap)
        self.image_label.setAlignment(Qt.AlignCenter)
        
        # 启用识别按钮
        self.recognize_button.setEnabled(True)
        
        # 重置结果显示
        self.clear_recognition_results()
        
        # 如果摄像头在运行，停止它
        if self.camera_running:
             logger.info("Stopping camera because new image was loaded.")
             self.stop_camera()
        
        # 切换到图片模式
        self.switch_mode_button.setText(" 切换到相机")
        try:
            self.switch_mode_button.clicked.disconnect()
        except TypeError:
            pass  # 如果没有连接的信号，忽略错误
        self.switch_mode_button.clicked.connect(self.switch_to_camera_mode)

    # --- Camera Methods ---

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

        # Disable camera selection while camera is starting/running
        # if len(self.available_cameras) > 1:
        #     self.camera_selection_combo.setEnabled(False) 
        
        # Clear any existing image display
        if self.current_image:
            self.current_image = None
            self.cv_image = None
            self.image_label.clear()
            self.image_label.setText("启动摄像头...") 
        
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

        # Reset image label 
        self.image_label.clear() # Clear pixmap first
        self.image_label.setText("请拖拽图片到此处或点击\"上传图像\"按钮") # Corrected text
        self.image_label.setStyleSheet("background-color: #f0f0f0; color: gray;")
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
        if not self.camera_running or self.pause_camera_updates:
            return
            
        self.cv_image = frame.copy() # Save frame
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
        pixmap = QPixmap.fromImage(qt_image)
        pixmap = self._resize_pixmap(pixmap)
        self.image_label.setPixmap(pixmap) # Display frame
        self.current_image = None # Ensure static image is cleared

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

    def _ensure_capture_dir(self):
        """确保捕获图像的保存目录存在"""
        capture_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'captures')
        os.makedirs(capture_dir, exist_ok=True)
        return capture_dir
    
    def add_record(self, image_path, sign_text, print_text, result_text):
        """将识别结果保存到数据库"""
        try:
            # 从比对结果中提取相似度
            import re
            similarity = 0.0
            if "相似度:" in result_text:
                match = re.search(r'相似度: (\d+)%', result_text)
                if match:
                    similarity = float(match.group(1)) / 100
            
            # 提取结果（通过/不通过）
            # 更精确地判断是否通过，检查是否包含"✓ 通过"而不是仅检查"通过"
            result = "通过" if "✓ 通过" in result_text else "不通过"
            
            # 调用数据库函数保存记录
            from src.utils.database_manager import add_history_record
            add_history_record(image_path, sign_text, print_text, similarity, result)
            logger.info(f"Record saved: {image_path}, {sign_text}, {print_text}, {similarity}, {result}")
            return True
        except Exception as e:
            logger.error(f"Failed to save record: {e}")
            return False

    def switch_to_camera_mode(self):
        """切换到相机识别模式"""
        if self.camera_running: return # Already in camera mode
        self.clear_recognition_results()
        # Clear image display and variables
        self.image_label.clear()
        self.image_label.setText("正在启动相机...")
        self.current_image = None
        self.cv_image = None
        self.image_path = None 
        QApplication.processEvents() 
        self.start_camera() # This will update buttons via update_camera_status

    def switch_to_image_mode(self):
        """切换到图片识别模式"""
        if not self.camera_running: return # Already in image mode or camera failed
        self.pause_camera_updates = False # Ensure pause is reset
        self.resume_camera_button.setEnabled(False) # Disable resume button
        self.clear_recognition_results()
        self.stop_camera() # This updates buttons and resets label

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
        self.label_text_result.setText("标牌文字: 等待识别...")
        self.print_text_result.setText("喷码文字: 等待识别...")
        self.comparison_result.setText("比对结果: 等待比对...")
        self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=self.default_groupbox_background))
        # 清除处理结果
        self.processing_result = None
