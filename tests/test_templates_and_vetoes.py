import os
import sys
import unittest
import cv2
import numpy as np

sys.path.insert(0, os.path.abspath("."))
from src.core.detector import BabyDetector

class TestTemplatesAndVetoes(unittest.TestCase):
    def setUp(self):
        self.detector = BabyDetector(use_yolo=False)
        self.detector.roi_enabled = False
        self.detector.template_enabled = True

    def test_negative_templates_are_strictly_rejected(self):
        """Verifica que cada uno de los objetos vetados sea rechazado por el filtro de negativos."""
        neg_dir = os.path.abspath("templates_negatives")
        if not os.path.exists(neg_dir):
            self.skipTest("No se encontró la carpeta templates_negatives")

        neg_files = [f for f in os.listdir(neg_dir) if f.lower().endswith((".jpg", ".png", ".jpeg"))]
        if not neg_files:
            self.skipTest("No hay archivos negativos locales en templates_negatives/")

        for fname in neg_files:
            fpath = os.path.join(neg_dir, fname)
            img = cv2.imread(fpath)
            self.assertIsNotNone(img, f"No se pudo cargar el negativo: {fname}")

            # Probar función directa _is_patch_negative
            is_neg = self.detector._is_patch_negative(img, None, None, 0.50)
            self.assertTrue(is_neg, f"El objeto vetado {fname} DEBE ser identificado como negativo por _is_patch_negative")

    def test_positive_templates_are_recognized(self):
        """Verifica que las fotos reales del bebé sean reconocidas correctamente cuando se presentan en pantalla."""
        pos_dir = os.path.abspath("templates")
        if not os.path.exists(pos_dir):
            self.skipTest("No se encontró la carpeta templates")

        pos_files = [f for f in os.listdir(pos_dir) if f.lower().endswith((".jpg", ".png", ".jpeg"))]
        if not pos_files:
            self.skipTest("No hay fotos locales del usuario en templates/")

        recognized_count = 0
        self.detector.yolo.enabled = False  # Aislar la validación de plantillas fotográficas
        for fname in pos_files[:4]:  # Probar fotos principales del bebé
            fpath = os.path.join(pos_dir, fname)
            img = cv2.imread(fpath)
            if img is None:
                continue

            scene = np.full((600, 800, 3), 120, dtype=np.uint8)
            h, w = img.shape[:2]
            # Incrustar en el centro de la escena
            sy, sx = 200, 250
            scene[sy:sy+h, sx:sx+w] = img

            self.detector._smooth_baby_box = None
            self.detector._last_baby_match_time = 0.0
            self.detector._last_active_baby_anchor = None
            self.detector.frame_count = 1
            self.detector.template_threshold = 0.45

            motion_det, baby_det, _, info = self.detector.process_frame(scene)
            if baby_det:
                recognized_count += 1

        self.assertGreater(recognized_count, 0, "Al menos una foto real del bebé debe ser reconocida positivamente en la escena")

    def test_discrimination_between_baby_and_pillow(self):
        """Verifica que en una escena con una almohada vetada y un bebé, la detección elija al bebé y no a la almohada."""
        neg_dir = os.path.abspath("templates_negatives")
        pos_dir = os.path.abspath("templates")

        neg_files = [f for f in os.listdir(neg_dir) if f.lower().endswith((".jpg", ".png", ".jpeg"))]
        pos_files = [f for f in os.listdir(pos_dir) if f.lower().endswith((".jpg", ".png", ".jpeg"))]

        if not neg_files or not pos_files:
            self.skipTest("Faltan archivos de prueba positivos o negativos")

        neg_img = cv2.imread(os.path.join(neg_dir, neg_files[0]))
        pos_img = cv2.imread(os.path.join(pos_dir, pos_files[0]))

        scene = np.full((600, 800, 3), 100, dtype=np.uint8)
        
        # Colocar almohada vetada a la izquierda (x=50)
        nh, nw = neg_img.shape[:2]
        scene[150:150+nh, 50:50+nw] = neg_img

        # Colocar bebé a la derecha (x=450)
        ph, pw = pos_img.shape[:2]
        scene[150:150+ph, 450:450+pw] = pos_img

        self.detector._smooth_baby_box = None
        self.detector._last_baby_match_time = 0.0
        self.detector._last_active_baby_anchor = None
        self.detector.template_threshold = 0.45
        self.detector.frame_count = 1

        motion_det, baby_det, _, info = self.detector.process_frame(scene)
        self.assertTrue(baby_det, "El bebé debe ser detectado en la escena compuesta")

        # Verificar que la caja de detección esté sobre el bebé (x >= 350) y NO sobre la almohada (x < 250)
        smooth_box = getattr(self.detector, "_smooth_baby_box", None)
        self.assertIsNotNone(smooth_box, "Debe existir un recuadro de detección")
        bx, by, bw, bh = smooth_box
        self.assertGreater(bx, 250, f"La caja de detección ({bx}, {by}) debe estar sobre el bebé (x > 250) y no sobre la almohada!")

    def test_deduplication_of_positives_and_negatives(self):
        """Verifica que las plantillas idénticas o muy similares no se dupliquen en las galerías."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            self.detector.templates.templates_dir = tmpdir
            self.detector.templates.negatives_dir = os.path.join(tmpdir, "negatives")
            self.detector.templates.target_templates = []
            self.detector.templates.negative_templates = []

            sample_crop = np.full((100, 100, 3), 150, dtype=np.uint8)
            cv2.circle(sample_crop, (50, 50), 30, (200, 50, 100), -1)

            # 1. Guardar primera vez
            self.detector.save_target_template_from_crop(sample_crop)
            self.assertEqual(len(self.detector.target_templates), 1)

            # 2. Intentar guardar el mismo recorte (o con leve ruido)
            noisy_crop = sample_crop.copy()
            noisy_crop[0:5, 0:5] = 155
            self.detector.save_target_template_from_crop(noisy_crop)
            self.assertEqual(len(self.detector.target_templates), 1, "No debe duplicar recortes similares en el álbum positivo")

            # 3. Guardar en negativos
            self.detector.save_negative_template_from_crop(sample_crop)
            self.assertEqual(len(self.detector.negative_templates), 1)

            # 4. Intentar guardar negativo duplicado
            self.detector.save_negative_template_from_crop(noisy_crop)
            self.assertEqual(len(self.detector.negative_templates), 1, "No debe duplicar recortes similares en negativos vetados")

            # 5. El positivo en conflicto debió haber sido eliminado
            self.assertEqual(len(self.detector.target_templates), 0, "Un negativo vetado idéntico debe purgar el positivo en conflicto")

if __name__ == "__main__":
    unittest.main()
