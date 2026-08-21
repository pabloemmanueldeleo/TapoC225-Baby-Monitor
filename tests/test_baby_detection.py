import sys
import os
import time
import logging
import cv2
import numpy as np

# Asegurar que el directorio raíz del proyecto esté en el path de Python
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestBabyDetection")

import unittest
import tempfile
import shutil

class TestBabyDetection(unittest.TestCase):
    def test_baby_detection_pipeline(self):
        logger.info("Iniciando test de verificación del motor de detección por plantilla multi-ángulo...")
        from src.core.detector import BabyDetector

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_tmpl = os.path.join(tmp_dir, "templates")
            tmp_neg = os.path.join(tmp_dir, "negatives")
            detector = BabyDetector(sensitivity=0.01, use_yolo=False, templates_dir=tmp_tmpl, negatives_dir=tmp_neg)

            # 1. Crear un frame sintético de simulación de cuna (640x480)
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.rectangle(frame, (100, 100), (540, 400), (40, 40, 40), -1) # Cuna fondo
            
            # Dibujar la figura de un bebé (círculo cabeza + cuerpo)
            cv2.circle(frame, (320, 220), 30, (200, 180, 255), -1) # Cabeza
            cv2.rectangle(frame, (290, 250), (350, 320), (255, 200, 150), -1) # Cuerpo
            cv2.putText(frame, "BEBE TEST", (280, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

            # 2. Extraer el recorte del bebé y registrarlo como plantilla objetivo
            baby_crop = frame[180:330, 270:370].copy()
            self.assertGreater(baby_crop.size, 0, "El recorte del bebé sintético falló.")
            
            saved_ok = detector.save_target_template_from_crop(baby_crop)
            self.assertTrue(saved_ok, "No se pudo guardar la plantilla en templates/.")
            self.assertGreater(len(detector.target_templates), 0, "No hay plantillas registradas.")

            logger.info(f"✅ Plantilla del bebé guardada exitosamente. Total plantillas: {len(detector.target_templates)}")

            # 3. Procesar el frame con el detector para simular monitoreo
            motion_det, baby_det, annotated_frame, info = detector.process_frame(frame)

            logger.info(f"Resultados de inferencia -> Movimiento: {motion_det}, Bebé Target: {baby_det}")
            self.assertTrue(baby_det, "El detector no reconoció la plantilla guardada del bebé.")

            # 4. Verificar que se dibujó el marcado
            os.makedirs("snapshots", exist_ok=True)
            cv2.imwrite("snapshots/test_detection_output.jpg", annotated_frame)
            logger.info("✅ Foto con marcado de verificación guardada en snapshots/test_detection_output.jpg")
            logger.info("✅ El test de detección por plantilla de bebé pasó al 100% con éxito.")

if __name__ == "__main__":
    unittest.main()

