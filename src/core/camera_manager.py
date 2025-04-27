import cv2
import logging
import time
from PyQt5.QtCore import QObject, pyqtSignal, QThread, pyqtSlot
import numpy as np

# Setup logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

class CameraWorker(QThread):
    """
    Handles camera operations in a separate thread to avoid blocking the GUI.
    """
    frame_ready = pyqtSignal(np.ndarray) # Emit raw NumPy array frames
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, camera_index=0, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = False
        self.cap = None

    def run(self):
        """Main loop for capturing frames from the camera."""
        self._running = True
        logger.info(f"CameraWorker thread started, trying to connect to camera index {self.camera_index}")
        try:
            # Try specifying the backend explicitly (Media Foundation is often stable on Windows)
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_MSMF)
            
            # Check if the camera opened successfully
            if not self.cap.isOpened():
                error_msg = f"Cannot open camera index {self.camera_index} with CAP_MSMF backend."
                logger.error(error_msg)
                self.error.emit(error_msg)
                self._running = False
                return # <-- Exit if cannot open

            logger.info(f"Camera {self.camera_index} opened successfully via MSMF.")
            
            # --- Camera warm-up --- 
            for _ in range(5): # Read and discard a few frames
                ret, frame = self.cap.read()
                if not ret:
                    logger.warning("Warm-up frame read failed.")
                time.sleep(0.05) # Small delay during warm-up
            # --- End warm-up ---

            logger.debug(f"Entering run loop, self._running is {self._running}") # Add log before loop

            while self._running:
                logger.debug("Attempting to read frame...")
                ret, frame = self.cap.read()
                logger.debug(f"cap.read() returned: ret={ret}") # Log return value

                if not ret:
                    logger.warning("Failed to retrieve frame (ret=False). Camera might be disconnected or blocked.")
                    time.sleep(0.1) # Wait a bit before retrying
                    continue
                if frame is None:
                    logger.warning("Retrieved frame is None. Skipping this frame.")
                    time.sleep(0.05)
                    continue

                logger.debug(f"Frame read successfully, shape: {frame.shape}. Emitting signal...")
                self.frame_ready.emit(frame)
                logger.debug("frame_ready signal emitted.")

                # Yield control slightly, adjust if needed
                time.sleep(0.01) 

        except IOError as e: # Specific error for camera opening
            logger.error(f"Camera IO Error: {e}")
            self.error.emit(str(e))
        except Exception as e: # Catch other potential errors
            logger.error(f"Unexpected error in CameraWorker run loop: {e}", exc_info=True)
            self.error.emit(f"Unexpected camera error: {e}")
        finally:
            if self.cap is not None and self.cap.isOpened():
                self.cap.release()
                logger.info(f"Camera {self.camera_index} released.")
            self.finished.emit()
            logger.info("CameraWorker thread finished.")

    def stop(self):
        """Signals the run loop to stop."""
        logger.info("Requesting CameraWorker thread stop...")
        self._running = False

