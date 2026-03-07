#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OCR处理器模块 - 封装PaddleOCR功能（离线优先）

- 显式使用本地 det/rec 模型，避免联网下载
- 关闭逐块方向分类（use_angle_cls=False）
"""

import os
import sys
import logging
import numpy as np
from paddleocr import PaddleOCR
import cv2

logger = logging.getLogger(__name__)


def _candidate_model_dirs() -> list:
    """返回可能包含OCR模型的候选根目录（按优先级）。"""
    candidates = []
    env_dir = os.environ.get("CHECKCHECK_OCR_MODELS")
    if env_dir:
        candidates.append(env_dir)

    # PyInstaller 打包提取目录
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass and os.path.isdir(meipass):
        candidates.append(meipass)

    # 可执行文件所在目录
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(exe_dir)

    # 项目根目录（src 的上上级）
    proj_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates.append(proj_root)

    # 当前工作目录
    candidates.append(os.getcwd())

    # 去重，保持顺序
    seen = set()
    ordered = []
    for p in candidates:
        if p and p not in seen:
            ordered.append(p)
            seen.add(p)
    return ordered


def _find_local_model_dirs() -> tuple:
    """查找本地 det/rec 模型目录。返回 (det_dir, rec_dir) 或 (None, None)。"""
    for base in _candidate_model_dirs():
        det_dir = os.path.join(base, "ch_PP-OCRv4_det_infer")
        rec_dir = os.path.join(base, "ch_PP-OCRv4_rec_infer")
        if os.path.isdir(det_dir) and os.path.isdir(rec_dir):
            return det_dir, rec_dir
    return None, None

def _prepare_dummy_cls_dir() -> str:
    """
    准备一个本地的“伪”cls模型目录，放置空的 inference.pdmodel 与 inference.pdiparams 文件，
    以绕过 PaddleOCR 在初始化阶段对 cls 模型的强制下载检查。
    """
    for base in _candidate_model_dirs():
        try:
            dummy_dir = os.path.join(base, "_cls_dummy_infer")
            os.makedirs(dummy_dir, exist_ok=True)
            for fname in ("inference.pdmodel", "inference.pdiparams"):
                fpath = os.path.join(dummy_dir, fname)
                if not os.path.exists(fpath):
                    with open(fpath, "wb") as _f:
                        _f.write(b"")
            return dummy_dir
        except Exception:
            continue
    # 兜底：放在当前工作目录
    fallback = os.path.join(os.getcwd(), "_cls_dummy_infer")
    os.makedirs(fallback, exist_ok=True)
    for fname in ("inference.pdmodel", "inference.pdiparams"):
        fpath = os.path.join(fallback, fname)
        if not os.path.exists(fpath):
            with open(fpath, "wb") as _f:
                _f.write(b"")
    return fallback


class PaddleOcrProcessor:
    """
    PaddleOCR处理器类，封装PaddleOCR的文本检测和识别功能
    """

    def __init__(self, use_gpu: bool = False, lang: str = "ch", use_angle_cls: bool = False):
        """
        初始化PaddleOCR处理器

        Args:
            use_gpu (bool): 是否使用GPU加速，默认False
            lang (str): 识别语言，默认"ch"（中文）
            use_angle_cls (bool): 是否使用文本方向分类，默认False（离线更稳）
        """
        logger.info("Initializing PaddleOCR processor...")
        det_dir, rec_dir = _find_local_model_dirs()
        try:
            if det_dir and rec_dir:
                logger.info(f"Using local OCR models: det={det_dir}, rec={rec_dir}")
                self.ocr_engine = PaddleOCR(
                    use_angle_cls=False,
                    det_model_dir=det_dir,
                    rec_model_dir=rec_dir,
                    cls_model_dir=_prepare_dummy_cls_dir(),
                    lang=lang,
                    use_gpu=use_gpu,
                    show_log=False
                )
            else:
                # 本地未找到则回退到默认配置（可能触发在线下载）
                logger.warning("Local OCR model directories not found. Falling back to default PaddleOCR config. This may attempt network downloads.")
                self.ocr_engine = PaddleOCR(
                    use_angle_cls=False,
                    cls_model_dir=_prepare_dummy_cls_dir(),
                    lang=lang,
                    use_gpu=use_gpu,
                    show_log=False
                )
            logger.info("PaddleOCR engine initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize PaddleOCR engine: {e}")
            raise

    def ocr(self, image, cls: bool = False):
        """
        执行OCR识别（禁用逐块方向分类）。

        Args:
            image: 图像数据（numpy数组，BGR）。
            cls (bool): 兼容参数，实际强制为 False。

        Returns:
            list: OCR结果，格式为[[box], (text, confidence)] 列表。
        """
        if image is None:
            logger.error("Cannot perform OCR on None image.")
            return None

        try:
            if isinstance(image, np.ndarray):
                import time
                start_time = time.time()
                result = self.ocr_engine.ocr(image, cls=False)
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
                texts.append(line[1][0])

        return texts

    def get_text_with_positions(self, ocr_result):
        """
        获取带位置信息的文本

        Args:
            ocr_result: OCR结果

        Returns:
            list: 包含位置信息的文本列表，格式为[(box, text, confidence), ...]
        """
        if not ocr_result or not ocr_result[0]:
            return []

        text_with_pos = []
        for line in ocr_result[0]:
            if len(line) >= 2 and isinstance(line[1], tuple) and len(line[1]) >= 2:
                box = line[0]
                text = line[1][0]
                confidence = line[1][1]
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

        result_image = image.copy()

        for line in ocr_result[0]:
            if len(line) < 2:
                continue

            box = line[0]
            if not isinstance(box, list) or len(box) != 4:
                continue

            text = line[1][0]
            confidence = line[1][1]

            box = np.array(box).astype(np.int32).reshape((-1, 1, 2))
            cv2.polylines(result_image, [box], True, (0, 255, 0), 2)

            rect = cv2.boundingRect(box)
            x, y, w, h = rect

            display_text = text
            if show_confidence:
                display_text = f"{text} ({confidence:.2f})"

            cv2.rectangle(result_image, (x, y - 20), (x + max(60, len(display_text) * 10), y), (0, 255, 0), -1)
            cv2.putText(result_image, display_text, (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        return result_image




