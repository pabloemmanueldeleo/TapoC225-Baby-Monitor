import cv2
import os
import threading
import time
import numpy as np
import logging
from typing import Optional

logger = logging.getLogger("VideoStream")

class RTSPVideoStream:
    """
    Captura RTSP multihilo. Un solo intento de conexión a la vez (lock).
    Mientras no hay stream, genera frame sintético animado.
    """
    def __init__(self, rtsp_url: Optional[str] = None):
        self.rtsp_url = rtsp_url
        self.cap: Optional[cv2.VideoCapture] = None
        self.current_frame: Optional[np.ndarray] = None
        self.running = False
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.connected = False
        self._connecting = False          # Evita múltiples hilos de conexión paralelos
        self._connect_lock = threading.Lock()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def _connect(self):
        with self._connect_lock:          # Solo un intento activo a la vez
            if self.connected:
                return
            if not self.rtsp_url or "TuClaveCamaraRTSP" in self.rtsp_url:
                logger.warning("URL RTSP no configurada o usa valores por defecto.")
                return

            # Configurar transporte RTSP vía TCP estable para Tapo C225
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
            os.environ["OPENCV_FFMPEG_LOG_LEVEL"] = "quiet"


            try:
                cv2.setLogLevel(0)
            except Exception:
                pass

            import re
            sanitized_url = re.sub(r":([^@]+)@", r":••••••••@", self.rtsp_url) if self.rtsp_url else ""
            logger.info(f"Abriendo stream RTSP (TCP sin pérdida de fotogramas): {sanitized_url}")
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if cap.isOpened():
                self.cap = cap
                self.connected = True
                logger.info("Stream RTSP abierto correctamente.")
            else:
                cap.release()
                logger.error("No se pudo abrir el stream RTSP.")

    def _generate_synthetic_frame(self) -> np.ndarray:
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(img, (20, 20), (620, 460), (40, 40, 40), 2)
        t = time.time()
        cx = int(320 + 200 * np.sin(t * 2))
        cy = int(240 + 100 * np.cos(t * 2))
        cv2.circle(img, (cx, cy), 15, (0, 200, 255), -1)
        cv2.putText(img, "Tapo C225 - Stream de Prueba / Esperando .env", (40, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, "Configure TAPO_IP y TAPO_STREAM_USER en .env", (40, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
        cv2.rectangle(img, (150, 150), (490, 380), (255, 100, 0), 2)
        cv2.putText(img, "[ Zona de Cuna / ROI ]", (160, 140),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 100, 0), 1)
        cv2.putText(img, "ZONA CUNA MONITOREADA", (100, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
        return img

    def _update_loop(self):
        retry_delay = 5.0
        last_retry = 0.0

        while self.running:
            if not self.connected and not self._connecting:
                now = time.time()
                if now - last_retry > retry_delay and self.rtsp_url:
                    last_retry = now
                    self._connecting = True
                    t = threading.Thread(target=self._connect_and_clear_flag, daemon=True)
                    t.start()

            if self.connected and self.cap:
                try:
                    if not self.cap.isOpened():
                        self.connected = False
                        continue

                    ret, frame = self.cap.read()
                    if ret and frame is not None:
                        with self.lock:
                            self.current_frame = frame
                    else:
                        self.connected = False
                        if self.cap:
                            self.cap.release()
                        time.sleep(0.5)

                except Exception as e:
                    logger.debug(f"Stream interrumpido: {e}")
                    self.connected = False
            else:
                frame = self._generate_synthetic_frame()
                with self.lock:
                    self.current_frame = frame
                time.sleep(0.03)

    def _connect_and_clear_flag(self):
        try:
            self._connect()
        finally:
            self._connecting = False

    def get_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
            return None

    def read(self) -> Optional[np.ndarray]:
        """Alias compatible con OpenCV para obtener el fotograma actual."""
        return self.get_frame()

    def stop(self):
        self.running = False
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
