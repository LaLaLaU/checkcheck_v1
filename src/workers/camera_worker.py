import cv2
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, QThread
import logging

logger = logging.getLogger(__name__)

class CameraWorker(QObject):
    frame_ready = pyqtSignal(np.ndarray)
    error_occurred = pyqtSignal(str)
    camera_opened = pyqtSignal(bool) # Signal to indicate if camera opened successfully

    def __init__(self, camera_index=1, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = False
        self.cap = None
        logger.info(f"CameraWorker initialized with camera index: {self.camera_index}")

    def run(self):
        logger.info(f"CameraWorker thread started ({QThread.currentThreadId()}). Opening camera {self.camera_index}...")
        self._running = True
        logger.info(f"Attempting to open camera {self.camera_index}...")
        # 尝试不同的API Preference
        apis_to_try = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        for api in apis_to_try:
            self.cap = cv2.VideoCapture(self.camera_index, api)
            if self.cap.isOpened():
                logger.info(f"Successfully opened camera {self.camera_index} using API: {api}")
                self.camera_opened.emit(True)
                break
            else:
                logger.warning(f"Failed to open camera {self.camera_index} with API: {api}")
                self.cap.release() # 释放之前的尝试
                self.cap = None # 重置为 None

        if not self.cap or not self.cap.isOpened():
            error_msg = f"Error: Could not open camera with index {self.camera_index} using any available API."
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            self.camera_opened.emit(False)
            self._running = False
            logger.info("CameraWorker run loop finished. Releasing resources...")
            if self.cap and self.cap.isOpened():
                logger.info("Releasing camera capture...")
                self.cap.release()
                logger.info("Camera capture released.")
            else:
                logger.info("Camera capture was not open or already released.")
            logger.info("Emitting finished signal...")
            # self.finished.emit() # No finished signal in original code
            logger.info("Finished signal emitted. CameraWorker run() completed.")
            return

        logger.info(f"Camera {self.camera_index} opened successfully. Starting frame capture loop.")
        while self._running:
            ret, frame = self.cap.read()
            if not self._running: # Double-check after blocking read
                logger.debug("Loop condition false after cap.read()")
                break 
            if not ret:
                logger.warning(f"Warning: Could not read frame from camera {self.camera_index}. Stopping capture.")
                # Maybe emit an error signal here too?
                self.error_occurred.emit(f"无法从相机 {self.camera_index} 读取帧。")
                break # Exit loop if frame reading fails

            # Emit the raw frame
            self.frame_ready.emit(frame)

            # Add a small delay to prevent high CPU usage and allow event processing
            # Use QThread.msleep for better integration with Qt event loop
            QThread.msleep(30) # Adjust delay as needed (e.g., 30ms ~ 33fps)

            # Give the event loop a chance to process signals (like stop signal)
            # Important if frame processing takes time later.
            QThread.msleep(1) # Small sleep to yield thread

        logger.info(f"Stopping camera {self.camera_index} capture.")
        if self.cap:
            logger.info("Releasing camera capture...")
            self.cap.release()
            logger.info("Camera capture released.")
        else:
            logger.info("Camera capture was not open or already released.")
        self.cap = None # Ensure cap is None after release
        self._running = False # Ensure running flag is false
        logger.info("Emitting finished signal...")
        # self.finished.emit() # No finished signal in original code
        logger.info("Finished signal emitted. CameraWorker run() completed.")

    def stop(self):
        logger.info("CameraWorker stop() called. Setting _running to False.")
        self._running = False
        logger.info("_running is now False.")
        logger.info("CameraWorker stop() completed.")

    def is_running(self):
        return self._running

    def __del__(self):
        # Ensure camera is released if the worker object is deleted
        if self.cap and self.cap.isOpened():
            logger.warning(f"CameraWorker deleted while camera {self.camera_index} was still potentially open. Releasing.")
            self.cap.release()
