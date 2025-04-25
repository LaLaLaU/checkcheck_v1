#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CheckCheck 导管喷码自动核对系统 - 主窗口

此模块实现应用程序的主窗口，包括UI布局和基本功能。
"""

import os
import sys
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QMessageBox,
    QSplitter, QFrame, QGroupBox
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QSize


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
        
        # 设置UI
        self._setup_ui()
        
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
        image_layout.addWidget(self.image_label)
        
        # 添加到分割器
        splitter.addWidget(image_widget)
        
        # 下方区域 - 结果显示和控制按钮
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        
        # 结果显示区
        results_group = QGroupBox("识别结果")
        results_layout = QVBoxLayout(results_group)
        
        # 标牌文字结果
        self.label_text_result = QLabel("标牌文字: 等待识别...")
        results_layout.addWidget(self.label_text_result)
        
        # 喷码文字结果
        self.print_text_result = QLabel("喷码文字: 等待识别...")
        results_layout.addWidget(self.print_text_result)
        
        # 比对结果
        self.comparison_result = QLabel("比对结果: 等待比对...")
        results_layout.addWidget(self.comparison_result)
        
        # 添加结果组到底部布局
        bottom_layout.addWidget(results_group)
        
        # 控制按钮区域
        buttons_layout = QHBoxLayout()
        
        # 上传图像按钮
        self.upload_button = QPushButton("上传图像")
        self.upload_button.clicked.connect(self.on_upload_image)
        buttons_layout.addWidget(self.upload_button)
        
        # 开始识别按钮
        self.recognize_button = QPushButton("开始识别")
        self.recognize_button.clicked.connect(self.on_start_recognition)
        self.recognize_button.setEnabled(False)  # 初始禁用，直到上传图像
        buttons_layout.addWidget(self.recognize_button)
        
        # 设置按钮
        self.settings_button = QPushButton("设置")
        self.settings_button.clicked.connect(self.on_open_settings)
        buttons_layout.addWidget(self.settings_button)
        
        # 历史记录按钮
        self.history_button = QPushButton("历史记录")
        self.history_button.clicked.connect(self.on_open_history)
        buttons_layout.addWidget(self.history_button)
        
        # 添加按钮布局到底部布局
        bottom_layout.addLayout(buttons_layout)
        
        # 添加到分割器
        splitter.addWidget(bottom_widget)
        
        # 设置分割器初始大小
        splitter.setSizes([600, 200])
    
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
        # 这里暂时只显示一个消息框，后续会实现实际的OCR识别功能
        QMessageBox.information(
            self, 
            "信息", 
            f"将对图像 {os.path.basename(self.image_path)} 进行OCR识别\n"
            "此功能将在后续阶段实现"
        )
    
    def on_open_settings(self):
        """
        处理打开设置按钮点击事件
        """
        QMessageBox.information(
            self, 
            "信息", 
            "设置功能将在后续阶段实现"
        )
    
    def on_open_history(self):
        """
        处理打开历史记录按钮点击事件
        """
        QMessageBox.information(
            self, 
            "信息", 
            "历史记录功能将在后续阶段实现"
        )
    
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
