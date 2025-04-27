#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CheckCheck 导管喷码自动核对系统 - 主窗口

此模块实现应用程序的主窗口，包括UI布局和基本功能。
"""

import os
import sys
import time
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QMessageBox,
    QSplitter, QFrame, QGroupBox, QProgressDialog,
    QApplication, QFormLayout, QStyle, QSizePolicy
)
from PyQt5.QtGui import QPixmap, QImage, QFont, QIcon, QImageReader
from PyQt5.QtCore import Qt, QSize, QMimeData, pyqtSignal, QTimer, pyqtSlot
from src.core.processor import ImageProcessor
from src.utils.database_manager import init_db, add_history_record, check_history_exists 
from src.ui.history_window import HistoryWindow
from src.core.camera_manager import CameraManager
import logging

# --- Custom Widget for Drag and Drop --- 

class ImageDropLabel(QLabel):
    """A QLabel subclass that accepts image file drops."""
    fileDropped = pyqtSignal(str) # Signal emitted when a valid image file is dropped

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setText("将图像文件拖拽到此处 或 点击上传图像按钮 或 等待摄像头启动...")
        self.setFrameShape(QFrame.Box)
        self.setMinimumHeight(400)
        self.setMinimumSize(400, 300) # Set a minimum size
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored) # Allow shrinking/expanding
        self.setScaledContents(True) # Enable scaling
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
        self.current_image = None 
        self.cv_image = None  
        self.current_cv_frame = None 
        self.processor = None  
        self.processing_result = None  
        self.camera_manager = None 
        self.frame_log_count = 0 # <-- 添加日志计数器
        
        # 初始化数据库
        try:
            init_db()
        except Exception as e:
            QMessageBox.critical(self, "数据库错误", f"无法初始化历史记录数据库: {e}")
        
        # 设置UI
        self._setup_ui()
        
        # 初始化图像处理器 和 摄像头
        self._init_processor()
        self._init_camera() 
        
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
            logging.error(f"Failed to initialize processor: {e}", exc_info=True) 

    def _init_camera(self):
        """Initialize the camera manager."""
        try:
            # Attempt to initialize the camera manager with index 1
            self.camera_manager = CameraManager(camera_index=1, parent=self) # <-- Changed index to 1
            self.camera_manager.frame_ready.connect(self.update_frame, Qt.QueuedConnection)
            self.camera_manager.error.connect(self.handle_camera_error)
            self.camera_manager.start_capture()

            logging.info("CameraManager initialized.")
        except Exception as e:
            QMessageBox.critical(self, "摄像头错误", f"无法初始化摄像头管理器: {e}")
            logging.error(f"Failed to initialize CameraManager: {e}", exc_info=True)
            self.camera_manager = None 

    def _setup_ui(self):
        """
        设置UI布局和组件
        """
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 创建分割器，上方为图像显示区，下方为结果显示区
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter)
        
        # 上方区域 - 图像显示
        image_widget = QWidget()
        image_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) # <-- 添加此行
        image_layout = QVBoxLayout(image_widget)
        
        # 图像显示标签 - 使用自定义的 ImageDropLabel
        self.image_label = ImageDropLabel(self) 
        self.image_label.setScaledContents(True) 
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) 
        image_layout.addWidget(self.image_label)
        
        # 添加到分割器
        splitter.addWidget(image_widget)
        
        # 下方区域 - 结果显示和控制按钮
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        
        # 结果显示区 (使用 QFormLayout)
        self.results_groupbox = QGroupBox("识别结果")
        results_layout = QFormLayout(self.results_groupbox) 
        results_layout.setRowWrapPolicy(QFormLayout.WrapLongRows) 
        results_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        results_layout.setLabelAlignment(Qt.AlignLeft)
        results_layout.setVerticalSpacing(15) 
        
        # 定义更大的字体
        result_font = QFont()
        result_font.setPointSize(14) 
        
        # 标牌文字结果
        self.label_text_result = QLabel("等待识别...")
        self.label_text_result.setFont(result_font) 
        self.label_text_result.setWordWrap(True) 
        results_layout.addRow(self.label_text_result) 
        
        # 喷码文字结果
        self.print_text_result = QLabel("等待识别...")
        self.print_text_result.setFont(result_font) 
        self.print_text_result.setWordWrap(True) 
        results_layout.addRow(self.print_text_result) 
        
        # 比对结果 (改回 QLabel)
        self.comparison_result = QLabel("等待比对...") 
        self.comparison_result.setFont(result_font) 
        self.comparison_result.setTextFormat(Qt.RichText) 
        self.comparison_result.setWordWrap(True) 
        results_layout.addRow(self.comparison_result) 
        
        bottom_layout.addWidget(self.results_groupbox)
        
        # 控制按钮区域
        button_layout = QHBoxLayout()
        
        # 上传图像按钮
        self.upload_button = QPushButton("上传图像")
        upload_icon = self.style().standardIcon(QStyle.SP_DialogOpenButton) 
        self.upload_button.setIcon(upload_icon) 
        self.upload_button.setIconSize(QSize(24, 24)) 
        self.upload_button.clicked.connect(self.on_upload_image)
        button_layout.addWidget(self.upload_button)
        
        # 开始识别按钮
        self.recognize_button = QPushButton("开始识别")
        recognize_icon = self.style().standardIcon(QStyle.SP_MediaPlay) 
        self.recognize_button.setIcon(recognize_icon) 
        self.recognize_button.setIconSize(QSize(24, 24)) 
        self.recognize_button.clicked.connect(self.on_start_recognition)
        self.recognize_button.setEnabled(False)  
        button_layout.addWidget(self.recognize_button)
        
        # 设置按钮
        self.settings_button = QPushButton("设置")
        settings_icon = self.style().standardIcon(QStyle.SP_FileDialogDetailedView) 
        self.settings_button.setIcon(settings_icon) 
        self.settings_button.setIconSize(QSize(24, 24)) 
        self.settings_button.clicked.connect(self.on_open_settings)
        button_layout.addWidget(self.settings_button)
        
        # 历史记录按钮
        self.history_button = QPushButton(" 历史记录") 
        history_icon = self.style().standardIcon(QStyle.SP_FileDialogListView) 
        self.history_button.setIcon(history_icon)
        self.history_button.setIconSize(QSize(24, 24)) 
        self.history_button.clicked.connect(self._show_history_window)
        button_layout.addWidget(self.history_button)
        
        # 将按钮布局添加到下方布局
        bottom_layout.addLayout(button_layout)
        
        # 添加到分割器
        splitter.addWidget(bottom_widget)
        
        # 设置分割器比例 (注释掉，让其自动分配)
        # splitter.setSizes([int(self.height() * 0.7), int(self.height() * 0.3)])

        # 应用简单的 QSS 样式
        self.setStyleSheet("""
            QMainWindow { background-color: #ffffff; }
            QGroupBox { font-size: 12pt; border: 1px solid #cccccc; border-radius: 5px; margin-top: 1.5ex; padding-top: 12px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; left: 10px; }
            QPushButton { padding: 8px 15px; border: 1px solid #cccccc; border-radius: 4px; background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f6f7fa, stop:1 #dadbde); min-width: 80px; font-size: 10pt; }
            QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e6e7ea, stop:1 #ced0d4); }
            QPushButton:pressed { background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #dadbde, stop:1 #f6f7fa); }
            QPushButton:disabled { background-color: #e0e0e0; color: #a0a0a0; }
            QLabel { font-size: 10pt; } /* Add default font size for other QLabels */
            #image_label { border: 1px solid #cccccc; } /* Remove background color */
        """)
        
        self.base_groupbox_style = "QGroupBox {{ border: 1px solid gray; border-radius: 5px; margin-top: 0.5em; background-color: {background_color}; }} QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }}"
        self.default_groupbox_background = "transparent"
        self.pass_background_color = "#ccffcc" 
        self.fail_background_color = "#ffcccc" 
        
        # 设置初始默认背景（可能会被全局样式覆盖，但没关系，处理时会重新设置）
        self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=self.default_groupbox_background))
        
        # Connect the drop signal
        self.image_label.fileDropped.connect(self._load_image)

    # --- Camera Handling Slots --- 

    @pyqtSlot(np.ndarray)
    def update_frame(self, frame):
        """更新显示的图像帧"""
        # logging.debug("update_frame called.")
        if frame is not None:
            # logging.debug(f"Received frame with shape: {frame.shape}, dtype: {frame.dtype}")
            try:
                # Log raw frame details before conversion
                logging.debug(f"Raw frame shape: {frame.shape}, dtype: {frame.dtype}") # <-- Added log

                # Convert frame from BGR to RGB
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width, channel = rgb_frame.shape
                bytes_per_line = 3 * width
                
                # Create QImage using a copy
                q_img = QImage(rgb_frame.copy().data, width, height, bytes_per_line, QImage.Format_RGB888)

                if q_img.isNull():
                    logging.error("Failed to create QImage from frame.")
                    return

                pixmap = QPixmap.fromImage(q_img)

                if pixmap.isNull():
                    logging.error("Failed to create QPixmap from QImage.")
                    return

                # logging.debug(f"Setting pixmap with size: {pixmap.size()}") # Log is already present from previous step
                self.image_label.setPixmap(pixmap)
                # logging.debug("Pixmap set on image_label.") # Log is already present

            except Exception as e:
                logging.error(f"Error processing frame in update_frame: {e}", exc_info=True) # Added exc_info

    @pyqtSlot(str)
    def handle_camera_error(self, error_message):
        """Slot to handle errors reported by the camera manager."""
        QMessageBox.critical(self, "摄像头错误", error_message)
        logging.error(f"Camera Error: {error_message}")
        # Disable recognition if camera fails
        self.recognize_button.setEnabled(False)
        self.recognize_button.setText("开始识别")
        self.image_label.setText("摄像头错误，请检查连接或设置。")

    # --- Event Overrides --- 

    def showEvent(self, event):
        """Start camera when the window is shown."""
        super().showEvent(event)
        if self.camera_manager:
            logging.info("Window shown, starting camera capture.")
            self.camera_manager.start_capture()
        else:
            logging.warning("Window shown, but camera manager is not available.")

    def closeEvent(self, event):
        """Stop camera and clean up when the window closes."""
        logging.info("Window closing, stopping camera capture.")
        if self.camera_manager:
            # Accessing the internal worker via the public method is better practice if available
            # Assuming CameraManager's stop_capture handles waiting appropriately.
            self.camera_manager.stop_capture() 
            # If stop_capture doesn't wait, we might need to add a wait here, 
            # but ideally CameraManager handles its own worker cleanup.
 
        super().closeEvent(event)

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
        self.label_text_result.setText("标牌文字: 等待识别...")
        self.print_text_result.setText("喷码文字: 等待识别...")
        self.comparison_result.setText("比对结果: 等待比对...")
        self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=self.default_groupbox_background))
        
        # 清除处理结果
        self.processing_result = None

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
        # Determine the input image source
        input_image = None
        source_text = ""
        if self.camera_manager and self.camera_manager.is_running() and self.current_cv_frame is not None:
            input_image = self.current_cv_frame.copy() # Use a copy to avoid race conditions
            source_text = "(摄像头)"
            logging.info("Starting recognition using camera frame.")
        elif self.cv_image is not None:
            input_image = self.cv_image # Already loaded from file
            source_text = "(文件)"
            logging.info("Starting recognition using uploaded file.")
        else:
            QMessageBox.warning(self, "无法识别", "没有可用的图像来源。请先上传图像或确保摄像头正在运行。")
            logging.warning("Recognition attempt failed: No image source available.")
            return

        # 清除旧结果并禁用按钮
        self.clear_results()
        self.recognize_button.setEnabled(False)
        self.recognize_button.setText(f"正在处理 {source_text}...")
        QApplication.processEvents() # 确保UI更新
        
        try:
            # 处理图像
            self.processing_result = self.processor.process_image(input_image)
            
            # 更新UI显示结果
            self._update_results_display(self.processing_result)
            
            # 尝试保存到历史记录 (确保 self.image_path 存在或处理摄像头情况)
            # Determine image path for history (use placeholder for camera for now)
            history_image_path = self.image_path if self.cv_image is not None else "camera_capture"
            
            if self.processing_result: # Ensure there are results to save
                try:
                    # 提取原始文本和结果 - **使用原始文本字段**
                    # !! 请确保 'label_text' 和 'print_text' 是 processor 返回结果中包含原始文本的正确键名 !!
                    sign_text_raw = self.processing_result.get('label_text', "") 
                    print_text_raw = self.processing_result.get('print_text', "") 
                    similarity = self.processing_result.get('similarity', 0.0)
                    result_str = "通过" if abs(similarity - 1.0) < 1e-6 else "不通过"
                    
                    # 检查是否已存在相同的记录 (使用 history_image_path)
                    if history_image_path and not check_history_exists(history_image_path, sign_text_raw, print_text_raw):
                        add_history_record(
                            history_image_path,
                            sign_text_raw,
                            print_text_raw,
                            similarity,
                            result_str
                        )
                        logging.info(f"History record added for {history_image_path}")
                    elif not history_image_path:
                        logging.warning("History image path is None or invalid, cannot check/save history.")
                    else:
                        logging.info(f"History record already exists for {history_image_path}. Displaying duplicate info.")
                        self.comparison_result.setText(self.comparison_result.text() + " <span style='color: gray; font-size: 9pt;'>(已存在该条记录)</span>")
                except Exception as e:
                    QMessageBox.warning(self, "历史记录错误", f"无法保存历史记录: {e}")
                    logging.error(f"Error saving history: {e}", exc_info=True)
        
        except Exception as e:
            QMessageBox.critical(self, "处理错误", f"图像处理失败: {e}")
            logging.error(f"Error during processing: {e}", exc_info=True)
            self.clear_results()
        
        finally:
            # 无论成功或失败，都重新启用按钮并恢复文本
            self.recognize_button.setEnabled(True)
            # Restore button text based on available source (if any)
            if self.camera_manager and self.camera_manager.is_running():
                self.recognize_button.setText("开始识别 (摄像头)")
            elif self.cv_image is not None:
                self.recognize_button.setText("开始识别 (文件)")
            else:
                self.recognize_button.setText("开始识别")
                self.recognize_button.setEnabled(False) # Disable if no source
 
    def _update_results_display(self, results):
        """
        更新结果显示
        """
        if not results:
            return
        
        # 获取结果
        html_label_text = results.get('html_label_text', "")
        html_print_text = results.get('html_print_text', "")
        comparison = results.get('comparison', {})
        
        # 更新标牌文字 (使用HTML)
        self.label_text_result.setText(f"标牌文字: {html_label_text}")
        self.label_text_result.setTextFormat(Qt.RichText) 
        
        # 更新喷码文字 (使用HTML)
        self.print_text_result.setText(f"喷码文字: {html_print_text}")
        self.print_text_result.setTextFormat(Qt.RichText) 
        
        # 更新比对结果
        similarity = comparison.get('similarity', 0.0)
        
        result_text = f"相似度 {similarity:.2%}" 
        
        # 仅在 100% 相似时判断为通过
        if abs(similarity - 1.0) < 1e-6: 
            result_text += ", <b><span style='color: green;'>✔ 通过</span></b>" 
            bg_color = self.pass_background_color
        else:
            result_text += ", <b><span style='color: red;'>✘ 不通过</span></b>" 
            bg_color = self.fail_background_color
 
        self.comparison_result.setText(result_text) 
 
        # Apply background color to the results groupbox
        self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=bg_color))
 
    def _display_processed_image(self):
        """
        显示处理后的图像
        """
        if not self.processing_result or 'visualized_image' not in self.processing_result:
            return
        
        # 获取处理后的图像
        vis_image = self.processing_result['visualized_image']
        
        # 转换为QPixmap
        height, width, channel = vis_image.shape
        bytes_per_line = 3 * width
        q_image = QImage(vis_image.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
        pixmap = QPixmap.fromImage(q_image)
        
        # 调整大小并显示
        pixmap = self._resize_pixmap(pixmap)
        self.image_label.setPixmap(pixmap)
    
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
        history_dialog = HistoryWindow(self) 
        history_dialog.exec_() 
    
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
        self.label_text_result.setText("标牌文字: 等待识别...")
        self.print_text_result.setText("喷码文字: 等待识别...")
        self.comparison_result.setText("比对结果: 等待比对...")
        self.results_groupbox.setStyleSheet(self.base_groupbox_style.format(background_color=self.default_groupbox_background))
        
        # 清除处理结果
        self.processing_result = None

# --- Application Entry Point --- 
if __name__ == '__main__':
    # Configure logging - set level to DEBUG to see all messages
    logging.basicConfig(level=logging.DEBUG, 
                        format='%(asctime)s - %(levelname)s - %(name)s - %(threadName)s - %(message)s')
    
    # Force the style to be the same on all OSs:
    QApplication.setStyle("Fusion")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