class CameraManager(QObject):
    """
    Manages the camera worker and thread, providing signals for frames and errors.
    """
    frame_ready = pyqtSignal(np.ndarray)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, camera_index=0, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._worker = None
        self._thread = None # Keep a reference to QThread for management

    def is_running(self):
        """Check if the camera worker thread is active."""
        # Check if worker exists and is running its loop
        return self._worker is not None and self._worker.isRunning() and self._worker._running

    @pyqtSlot()
    def start_capture(self):
        """Start the camera capture."""
        if self.is_running():
            logger.warning("CameraWorker thread already running.")
            return

        logger.info("Starting camera capture...")
        self._worker = CameraWorker(self.camera_index)
        # Connect worker signals to manager slots/signals
        self._worker.frame_ready.connect(self._on_worker_frame_ready) # Connect to the new slot
        self._worker.error.connect(self.error)
        self._worker.finished.connect(self.finished)
        self._worker.finished.connect(self._handle_worker_finished) # Clean up

        logger.info("Starting CameraWorker thread.")
        self._worker.start()

    @pyqtSlot()
    def stop_capture(self):
        """Stop the camera capture thread safely and wait for it to finish."""
        if self._worker.isRunning():
            logger.info("Stopping CameraWorker thread.")
            self._worker.stop() # Use the stop method we defined
            # Give the thread some time to finish its current loop and release the camera
            logger.debug("Waiting for CameraWorker thread to finish after stop signal...")
            finished = self._worker.wait(1500) # Wait up to 1.5 seconds
            logger.info(f"CameraWorker thread finished waiting: {finished}")
            if not finished:
                logger.warning("CameraWorker thread did not finish gracefully after 1.5s, attempting termination.")
                self._worker.terminate() # Force terminate if it doesn't stop
        else:
            logger.info("CameraWorker thread is not running.")

    @pyqtSlot()
    def _handle_worker_finished(self):
        """Slot called when the worker thread finishes execution."""
        logger.info("CameraWorker finished signal received. Cleaning up worker reference.")
        self._worker = None # Clean up reference

    @pyqtSlot(str)
    def _handle_worker_error(self, error_message):
        """Slot called when the worker thread emits an error."""
        logger.error(f"Error signal received from CameraWorker: {error_message}")
        # Forward the error signal
        self.error.emit(error_message)

    @pyqtSlot(np.ndarray)
    def _on_worker_frame_ready(self, frame):
        """Slot to receive frame from worker and re-emit manager's signal."""
        # logger.debug(f"Manager received frame, shape: {frame.shape}. Re-emitting signal...") # Optional: Add debug log if needed
        self.frame_ready.emit(frame)

# --- Old test function, kept as reference or for standalone testing ---
def test_camera_connection_standalone(camera_index=0):
    """
    Attempt to connect to the specified camera index and capture a frame.

    Args:
        camera_index (int): The camera index to attempt to connect to, default is 0.

    Returns:
        bool: True if the connection is successful and a frame is captured, False otherwise.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Attempting to connect to camera index {camera_index}")
    # Try using the DirectShow backend for better Windows compatibility
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)

    if not cap.isOpened():
        logger.error(f"Failed to open camera index {camera_index}")
        # Try without specifying a backend
        logger.info(f"Attempting to connect to camera index {camera_index} without specifying backend")
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            logger.error(f"Failed to open camera index {camera_index} without specifying backend")
            return False
        else:
            logger.info(f"Successfully connected to camera index {camera_index} without specifying backend")

    else:
        logger.info(f"Successfully connected to camera index {camera_index} using DirectShow backend")

    # Attempt to read a frame
    ret, frame = cap.read()

    if not ret or frame is None:
        logger.error("Failed to read a frame from the camera.")
        cap.release()
        return False
    else:
        logger.info(f"Successfully read a frame, shape: {frame.shape}")
        # Optional: Display the frame for quick verification
        # cv2.imshow(f'Camera Test (Index {camera_index}) - Press Q to close', frame)
        # print("Press 'q' to close the test window...")
        # while True:
        #     if cv2.waitKey(1) & 0xFF == ord('q'):
        #         break
        # cv2.destroyAllWindows()

    # Release camera resources
    cap.release()
    logger.info("Camera resources released.")
    return True

# --- You can add new test code here to test CameraManager ---
if __name__ == '__main__':
    # This cannot be tested directly because it depends on the PyQt event loop
    # It needs to be tested within a PyQt application
    print("CameraManager needs to be tested within a PyQt application.")
    print("You can run the old standalone test function:")
    # if test_camera_connection_standalone(0):
    #     print("\nCamera 0 connection test successful!")
    # else:
    #     print("\nCamera 0 connection test failed. Please check if the camera is connected, drivers are installed, or try a different index (e.g., 1, 2...).")
