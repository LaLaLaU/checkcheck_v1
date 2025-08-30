#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OCR处理器模块 - 封装PaddleOCR功能

此模块提供OCR文本检测和识别功能，使用PaddleOCR引擎。
"""

import os
import logging
import numpy as np
from paddleocr import PaddleOCR
import cv2

logger = logging.getLogger(__name__)

class PaddleOcrProcessor:
    """
    PaddleOCR处理器类，封装PaddleOCR的文本检测和识别功能
    """
    
    def __init__(self, use_gpu=False, lang="ch", use_angle_cls=True):
        """
        初始化PaddleOCR处理器
        
        Args:
            use_gpu (bool): 是否使用GPU加速，默认False
            lang (str): 识别语言，默认"ch"（中文）
            use_angle_cls (bool): 是否使用文本方向分类，默认True
        """
        logger.info("Initializing PaddleOCR processor...")
        try:
            # 创建PaddleOCR实例
            self.ocr_engine = PaddleOCR(
                use_angle_cls=use_angle_cls,
                lang=lang,
                use_gpu=use_gpu,
                show_log=False
            )
            logger.info("PaddleOCR engine initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize PaddleOCR engine: {e}")
            raise
    
    def ocr(self, image, cls=True):
        """
        执行OCR识别
        
        Args:
            image: 图像数据，可以是图像路径或numpy数组
            cls (bool): 是否使用方向分类，默认True
            
        Returns:
            list: OCR结果，格式为[[[x1,y1],[x2,y2],[x3,y3],[x4,y4]],(text,confidence)]
        """
        if image is None:
            logger.error("Cannot perform OCR on None image.")
            return None
        
        try:
            # 如果输入是numpy数组，确保它是BGR格式
            if isinstance(image, np.ndarray):
                # 执行OCR识别
                import time
                start_time = time.time()
                result = self.ocr_engine.ocr(image, cls=cls)
                end_time = time.time()
                
                logger.info(f"OCR processing completed in {(end_time - start_time) * 1000:.2f} ms")
                return result
            else:
                logger.error("Unsupported image format. Expected numpy array.")
                return None
        except Exception as e:
            logger.error(f"Error during OCR processing: {e}")
            return None
    
    def extract_text(self, ocr_result):
        """
        从OCR结果中提取纯文本
        
        Args:
            ocr_result: OCR结果
            
        Returns:
            list: 文本列表
        """
        if not ocr_result or not ocr_result[0]:
            return []
        
        texts = []
        for line in ocr_result[0]:
            if len(line) >= 2 and isinstance(line[1], tuple) and len(line[1]) >= 1:
                texts.append(line[1][0])  # 文本内容
        
        return texts
    
    def get_text_with_positions(self, ocr_result):
        """
        获取带位置信息的文本
        
        Args:
            ocr_result: OCR结果
            
        Returns:
            list: 包含位置和文本的列表，格式为[(box, text, confidence), ...]
        """
        if not ocr_result or not ocr_result[0]:
            return []
        
        text_with_pos = []
        for line in ocr_result[0]:
            if len(line) >= 2 and isinstance(line[1], tuple) and len(line[1]) >= 2:
                box = line[0]  # 文本框坐标
                text = line[1][0]  # 文本内容
                confidence = line[1][1]  # 置信度
                text_with_pos.append((box, text, confidence))
        
        return text_with_pos
    
    def draw_ocr_results(self, image, ocr_result, show_confidence=False):
        """
        在图像上绘制OCR结果
        
        Args:
            image: 原始图像
            ocr_result: OCR结果
            show_confidence (bool): 是否显示置信度
            
        Returns:
            numpy.ndarray: 绘制了OCR结果的图像
        """
        if image is None or not ocr_result or not ocr_result[0]:
            return image
        
        # 创建图像副本
        result_image = image.copy()
        
        # 绘制每个文本框和文本
        for line in ocr_result[0]:
            if len(line) < 2:
                continue
                
            box = line[0]
            if not isinstance(box, list) or len(box) != 4:
                continue
                
            text = line[1][0]
            confidence = line[1][1]
            
            # 转换为整数坐标
            box = np.array(box).astype(np.int32).reshape((-1, 1, 2))
            
            # 绘制文本框
            cv2.polylines(result_image, [box], True, (0, 255, 0), 2)
            
            # 获取文本位置
            rect = cv2.boundingRect(box)
            x, y, w, h = rect
            
            # 准备显示文本
            display_text = text
            if show_confidence:
                display_text = f"{text} ({confidence:.2f})"
                
            # 绘制文本背景
            cv2.rectangle(result_image, (x, y - 20), (x + len(display_text) * 10, y), (0, 255, 0), -1)
            
            # 绘制文本
            cv2.putText(result_image, display_text, (x, y - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        
        return result_image
