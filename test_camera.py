#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试摄像头初始化逻辑
"""
import cv2
import time
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_camera_priority():
    """测试优先检查索引1的摄像头，如果不可用则扫描其他摄像头"""
    logger.info("开始测试摄像头优先级逻辑")
    available_cameras = []
    
    # 1. 优先检查索引1
    logger.info("优先检查索引1...")
    try:
        cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
        if cap is not None and cap.isOpened():
            logger.info("摄像头索引1可用")
            available_cameras.append(1)
            # 显示摄像头画面
            logger.info("显示摄像头1画面，按Q退出")
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                cv2.imshow('Camera 1', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            cap.release()
            cv2.destroyAllWindows()
        else:
            logger.info("摄像头索引1不可用")
            if cap is not None:
                cap.release()
            # 如果索引1不可用，扫描其他摄像头
            scan_other_cameras()
    except Exception as e:
        logger.error(f"检查摄像头索引1时出错: {e}")
        # 出错时扫描其他摄像头
        scan_other_cameras()

def scan_other_cameras():
    """扫描其他摄像头（0, 2, 3, 4）"""
    logger.info("扫描其他摄像头...")
    indices_to_check = [0, 2, 3, 4]
    available_cameras = []
    
    for index in indices_to_check:
        logger.info(f"检查摄像头索引 {index}...")
        try:
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if cap is not None and cap.isOpened():
                logger.info(f"摄像头索引 {index} 可用")
                available_cameras.append(index)
                cap.release()
            elif cap is not None:
                cap.release()
        except Exception as e:
            logger.error(f"检查摄像头索引 {index} 时出错: {e}")
    
    logger.info(f"可用摄像头: {available_cameras}")
    
    # 如果有可用摄像头，显示第一个
    if available_cameras:
        selected_index = available_cameras[0]
        try:
            logger.info(f"显示摄像头 {selected_index} 画面，按Q退出")
            cap = cv2.VideoCapture(selected_index, cv2.CAP_DSHOW)
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                cv2.imshow(f'Camera {selected_index}', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            cap.release()
            cv2.destroyAllWindows()
        except Exception as e:
            logger.error(f"显示摄像头 {selected_index} 画面时出错: {e}")
    else:
        logger.warning("未检测到可用摄像头")

if __name__ == "__main__":
    test_camera_priority()
