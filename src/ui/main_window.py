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
    QApplication, QFormLayout, QStyle
)
from PyQt5.QtGui import QPixmap, QImage, QFont, QIcon
from PyQt5.QtCore import Qt, QSize

# 导入核心处理模块
from src.core.processor import ImageProcessor
from src.utils.database_manager import init_db, add_history_record
from src.ui.history_window import HistoryWindow

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
        self.cv_image = None  # OpenCV格式的图像
        self.processor = None  # 图像处理器
        self.processing_result = None  # 处理结果
        
        # 初始化数据库
        try:
            init_db()
        except Exception as e:
            QMessageBox.critical(self, "数据库错误", f"无法初始化历史记录数据库: {e}")
        
        # 设置UI
        self._setup_ui()
        
        # 初始化图像处理器
        self._init_processor()
        
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
        image_layout = QVBoxLayout(image_widget)
        
        # 图像显示标签
        self.image_label = QLabel("请上传图像")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFrameShape(QFrame.Box)
        self.image_label.setMinimumHeight(400)
        self.image_label.setStyleSheet("background-color: #f0f0f0;")
        self.image_label.setObjectName("image_label") # 给图像标签设置对象名以便QSS选择
        image_layout.addWidget(self.image_label)
        
        # 添加到分割器
        splitter.addWidget(image_widget)
        
        # 下方区域 - 结果显示和控制按钮
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        
        # 结果显示区 (使用 QFormLayout)
        results_group = QGroupBox("识别结果")
        results_layout = QFormLayout(results_group) 
        results_layout.setRowWrapPolicy(QFormLayout.WrapLongRows) # 允许长行换行
        results_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        results_layout.setLabelAlignment(Qt.AlignLeft)
        results_layout.setVerticalSpacing(15) # 增大行之间的垂直间距

        # 定义更大的字体
        result_font = QFont()
        result_font.setPointSize(14) # 设置字体大小为 14
        
        # 标牌文字结果
        self.label_text_result = QLabel("等待识别...")
        self.label_text_result.setFont(result_font) # 应用字体
        self.label_text_result.setWordWrap(True) # 允许换行
        results_layout.addRow(self.label_text_result) # 移除标签
        
        # 喷码文字结果
        self.print_text_result = QLabel("等待识别...")
        self.print_text_result.setFont(result_font) # 应用字体
        self.print_text_result.setWordWrap(True) # 允许换行
        results_layout.addRow(self.print_text_result) # 移除标签
        
        # 比对结果 (改回 QLabel)
        self.comparison_result = QLabel("等待比对...") # 改回 QLabel
        self.comparison_result.setFont(result_font) # 应用字体
        self.comparison_result.setTextFormat(Qt.RichText) # 允许富文本
        self.comparison_result.setWordWrap(True) # 允许换行
        # QLabel 默认是左对齐的，通常不需要显式设置
        results_layout.addRow(self.comparison_result) # 移除标签
        
        bottom_layout.addWidget(results_group)
        
        # 控制按钮区域
        button_layout = QHBoxLayout()
        
        # 上传图像按钮
        self.upload_button = QPushButton("上传图像")
        upload_icon = self.style().standardIcon(QStyle.SP_DialogOpenButton) # 获取标准图标
        self.upload_button.setIcon(upload_icon) # 设置图标
        self.upload_button.setIconSize(QSize(24, 24)) # 设置图标大小
        self.upload_button.clicked.connect(self.on_upload_image)
        button_layout.addWidget(self.upload_button)
        
        # 开始识别按钮
        self.recognize_button = QPushButton("开始识别")
        recognize_icon = self.style().standardIcon(QStyle.SP_MediaPlay) # 获取标准图标
        self.recognize_button.setIcon(recognize_icon) # 设置图标
        self.recognize_button.setIconSize(QSize(24, 24)) # 设置图标大小
        self.recognize_button.clicked.connect(self.on_start_recognition)
        self.recognize_button.setEnabled(False)  # 初始禁用，直到上传图像
        button_layout.addWidget(self.recognize_button)
        
        # 设置按钮
        self.settings_button = QPushButton("设置")
        settings_icon = self.style().standardIcon(QStyle.SP_FileDialogDetailedView) # 获取标准图标
        self.settings_button.setIcon(settings_icon) # 设置图标
        self.settings_button.setIconSize(QSize(24, 24)) # 设置图标大小
        self.settings_button.clicked.connect(self.on_open_settings)
        button_layout.addWidget(self.settings_button)
        
        # 历史记录按钮
        self.history_button = QPushButton(" 历史记录") # Keep space for alignment if needed
        history_icon = self.style().standardIcon(QStyle.SP_FileDialogListView) # Use standard icon
        self.history_button.setIcon(history_icon)
        self.history_button.setIconSize(QSize(24, 24)) # Match other buttons' icon size
        self.history_button.clicked.connect(self._show_history_window)
        button_layout.addWidget(self.history_button)
        
        # 将按钮布局添加到下方布局
        bottom_layout.addLayout(button_layout)
        
        # 添加到分割器
        splitter.addWidget(bottom_widget)
        
        # 设置分割器比例
        splitter.setSizes([int(self.height() * 0.7), int(self.height() * 0.3)])

        # 应用简单的 QSS 样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ffffff; /* 设置主窗口背景色 */
            }
            QGroupBox {
                font-size: 12pt; /* 组框标题字体大小 */
                border: 1px solid #cccccc; /* 组框边框 */
                border-radius: 5px; /* 圆角 */
                margin-top: 1.5ex; /* 增大顶部外边距，为标题留出更多空间 */
                padding-top: 12px; /* 增加顶部内边距，将内容向下推 */
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 3px;
                left: 10px; /* 标题左边距 */
            }
            QPushButton {
                padding: 8px 15px; /* 按钮内边距 */
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f6f7fa, stop:1 #dadbde); /* 渐变背景 */
                min-width: 80px; /* 按钮最小宽度 */
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e6e7ea, stop:1 #ced0d4); /* 悬停效果 */
            }
            QPushButton:pressed {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #dadbde, stop:1 #f6f7fa); /* 按下效果 */
            }
            QPushButton:disabled {
                background-color: #e0e0e0; /* 禁用状态 */
                color: #a0a0a0;
            }
            QLabel#image_label {
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
            }
        """)
    
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
        # 检查是否已加载图像
        if self.cv_image is None:
            QMessageBox.warning(self, "警告", "请先上传图像")
            return
        
        # 检查处理器是否初始化
        if self.processor is None:
            QMessageBox.critical(self, "错误", "OCR引擎未初始化")
            return

        # 禁用按钮并显示状态
        self.recognize_button.setEnabled(False)
        self.recognize_button.setText("正在处理...")
        QApplication.processEvents() # 确保UI更新
        
        try:
            # 处理图像
            self.processing_result = self.processor.process_image(self.cv_image)
            
            # 更新UI显示结果
            self._update_results_display()
            
            # 显示处理后的图像
            self._display_processed_image()
            
            # 保存历史记录
            if self.processing_result:
                try:
                    # 提取原始文本和结果 - **使用原始文本字段**
                    # !! 请确保 'label_text' 和 'print_text' 是 processor 返回结果中包含原始文本的正确键名 !!
                    sign_text_raw = self.processing_result.get('label_text', "") # <--- Correct key for label text
                    print_text_raw = self.processing_result.get('print_text', "") # <--- 使用原始喷码文本
                    similarity = self.processing_result.get('comparison', {}).get('similarity', 0.0)
                    result_str = "通过" if abs(similarity - 1.0) < 1e-6 else "不通过"
                    
                    # 保存历史记录
                    if self.image_path:
                        add_history_record(
                            self.image_path, 
                            sign_text_raw, 
                            print_text_raw, 
                            similarity, 
                            result_str
                        )
                    else:
                        print("Warning: current_image_path is not set, cannot save history.") # 或者记录日志
                except Exception as e:
                    QMessageBox.warning(self, "历史记录错误", f"无法保存历史记录: {e}")
                    # 或者记录日志
                    print(f"Error saving history: {e}")
        
        except Exception as e:
            QMessageBox.critical(self, "错误", f"图像处理失败: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            # 恢复按钮状态
            self.recognize_button.setEnabled(True)
            self.recognize_button.setText("开始识别")
    
    def _update_results_display(self):
        """
        更新结果显示
        """
        if not self.processing_result:
            return
        
        # 获取结果
        html_label_text = self.processing_result.get('html_label_text', "")
        html_print_text = self.processing_result.get('html_print_text', "")
        comparison = self.processing_result.get('comparison', {})
        
        # 更新标牌文字 (使用HTML)
        self.label_text_result.setText(f"标牌文字: {html_label_text}")
        self.label_text_result.setTextFormat(Qt.RichText) # 确保能解析HTML
        
        # 更新喷码文字 (使用HTML)
        self.print_text_result.setText(f"喷码文字: {html_print_text}")
        self.print_text_result.setTextFormat(Qt.RichText) # 确保能解析HTML
        
        # 更新比对结果
        similarity = comparison.get('similarity', 0.0)
        
        result_text = f"相似度 {similarity:.2%}" # 只显示相似度
        
        # 仅在 100% 相似时判断为通过
        if abs(similarity - 1.0) < 1e-6: # 使用浮点数比较
            result_text += ", <b><span style='color: green;'>✔ 通过</span></b>" # 添加 ✔ 图标
        else:
            result_text += ", <b><span style='color: red;'>✘ 不通过</span></b>" # 添加 ✘ 图标

        self.comparison_result.setText(result_text) # 使用 setText 更新 QLabel

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
        # Check if an instance already exists to avoid multiple windows (optional)
        # Or simply create a new modal dialog each time
        history_dialog = HistoryWindow(self) # Pass parent for modality if desired
        history_dialog.exec_() # Show as a modal dialog

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
