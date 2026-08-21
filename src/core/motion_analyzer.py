"""
Analizador de Movimiento por Visión Computacional (MOG2 Background Subtractor).
Gestiona la sustracción de fondo, filtros morfológicos, máscara de cuna y medición de reposo.
"""
import cv2
import numpy as np
import time
import logging
from typing import Tuple, Optional

logger = logging.getLogger("BabyDetector.Motion")

class MotionAnalyzer:
    """
    Controla la sustracción de fondo adaptativa MOG2 y el cálculo de movimiento efectivo
    dentro del ROI de la cuna y en la caja del bebé.
    """
    def __init__(self, sensitivity: float = 0.03):
        self.sensitivity = float(sensitivity)
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=50, detectShadows=False)
        self.warmup_frames = 20
        self.last_motion_time = 0.0
        self.last_motion_ratio = 0.0
        self.smooth_motion_ratio = 0.0
        self.motion_detected = False
        self.motion_cooldown_until = 0.0

    def reset_subtractor(self):
        """Reinicia el sustractor de fondo para recalibración rápida (ej. tras cambio de ROI)."""
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=50, detectShadows=False)
        self.warmup_frames = 15
        self.smooth_motion_ratio = 0.0
        self.motion_detected = False
        self.motion_cooldown_until = 0.0

    def analyze(self, roi_crop: np.ndarray, baby_box: Optional[np.ndarray]) -> Tuple[bool, float, np.ndarray]:
        """
        Analiza el recorte de la cuna buscando cambios de píxeles con MOG2.
        Aplica filtro EMA e histéresis temporal para evitar parpadeos y dar tiempo de reposo.
        Retorna: (motion_detected, effective_motion_ratio, fg_mask)
        """
        if roi_crop is None or roi_crop.size == 0:
            self.last_motion_ratio = 0.0
            self.motion_detected = False
            return False, 0.0, np.zeros((10, 10), dtype=np.uint8)

        rh, rw = roi_crop.shape[:2]
        roi_area = float(rh * rw)
        if roi_area <= 0:
            return False, 0.0, np.zeros((10, 10), dtype=np.uint8)

        fg_mask = self.bg_subtractor.apply(roi_crop)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)

        motion_pixels = cv2.countNonZero(fg_mask)
        motion_ratio = motion_pixels / roi_area

        # Evaluar movimiento focalizado en el cuerpo del bebé si está encuadrado
        baby_motion_ratio = 0.0
        if baby_box is not None:
            bx, by, bw, bh = map(int, baby_box)
            bx1_c, by1_c = max(0, bx), max(0, by)
            bx2_c, by2_c = min(rw, bx + bw), min(rh, by + bh)

            if (bx2_c > bx1_c) and (by2_c > by1_c):
                baby_fg = fg_mask[by1_c:by2_c, bx1_c:bx2_c]
                baby_area = float((bx2_c - bx1_c) * (by2_c - by1_c))
                if baby_area > 0:
                    baby_motion_ratio = cv2.countNonZero(baby_fg) / baby_area

        raw_effective_motion = max(motion_ratio, baby_motion_ratio)
        
        # Filtro EMA para estabilizar mediciones y eliminar ruido instantáneo
        alpha = 0.35
        self.smooth_motion_ratio = alpha * raw_effective_motion + (1.0 - alpha) * self.smooth_motion_ratio
        effective_motion = self.smooth_motion_ratio
        self.last_motion_ratio = float(effective_motion)

        now = time.time()
        if self.warmup_frames > 0:
            self.warmup_frames -= 1
            self.motion_detected = False
        else:
            # Gatillo con Histéresis y Ventana de Retención (Cooldown)
            if effective_motion >= self.sensitivity:
                self.motion_detected = True
                self.last_motion_time = now
                self.motion_cooldown_until = now + 1.2
            elif now < self.motion_cooldown_until and effective_motion >= (self.sensitivity * 0.50):
                # Mantener estado de movimiento activo mientras no descienda claramente
                self.motion_detected = True
            else:
                self.motion_detected = False

        return self.motion_detected, float(effective_motion), fg_mask
