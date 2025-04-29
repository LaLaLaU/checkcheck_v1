from typing import List
import cv2
import logging

logger = logging.getLogger(__name__)

def detect_available_cameras(max_cameras_to_check: int = 10) -> List[int]:
    """
    检测系统中可用的摄像头索引。

    Args:
        max_cameras_to_check: 要检查的最大摄像头索引数。

    Returns:
        一个包含可用摄像头索引的列表。
    """
    available_indices = []
    logger.info(f"正在检测最多 {max_cameras_to_check} 个摄像头...")
    for i in range(max_cameras_to_check):
        # 尝试使用 CAP_DSHOW，这是 Windows 上常用的 API
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap is not None and cap.isOpened():
            logger.info(f"发现可用摄像头，索引: {i}")
            available_indices.append(i)
            cap.release() # 立即释放摄像头，以便主程序可以使用
            logger.debug(f"已释放摄像头索引: {i}")
        else:
            # 如果 CAP_DSHOW 失败，可以尝试其他 API 或停止
            logger.debug(f"索引 {i} 不是一个有效的摄像头。")
            if cap is not None:
                cap.release() # 确保释放
    
    if not available_indices:
         logger.warning("未检测到任何可用的摄像头。")
    else:
        logger.info(f"检测到可用摄像头索引: {available_indices}")
        
    return available_indices

if __name__ == '__main__':
    # 用于独立测试此模块
    logging.basicConfig(level=logging.INFO)
    print("正在检测可用摄像头...")
    cameras = detect_available_cameras()
    if cameras:
        print(f"找到的摄像头索引: {cameras}")
    else:
        print("未找到任何摄像头。")
