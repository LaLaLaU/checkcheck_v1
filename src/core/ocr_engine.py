#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CheckCheck 导管喷码自动核对系统 - OCR引擎模块

此模块负责使用PaddleOCR进行文字识别。
"""

import os
import cv2
import numpy as np
from typing import Dict, List, Tuple, Union, Optional
from paddleocr import PaddleOCR


class OCREngine:
    """
    OCR引擎类，用于识别图像中的文字
    """
    
    def __init__(self, use_gpu: bool = False):
        """
        初始化OCR引擎
        
        Args:
            use_gpu (bool): 是否使用GPU加速，默认为False
        """
        # 初始化PaddleOCR
        self.ocr = PaddleOCR(
            use_angle_cls=True,  # 使用方向分类器
            lang="ch",  # 中文模型
            use_gpu=use_gpu,  # 是否使用GPU
            show_log=False  # 不显示日志
        )
        
        # 配置参数
        self.confidence_threshold = 0.7  # 置信度阈值
        
    def recognize_text(self, image: np.ndarray) -> Tuple[str, float, List]:
        """
        识别图像中的文字
        
        Args:
            image (np.ndarray): 输入图像
            
        Returns:
            Tuple[str, float, List]: 识别结果，包括:
                - 识别的文本字符串
                - 平均置信度
                - 原始识别结果列表，每项包含文本和置信度
        """
        # 确保图像是BGR格式
        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        # 进行OCR识别
        result = self.ocr.ocr(image, cls=True)
        
        # 处理结果
        if not result or not result[0]:
            return "", 0.0, []
        
        # 提取文本和置信度
        texts = []
        confidences = []
        original_results = []
        
        for line in result[0]:
            text = line[1][0]
            confidence = line[1][1]
            
            # 仅保留置信度高于阈值的结果
            if confidence >= self.confidence_threshold:
                texts.append(text)
                confidences.append(confidence)
                original_results.append((text, confidence))
        
        # 计算平均置信度
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        # 合并文本
        full_text = " ".join(texts)
        
        return full_text, avg_confidence, original_results
    
    def process_regions(self, regions: Dict[str, Dict]) -> Dict[str, Dict]:
        """
        处理检测到的区域，识别每个区域中的文字
        
        Args:
            regions (Dict[str, Dict]): 检测到的区域信息
            
        Returns:
            Dict[str, Dict]: 更新后的区域信息，包含OCR结果
        """
        result = regions.copy()
        
        # 处理标牌区域
        if 'label_region' in result:
            label_image = result['label_region']['image']
            text, confidence, details = self.recognize_text(label_image)
            result['label_region'].update({
                'text': text,
                'confidence': confidence,
                'ocr_details': details
            })
        
        # 处理喷码区域
        if 'print_region' in result:
            print_image = result['print_region']['image']
            text, confidence, details = self.recognize_text(print_image)
            result['print_region'].update({
                'text': text,
                'confidence': confidence,
                'ocr_details': details
            })
        
        return result
    
    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        预处理图像以提高OCR识别效果
        
        Args:
            image (np.ndarray): 输入图像
            
        Returns:
            np.ndarray: 预处理后的图像
        """
        # 转换为灰度图
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        
        # 二值化
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 降噪
        denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)
        
        # 锐化
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(denoised, -1, kernel)
        
        return sharpened
    
    def set_confidence_threshold(self, threshold: float) -> None:
        """
        设置置信度阈值
        
        Args:
            threshold (float): 新的置信度阈值，范围为0到1
        """
        if 0 <= threshold <= 1:
            self.confidence_threshold = threshold
