import sys
import os
import time
import logging

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestAppLaunch")

import unittest
from PySide6.QtWidgets import QApplication
from src.gui.pyside_app import PySideTapoApp

TEST_LAUNCH_CONFIG = os.path.join(PROJECT_ROOT, "tests", "test_launch_config.json")

class TestAppLaunch(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication(sys.argv)

    def tearDown(self):
        if os.path.exists(TEST_LAUNCH_CONFIG):
            try:
                os.remove(TEST_LAUNCH_CONFIG)
            except Exception:
                pass

    def test_launch(self):
        logger.info("Iniciando prueba automatizada de apertura de PySideTapoApp (PySide6)...")
        window = PySideTapoApp(config_path=TEST_LAUNCH_CONFIG)
        
        # Procesar eventos de interfaz y renderizado
        self.app.processEvents()

        # Verificaciones de componentes requeridos
        self.assertIsNotNone(window, "La ventana PySideTapoApp no pudo instanciarse.")
        self.assertTrue(hasattr(window, "slider_template_thresh"), "Falta el slider de similitud.")
        self.assertTrue(hasattr(window, "negatives_widget"), "Falta el widget de negativos vetados.")
        self.assertTrue(hasattr(window, "album_widget"), "Falta el álbum de fotos del bebé.")
        self.assertTrue(hasattr(window, "canvas"), "Falta el canvas de video.")
        self.assertEqual(window.slider_template_thresh.minimum(), 10, "El slider de similitud debe permitir bajar al 10%.")
        self.assertEqual(window.slider_template_thresh.maximum(), 90, "El slider de similitud debe llegar al 90%.")

        logger.info("✅ Todos los widgets principales de PySideTapoApp fueron verificados y renderizados exitosamente.")
        
        # Procesar ciclo de eventos durante 300ms
        start_t = time.time()
        while time.time() - start_t < 0.3:
            self.app.processEvents()
            time.sleep(0.05)

        window.close()
        logger.info("✅ La prueba automatizada de apertura de PySideTapoApp finalizó con éxito al 100%.")

if __name__ == "__main__":
    unittest.main()


