#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CheckCheck 导管喷码自动核对系统 - 区域检测模块

此模块负责自动检测图像中的标牌区域和喷码区域。
"""

import cv2
import numpy as np
from typing import Tuple, Dict, List, Optional
from paddleocr import PaddleOCR # Import PaddleOCR

class RegionDetector:
    """
    使用 PaddleOCR 检测器自动检测图像中的标牌区域和喷码区域
    """
    def __init__(self):
        """
        初始化区域检测器，使用PaddleOCR进行检测
        """
        print("Initializing PaddleOCR for detection...")
        # 初始化 PaddleOCR，仅用于检测
        # lang='ch' 支持中文和英文数字
        # rec=False 禁用识别模块
        # use_angle_cls=False 禁用角度分类
        # use_gpu=False 暂时禁用GPU，确保兼容性
        try:
            self.detector = PaddleOCR(lang='ch', use_angle_cls=False, use_gpu=False, rec=False, show_log=False)
            print("PaddleOCR detector initialized successfully.")
        except Exception as e:
            print(f"Error initializing PaddleOCR detector: {e}")
            self.detector = None

        # 可配置参数
        self.min_textbox_area = 500   # 最终文本框的最小面积
        self.max_textbox_area = 50000 # 最终文本框的最大面积
        self.min_aspect_ratio = 1.5   # 最终文本框的最小长宽比
        self.max_aspect_ratio = 20.0  # 最终文本框的最大长宽比
        
        # 可视化颜色
        self.label_color = (0, 0, 255)  # Red for label
        self.print_color = (0, 255, 0)  # Green for print

    def detect_regions(self, image: np.ndarray) -> Dict[str, Dict]:
        """
        检测图像中的标牌区域和喷码区域

        Args:
            image (np.ndarray): 输入图像

        Returns:
            Dict[str, Dict]: 包含检测到的区域信息，格式为：
                {
                    'label_region': {
                        'bbox': (x, y, w, h),
                        'image': 裁剪后的图像
                    },
                    'print_region': {
                        'bbox': (x, y, w, h),
                        'image': 裁剪后的图像
                    }
                }
        """
        if self.detector is None:
            print("PaddleOCR detector not initialized.")
            return {}

        # 使用PaddleOCR检测文本区域
        detected_bboxes = self._detect_text_regions(image)

        # 如果未检测到区域，返回空结果
        if not detected_bboxes:
            return {}

        # 对检测到的区域进行分类（标牌区域和喷码区域）
        label_bbox, print_bbox = self._classify_regions(image, detected_bboxes)

        # 返回结果
        result = {}
        if label_bbox:
            x, y, w, h = label_bbox
            result['label_region'] = {
                'bbox': label_bbox,
                'image': image[y:y+h, x:x+w].copy() # Use copy to avoid issues
            }

        if print_bbox:
            x, y, w, h = print_bbox
            result['print_region'] = {
                'bbox': print_bbox,
                'image': image[y:y+h, x:x+w].copy()
            }

        return result

    def _detect_text_regions(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        使用PaddleOCR检测器检测文本区域边界框

        Args:
            image (np.ndarray): 输入图像 (应为BGR格式)

        Returns:
            List[Tuple[int, int, int, int]]: 检测到的区域列表，每个区域为(x, y, w, h)
        """
        if self.detector is None:
            return []

        # PaddleOCR 需要 BGR 格式图像
        # 确保输入是 BGR
        img_for_detection = image.copy()
        if len(img_for_detection.shape) == 2: # 如果是灰度图，转为 BGR
            img_for_detection = cv2.cvtColor(img_for_detection, cv2.COLOR_GRAY2BGR)
        elif img_for_detection.shape[2] == 4: # 如果是 BGRA，转为 BGR
            img_for_detection = cv2.cvtColor(img_for_detection, cv2.COLOR_BGRA2BGR)

        try:
            # 执行检测
            # det_res 是一个列表，包含检测到的所有文本框信息
            # 每个文本框信息是一个包含四个顶点坐标的列表：[[[x1, y1], [x2, y2], [x3, y3], [x4, y4]], ...]
            det_res = self.detector.ocr(img_for_detection, cls=False, rec=False)

            bboxes = []
            if det_res and det_res[0]: # 检查是否有检测结果
                 for box_coords in det_res[0]:
                    # box_coords is like [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
                    # 将四个顶点坐标转换为水平边界框 (x, y, w, h)
                    points = np.array(box_coords, dtype=np.int32)
                    x, y, w, h = cv2.boundingRect(points)
                    bboxes.append((x, y, w, h))
            return bboxes
        except Exception as e:
            print(f"Error during PaddleOCR detection: {e}")
            return []

    def _merge_overlapping_boxes(self, boxes: List[Tuple[int, int, int, int]]) -> List[Tuple[int, int, int, int]]:
        """
        合并重叠的矩形框 (暂时可能不需要，因为PaddleOCR检测通常是行级别的)
        """
        if not boxes:
            return []
        
        # 按照x坐标排序
        boxes = sorted(boxes, key=lambda box: box[0])
        
        merged_boxes = [boxes[0]]
        
        for box in boxes[1:]:
            prev_box = merged_boxes[-1]
            
            # 检查是否有重叠
            # 两个矩形重叠的条件：一个矩形的左边界小于另一个矩形的右边界，且一个矩形的上边界小于另一个矩形的下边界
            if (prev_box[0] < box[0] + box[2] and 
                box[0] < prev_box[0] + prev_box[2] and 
                prev_box[1] < box[1] + box[3] and 
                box[1] < prev_box[1] + prev_box[3]):
                
                # 计算合并后的矩形
                x = min(prev_box[0], box[0])
                y = min(prev_box[1], box[1])
                w = max(prev_box[0] + prev_box[2], box[0] + box[2]) - x
                h = max(prev_box[1] + prev_box[3], box[1] + box[3]) - y
                
                # 更新最后一个矩形
                merged_boxes[-1] = (x, y, w, h)
            else:
                # 如果没有重叠，添加新的矩形
                merged_boxes.append(box)
        
        return merged_boxes
    
    def _classify_regions(self, image: np.ndarray, regions: List[Tuple[int, int, int, int]]) -> Tuple[Optional[Tuple[int, int, int, int]], Optional[Tuple[int, int, int, int]]]:
        """
        对检测到的区域进行分类，识别哪个是标牌区域，哪个是喷码区域
        (修改：基于位置进行初步分配，而非面积)
        
        Args:
            image (np.ndarray): 原始图像
            regions (List[Tuple[int, int, int, int]]): 检测到的区域列表 (应为合并后的)
            
        Returns:
            Tuple[Optional[Tuple[int, int, int, int]], Optional[Tuple[int, int, int, int]]]: 
                初步分配的标牌区域和喷码区域的坐标，如果未检测到足够区域则为None
        """
        if not regions:
            return None, None
        
        # 按Y坐标（区域顶部）从上到下排序
        regions = sorted(regions, key=lambda r: r[1])
        
        # 初步分配：顶部区域为标牌，次顶部区域为喷码
        label_region = regions[0]
        print_region = regions[1] if len(regions) > 1 else None
        
        # 注意：这仍然是一个简化的假设，后续可能需要更复杂的逻辑
        # 例如，基于文本内容、相对位置关系、尺寸比例等进行判断
        
        return label_region, print_region
    
    def visualize_regions(self, image: np.ndarray, regions: Dict) -> np.ndarray:
        """
        在图像上可视化检测到的区域和识别结果（如果提供）

        Args:
            image (np.ndarray): 原始图像
            regions (Dict): 检测和识别结果，格式同 process_image 返回值中的 'regions'

        Returns:
            np.ndarray: 可视化后的图像
        """
        vis_image = image.copy()

        label_region_info = regions.get('label_region')
        print_region_info = regions.get('print_region')

        if label_region_info and 'bbox' in label_region_info:
            x, y, w, h = label_region_info['bbox']
            cv2.rectangle(vis_image, (x, y), (x + w, y + h), self.label_color, 2)
            label_text = label_region_info.get('text', 'Label?') # Get text if available
            cv2.putText(vis_image, label_text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, self.label_color, 2)

        if print_region_info and 'bbox' in print_region_info:
            x, y, w, h = print_region_info['bbox']
            cv2.rectangle(vis_image, (x, y), (x + w, y + h), self.print_color, 2)
            print_text = print_region_info.get('text', 'Print?') # Get text if available
            cv2.putText(vis_image, print_text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, self.print_color, 2)

        return vis_image
