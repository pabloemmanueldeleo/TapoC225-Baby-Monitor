"""
Pruebas de verificación de rechequeo activo, expiración inercial y resolución de bloqueo.
"""
import os
import sys
import time
import unittest
import numpy as np
import cv2

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.detector import BabyDetector

import tempfile
import shutil

class TestRecheckAndExpiration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_tmpl = os.path.join(self.tmp_dir.name, "templates")
        self.tmp_neg = os.path.join(self.tmp_dir.name, "negatives")
        self.detector = BabyDetector(sensitivity=0.03, use_yolo=False, templates_dir=self.tmp_tmpl, negatives_dir=self.tmp_neg)
        self.detector.roi_enabled = False
        self.detector.template_enabled = True

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_phantom_box_does_not_persist_infinitely(self):
        """Verifica que una detección no confirmada expire tras el tiempo de reposo sin bloquearse."""
        frame = np.full((480, 640, 3), 100, dtype=np.uint8)
        
        # Simular una detección previa inicial
        self.detector._smooth_baby_box = np.array([200, 200, 80, 80], dtype=np.float32)
        # Establecer la marca de match en el pasado (hace 10 segundos)
        self.detector._last_baby_match_time = time.time() - 10.0
        self.detector._last_best_score = 0.90

        # Procesar frame vacío (sin bebé)
        motion_det, baby_det, _, info = self.detector.process_frame(frame)

        self.assertFalse(baby_det, "La detección DEBE expirar cuando no hay soporte visual tras el timeout")
        self.assertIsNone(self.detector._smooth_baby_box, "La caja suavizada debe limpiarse a None al expirar")
        self.assertIsNone(self.detector._active_baby_mask_poly, "La máscara debe limpiarse a None al expirar")

    def test_save_negative_immediately_resets_tracking(self):
        """Verifica que al vetar un falso positivo el tracking activo se reinicie de inmediato."""
        self.detector._smooth_baby_box = np.array([200, 200, 80, 80], dtype=np.float32)
        self.detector._active_baby_mask_poly = np.array([[200, 200], [280, 200], [280, 280], [200, 280]])
        self.detector._last_baby_match_time = time.time()

        dummy_crop = np.full((60, 60, 3), 200, dtype=np.uint8)
        saved = self.detector.save_negative_template_from_crop(dummy_crop, (0.01, 0.01, 0.05, 0.05))

        self.assertTrue(saved)
        self.assertIsNone(self.detector._smooth_baby_box, "El tracking debe limpiarse inmediatamente al vetar")
        self.assertIsNone(self.detector._active_baby_mask_poly, "La máscara debe limpiarse inmediatamente al vetar")

    def test_real_baby_template_takes_precedence_over_unconfirmed_area(self):
        """Verifica que si aparece un bebé real con plantilla en otra zona, el detector transicione inmediatamente."""
        # 1. Crear plantilla de bebé
        baby_tmpl = np.zeros((80, 80, 3), dtype=np.uint8)
        cv2.circle(baby_tmpl, (40, 40), 25, (220, 200, 255), -1)
        cv2.putText(baby_tmpl, "B", (30, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        self.detector.save_target_template_from_crop(baby_tmpl)

        # 2. Escena con el bebé en la izquierda (x=80, y=150)
        scene = np.full((480, 640, 3), 90, dtype=np.uint8)
        scene[150:230, 80:160] = baby_tmpl

        # Simular que el detector tenía una caja previa falsa en la derecha (x=450, y=150)
        self.detector._smooth_baby_box = np.array([450, 150, 80, 80], dtype=np.float32)
        self.detector._last_baby_match_time = time.time() - 2.0
        self.detector.template_threshold = 0.40

        motion_det, baby_det, _, info = self.detector.process_frame(scene)
        self.assertTrue(baby_det, "El detector debe reconocer al bebé real")
        self.assertIsNotNone(self.detector._smooth_baby_box)

        # La posición del box debe haberse movido a la izquierda (x < 200), no quedarse en 450
        bx = self.detector._smooth_baby_box[0]
        self.assertLess(bx, 200, f"La caja ({bx}) debe transicionar hacia el bebé real en x < 200")

if __name__ == "__main__":
    unittest.main()
