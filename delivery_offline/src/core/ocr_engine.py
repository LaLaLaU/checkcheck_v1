#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CheckCheck 导管喷码自动核对系统 - OCR引擎模块（离线优先）

- 显式使用本地 ch_PP-OCRv4_rec_infer 识别模型
- 禁用 angle_cls（逐块方向分类）
- 不再回退到联网下载的默认模型
"""

import os
import sys
import cv2
import numpy as np
from typing import Dict, List, Tuple
from paddleocr import PaddleOCR


def _candidate_dirs() -> list:
    paths = []
    env_dir = os.environ.get("CHECKCHECK_OCR_MODELS")
    if env_dir:
        paths.append(env_dir)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass and os.path.isdir(meipass):
        paths.append(meipass)
    if getattr(sys, "frozen", False):
        paths.append(os.path.dirname(sys.executable))
    proj_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    paths += [proj_root, os.getcwd()]
    seen, ordered = set(), []
    for p in paths:
        if p and p not in seen:
            ordered.append(p); seen.add(p)
    return ordered


def _find_rec_model_dir() -> str:
    for base in _candidate_dirs():
        p = os.path.join(base, "ch_PP-OCRv4_rec_infer")
        if os.path.isdir(p):
            return p
    return ""


class OCREngine:
    """OCR引擎类：对裁剪区域进行识别"""

    def __init__(self, use_gpu: bool = False):
        rec_dir = _find_rec_model_dir()
        if not rec_dir:
            print("Error: local recognition model directory not found (ch_PP-OCRv4_rec_infer). OCR disabled.")
            self.ocr = None
        else:
            self.ocr = PaddleOCR(
                use_angle_cls=False,
                det=False,
                rec_model_dir=rec_dir,
                use_gpu=use_gpu,
                show_log=False
            )
            print(f"OCREngine initialized with local recognition model: {rec_dir}")

        self.confidence_threshold = 0.7

    def recognize_text(self, image: np.ndarray) -> Tuple[str, float, List]:
        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        if self.ocr is None:
            return "", 0.0, []

        result = self.ocr.ocr(image, cls=False)
        if not result or not result[0]:
            return "", 0.0, []

        texts, confidences, details = [], [], []
        for line in result[0]:
            text = line[1][0]
            conf = float(line[1][1])
            if conf >= self.confidence_threshold:
                texts.append(text)
                confidences.append(conf)
                details.append((text, conf))

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return " ".join(texts), avg_conf, details

    def process_regions(self, regions: Dict[str, Dict]) -> Dict[str, Dict]:
        result = regions.copy()
        if 'label_region' in result:
            text, conf, det = self.recognize_text(result['label_region']['image'])
            result['label_region'].update({'text': text, 'confidence': conf, 'ocr_details': det})
        if 'print_region' in result:
            text, conf, det = self.recognize_text(result['print_region']['image'])
            result['print_region'].update({'text': text, 'confidence': conf, 'ocr_details': det})
        return result

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        return cv2.filter2D(denoised, -1, kernel)

    def set_confidence_threshold(self, threshold: float) -> None:
        if 0 <= threshold <= 1:
            self.confidence_threshold = threshold


