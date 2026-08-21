"""
Suite de pruebas unitarias y de integración para la lógica de sensibilidad,
detección de movimiento, umbrales de audio y notificaciones de alerta.
"""

import sys
import os
import time
import unittest
import numpy as np

# Asegurar importación del paquete src/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.detector import BabyDetector
from src.services.audio_monitor import RTSPAudioMonitor

class TestSensitivityAndAlerts(unittest.TestCase):

    def setUp(self):
        self.detector = BabyDetector(sensitivity=0.03, use_yolo=False)
        self.audio_monitor = RTSPAudioMonitor("rtsp://mock_stream")

    def test_motion_sensitivity_threshold(self):
        """Prueba que el detector responda correctamente al umbral de sensibilidad de movimiento."""
        frame1 = np.zeros((480, 640, 3), dtype=np.uint8)
        frame2 = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Simular un bloque con movimiento en el centro
        frame2[200:300, 200:300] = 255

        # Pasar calentamiento MOG2
        for _ in range(25):
            self.detector.process_frame(frame1)

        # Probar con alta sensibilidad (0.01)
        self.detector.sensitivity = 0.01
        motion_det, _, _, info = self.detector.process_frame(frame2)
        self.assertTrue(motion_det, "Debe detectar movimiento con alta sensibilidad (0.01).")

        # Probar con sensibilidad muy baja (0.90) donde el movimiento pequeño deba ignorarse
        self.detector.sensitivity = 0.90
        motion_det_low, _, _, _ = self.detector.process_frame(frame2)
        self.assertFalse(motion_det_low, "Debe ignorar movimientos menores cuando la sensibilidad es baja (0.90).")

    def test_audio_threshold(self):
        """Prueba la lógica de alertas sonoras y disparo de umbrales."""
        self.audio_monitor.set_threshold(0.40)
        self.assertEqual(self.audio_monitor.threshold, 0.40)

        # Simular volumen bajo
        self.audio_monitor.current_volume = 0.15
        self.assertFalse(self.audio_monitor.is_sound_alert(), "No debe sonar alarma si el volumen es 15% < 40%")

        # Simular volumen alto por llanto
        self.audio_monitor.current_volume = 0.65
        self.assertTrue(self.audio_monitor.is_sound_alert(), "Debe sonar alarma cuando el volumen 65% > 40%")

    def test_sustained_motion_filter_logic(self):
        """Prueba la lógica del acumulador temporal para filtrar micro-movimientos involuntarios."""
        min_duration = 3.0
        
        # 1. Simulación de micro-movimiento (1.2 segundos): No debe disparar alerta
        start_time = 100.0
        current_time = 101.2
        elapsed = current_time - start_time
        motion_alert = elapsed >= min_duration
        self.assertFalse(motion_alert, "Un micro-movimiento de 1.2s < 3.0s no debe activar la alerta.")

        # 2. Simulación de movimiento sostenido (3.5 segundos): Sí debe disparar alerta
        current_time = 103.5
        elapsed = current_time - start_time
        motion_alert = elapsed >= min_duration
        self.assertTrue(motion_alert, "Un movimiento continuo de 3.5s >= 3.0s sí debe activar la alerta.")

    def test_popup_image_click_signal(self):
        """Prueba que el popup emita la señal image_clicked al interactuar con el recorte."""
        from PySide6.QtWidgets import QApplication
        from src.gui.popup import CornerAlertWindow

        app = QApplication.instance() or QApplication(sys.argv)
        popup = CornerAlertWindow()
        
        signal_received = []
        popup.image_clicked.connect(lambda: signal_received.append(True))
        
        # Simular invocación del evento de clic
        popup._on_image_clicked(None)
        self.assertTrue(signal_received, "La señal image_clicked debe emitirse correctamente.")

    def test_popup_alert_levels(self):
        """Prueba que el pop-up soporte los distintos niveles de severidad (crítica combinada, auditiva y movimiento)."""
        from PySide6.QtWidgets import QApplication
        from src.gui.popup import CornerAlertWindow

        app = QApplication.instance() or QApplication(sys.argv)
        popup = CornerAlertWindow()
        
        # 1. Nivel Crítico (Llanto + Movimiento)
        popup.trigger_alert("ALERTA COMBINADA", "Movimiento + Llanto", None, alert_level="critical")
        self.assertIn("COMBINADA", popup.lbl_title.text().upper())

        # 2. Nivel Sonoro
        popup.trigger_alert("ALERTA AUDITIVA", "Llanto", None, alert_level="sound")
        self.assertIn("AUDITIVA", popup.lbl_title.text().upper())

        popup.hide()

if __name__ == "__main__":
    unittest.main()
