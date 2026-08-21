# =====================================================================
#  SUITE DE PRUEBAS DE PRECISIÓN Y REGRESIÓN DE IA - MONITOR TAPO C225
# =====================================================================
#  Instrucciones:
#  Coloca tus 5 fotos limpias (sin marcas ni recuadros dibujados) en tests/
#
#  1. test_scene_1_baby_sleeping.jpg -> Bebé durmiendo tranquilo en la cuna
#  2. test_scene_2_baby_moving.jpg   -> Bebé moviéndose / pataleando
#  3. test_scene_3_baby_mother.jpg   -> Bebé junto a mamá/adulto
#  4. test_scene_4_empty_crib.jpg    -> Cuna vacía (Sin bebé)
#  5. test_scene_5_night_vision.jpg   -> Visión nocturna (Infrarrojo)
# =====================================================================

import os
import sys
import time
import cv2
import numpy as np


sys.path.insert(0, os.path.abspath("."))
from src.core.detector import BabyDetector

import unittest

class TestDetectionPrecision(unittest.TestCase):
    def test_precision_suite(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            detector = BabyDetector(sensitivity=0.03, use_yolo=False)
            detector.templates.templates_dir = tmpdir
            detector.templates.negatives_dir = os.path.join(tmpdir, "negatives")
            detector.templates.target_templates = []
            detector.templates.negative_templates = []
            
            # Probar con frame sintético de cuna con bebé simulado
            frame_baby = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.rectangle(frame_baby, (100, 100), (540, 400), (40, 40, 40), -1)
            cv2.circle(frame_baby, (320, 220), 30, (200, 180, 255), -1)
            cv2.rectangle(frame_baby, (290, 250), (350, 320), (255, 200, 150), -1)
            
            # Registrar recorte centrado en el bebé sintético
            baby_crop = frame_baby[190:310, 290:350].copy()
            detector.save_target_template_from_crop(baby_crop)
            detector.template_threshold = 0.45
            
            motion_det, baby_det, annotated, info = detector.process_frame(frame_baby)
            self.assertTrue(baby_det, "El bebé sintético debe ser detectado")

            # Probar con frame sintético de cuna vacía
            frame_empty = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.rectangle(frame_empty, (100, 100), (540, 400), (40, 40, 40), -1)
            
            detector._smooth_baby_box = None
            detector._last_baby_match_time = 0.0
            detector.frame_count = 1
            motion_empty, baby_empty, _, _ = detector.process_frame(frame_empty)
            self.assertFalse(baby_empty, "En una cuna vacía no debe detectarse bebé")

if __name__ == "__main__":
    unittest.main()

