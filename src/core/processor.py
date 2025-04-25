#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CheckCheck 导管喷码自动核对系统 - 图像处理器

此模块整合了区域检测、OCR识别和文本比对功能，提供完整的图像处理流程。
"""

import cv2
import numpy as np
from typing import Dict, Tuple, Optional

from src.core.region_detector import RegionDetector
from src.core.ocr_engine import OCREngine
from src.core.text_comparator import TextComparator


class ImageProcessor:
    """
    图像处理器类，整合区域检测、OCR识别和文本比对功能
    """
    
    def __init__(self, use_gpu: bool = False):
        """
        初始化图像处理器
        
        Args:
            use_gpu (bool): 是否使用GPU加速OCR，默认为False
        """
        # 初始化各个组件
        self.region_detector = RegionDetector()
        self.ocr_engine = OCREngine(use_gpu=use_gpu)
        self.text_comparator = TextComparator()
        
    def process_image(self, image: np.ndarray) -> Dict:
        """
        处理图像，执行完整的检测、识别和比对流程
        
        Args:
            image (np.ndarray): 输入图像
            
        Returns:
            Dict: 处理结果，包括：
                - regions: 检测到的区域信息
                - label_text: 标牌文字
                - print_text: 喷码文字
                - comparison: 比对结果
                - visualized_image: 可视化后的图像
        """
        # 检测区域
        regions = self.region_detector.detect_regions(image)
        
        # 如果未检测到区域，返回空结果
        if not regions:
            return {
                'regions': {},
                'label_text': "",
                'print_text': "",
                'comparison': {
                    'similarity': 0.0,
                    'is_match': False,
                    'diff_details': []
                },
                'visualized_image': image
            }
        
        # OCR识别
        regions = self.ocr_engine.process_regions(regions)
        
        # 提取文本
        label_text = regions.get('label_region', {}).get('text', "")
        print_text = regions.get('print_region', {}).get('text', "")
        
        # 文本比对
        comparison = self.text_comparator.compare_texts(label_text, print_text)
        
        # 可视化结果
        visualized_image = self.region_detector.visualize_regions(image, regions)
        
        return {
            'regions': regions,
            'label_text': label_text,
            'print_text': print_text,
            'comparison': comparison,
            'visualized_image': visualized_image
        }
    
    def save_result(self, result: Dict, output_path: str) -> None:
        """
        保存处理结果
        
        Args:
            result (Dict): 处理结果
            output_path (str): 输出路径
        """
        # 保存可视化图像
        if 'visualized_image' in result:
            cv2.imwrite(output_path, result['visualized_image'])
    
    def set_similarity_threshold(self, threshold: float) -> None:
        """
        设置相似度阈值
        
        Args:
            threshold (float): 新的相似度阈值，范围为0到1
        """
        self.text_comparator.set_similarity_threshold(threshold)
    
    def set_confidence_threshold(self, threshold: float) -> None:
        """
        设置OCR置信度阈值
        
        Args:
            threshold (float): 新的置信度阈值，范围为0到1
        """
        self.ocr_engine.set_confidence_threshold(threshold)
