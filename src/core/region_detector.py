#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CheckCheck 导管喷码自动核对系统 - 区域检测模块（离线优先）

- 显式使用本地 ch_PP-OCRv4_det_infer 检测模型
- 禁用 angle_cls；不回退到联网下载
"""

import os
import sys
import cv2
import numpy as np
from typing import Tuple, Dict, List, Optional
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


def _find_det_model_dir() -> str:
    for base in _candidate_dirs():
        p = os.path.join(base, "ch_PP-OCRv4_det_infer")
        if os.path.isdir(p):
            return p
    return ""


def _prepare_dummy_infer_dir(name: str = "_dummy_infer") -> str:
    """创建包含空 inference 文件的占位目录，以阻止 PaddleOCR 下载对应模型。"""
    for base in _candidate_dirs():
        try:
            dummy = os.path.join(base, name)
            os.makedirs(dummy, exist_ok=True)
            for fname in ("inference.pdmodel", "inference.pdiparams"):
                fpath = os.path.join(dummy, fname)
                if not os.path.exists(fpath):
                    with open(fpath, "wb") as f:
                        f.write(b"")
            return dummy
        except Exception:
            continue
    fallback = os.path.join(os.getcwd(), name)
    os.makedirs(fallback, exist_ok=True)
    for fname in ("inference.pdmodel", "inference.pdiparams"):
        fpath = os.path.join(fallback, fname)
        if not os.path.exists(fpath):
            with open(fpath, "wb") as f:
                f.write(b"")
    return fallback


class RegionDetector:
    """使用 PaddleOCR 检测文本区域"""

    def __init__(self):
        print("Initializing PaddleOCR for detection (offline-first)...")

        det_dir = _find_det_model_dir()
        if not det_dir:
            print("Error: local detection model directory not found (ch_PP-OCRv4_det_infer). Detection disabled.")
            self.detector = None
        else:
            self.detector = PaddleOCR(
                det_model_dir=det_dir,
                use_angle_cls=False,
                use_gpu=False,
                rec=False,
                rec_model_dir=_prepare_dummy_infer_dir("_rec_dummy_infer"),
                cls_model_dir=_prepare_dummy_infer_dir("_cls_dummy_infer"),
                show_log=False
            )
            print(f"PaddleOCR detector initialized with local model: {det_dir}")

        # 简单的过滤参数
        self.min_textbox_area = 500
        self.max_textbox_area = 50000
        self.min_aspect_ratio = 1.5
        self.max_aspect_ratio = 20.0

        self.label_color = (0, 0, 255)
        self.print_color = (0, 255, 0)

    def detect_regions(self, image: np.ndarray) -> Dict[str, Dict]:
        if self.detector is None:
            print("PaddleOCR detector not initialized.")
            return {}

        detected_bboxes = self._detect_text_regions(image)
        if not detected_bboxes:
            return {}

        label_bbox, print_bbox = self._classify_regions(image, detected_bboxes)

        result: Dict[str, Dict] = {}
        if label_bbox:
            x, y, w, h = label_bbox
            result['label_region'] = {
                'bbox': label_bbox,
                'image': image[y:y+h, x:x+w].copy()
            }
        if print_bbox:
            x, y, w, h = print_bbox
            result['print_region'] = {
                'bbox': print_bbox,
                'image': image[y:y+h, x:x+w].copy()
            }
        return result

    def _detect_text_regions(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        img = image.copy()
        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        try:
            det_res = self.detector.ocr(img, cls=False, rec=False)
            bboxes: List[Tuple[int, int, int, int]] = []
            if det_res and det_res[0]:
                for box_coords in det_res[0]:
                    points = np.array(box_coords, dtype=np.int32)
                    x, y, w, h = cv2.boundingRect(points)
                    bboxes.append((x, y, w, h))
            return bboxes
        except Exception as e:
            print(f"Error during PaddleOCR detection: {e}")
            return []

    def _merge_overlapping_boxes(self, boxes: List[Tuple[int, int, int, int]]) -> List[Tuple[int, int, int, int]]:
        if not boxes:
            return []
        boxes = sorted(boxes, key=lambda box: box[0])
        merged = [boxes[0]]
        for box in boxes[1:]:
            x1, y1, w1, h1 = merged[-1]
            x2, y2, w2, h2 = box
            if (x1 < x2 + w2 and x2 < x1 + w1 and y1 < y2 + h2 and y2 < y1 + h1):
                x = min(x1, x2)
                y = min(y1, y2)
                w = max(x1 + w1, x2 + w2) - x
                h = max(y1 + h1, y2 + h2) - y
                merged[-1] = (x, y, w, h)
            else:
                merged.append(box)
        return merged

    def _classify_regions(self, image: np.ndarray, regions: List[Tuple[int, int, int, int]]) -> Tuple[Optional[Tuple[int, int, int, int]], Optional[Tuple[int, int, int, int]]]:
        if not regions:
            return None, None
        regions = sorted(regions, key=lambda r: r[1])  # 由上到下
        label_region = regions[0]
        print_region = regions[1] if len(regions) > 1 else None
        return label_region, print_region

    def visualize_regions(self, image: np.ndarray, regions: Dict) -> np.ndarray:
        vis = image.copy()
        lr = regions.get('label_region')
        pr = regions.get('print_region')
        if lr and 'bbox' in lr:
            x, y, w, h = lr['bbox']
            cv2.rectangle(vis, (x, y), (x + w, y + h), self.label_color, 2)
            label_text = lr.get('text', 'Label?')
            cv2.putText(vis, label_text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, self.label_color, 2)
        if pr and 'bbox' in pr:
            x, y, w, h = pr['bbox']
            cv2.rectangle(vis, (x, y), (x + w, y + h), self.print_color, 2)
            print_text = pr.get('text', 'Print?')
            cv2.putText(vis, print_text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, self.print_color, 2)
        return vis

