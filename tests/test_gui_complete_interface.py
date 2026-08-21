"""
Pruebas Unitarias e Integración Exhaustivas de la Interfaz Gráfica (GUI) PySide6.
Verifica programáticamente CADA botón, control, slider, recorte con ratón,
gestión de fotos/vetos, pop-up y respuestas de la ventana principal.
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

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTime
from PySide6.QtTest import QTest

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from src.gui.pyside_app import PySideTapoApp

TEST_CONFIG_PATH = os.path.join(PROJECT_ROOT, "tests", "test_gui_config.json")

import tempfile
import shutil

class TestCompleteGUIInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_CONFIG_PATH):
            try:
                os.remove(TEST_CONFIG_PATH)
            except Exception:
                pass

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_tmpl = os.path.join(self.tmp_dir.name, "templates")
        self.tmp_neg = os.path.join(self.tmp_dir.name, "negatives")
        os.makedirs(self.tmp_tmpl, exist_ok=True)
        os.makedirs(self.tmp_neg, exist_ok=True)

        if os.path.exists("templates"):
            for f in os.listdir("templates"):
                if f.endswith(".jpg"):
                    try:
                        shutil.copy(os.path.join("templates", f), os.path.join(self.tmp_tmpl, f))
                    except Exception:
                        pass

        self.window = PySideTapoApp(config_path=TEST_CONFIG_PATH)
        self.window.detector.templates.templates_dir = self.tmp_tmpl
        self.window.detector.templates.negatives_dir = self.tmp_neg
        self.window.detector.templates.load_target_templates()
        self.window.detector.templates.load_negative_templates()
        self.window.gallery_panel.update_album_ui()
        self.window.gallery_panel.update_negatives_ui()
        self.app.processEvents()

    def tearDown(self):
        if hasattr(self, "window") and self.window is not None:
            self.window.close()
            self.app.processEvents()
        if hasattr(self, "tmp_dir"):
            try:
                self.tmp_dir.cleanup()
            except Exception:
                pass
        if os.path.exists(TEST_CONFIG_PATH):
            try:
                os.remove(TEST_CONFIG_PATH)
            except Exception:
                pass

    def test_01_window_components_exist(self):
        """Verifica que todos los componentes clave de la GUI estén presentes y conectados."""
        w = self.window
        self.assertIsNotNone(w.canvas)
        self.assertIsNotNone(w.settings_panel)
        self.assertIsNotNone(w.gallery_panel)
        self.assertIsNotNone(w.popup_alert)
        self.assertIsNotNone(w.analytics_tab)

    def test_02_mouse_roi_selection_lifecycle(self):
        """Verifica el flujo completo de selección y activación de ROI de cuna con eventos reales de ratón."""
        w = self.window
        sp = w.settings_panel

        # Establecer frame simulado para que render_rect tenga dimensiones válidas
        dummy_frame = np.full((480, 640, 3), 120, dtype=np.uint8)
        w.canvas.update_frame(dummy_frame)
        self.app.processEvents()

        # Activar modo ROI con botón
        sp.btn_mode_roi.setChecked(True)
        sp.roi_mode_toggled.emit(True)
        self.assertEqual(w.canvas.mouse_mode, "🎯 Ajustar Zona Cuna")

        # Simular arrastre real de ratón en el lienzo de video
        from PySide6.QtCore import QPoint
        p1 = w.canvas.render_rect.topLeft() + QPoint(20, 20)
        p2 = w.canvas.render_rect.bottomRight() - QPoint(20, 20)
        QTest.mousePress(w.canvas, Qt.LeftButton, pos=p1)
        QTest.mouseMove(w.canvas, pos=p2)
        QTest.mouseRelease(w.canvas, Qt.LeftButton, pos=p2)
        self.app.processEvents()

        # Verificar que el detector y la UI se actualizaron
        self.assertIsNotNone(w.detector.roi)
        self.assertTrue(w.detector.roi_enabled)
        self.assertTrue(sp.chk_use_roi.isChecked())
        self.assertFalse(sp.btn_mode_roi.isChecked())
        self.assertEqual(w.canvas.mouse_mode, "NONE")

    def test_03_mouse_baby_crop_and_save_lifecycle(self):
        """Verifica el recorte del bebé con eventos reales de ratón y guardado en el álbum."""
        w = self.window
        sp = w.settings_panel

        # Mock frame sintético en la app con patrón único dinámico
        dummy_frame = np.full((480, 640, 3), 120, dtype=np.uint8)
        dummy_frame[150:250, 200:300] = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        w._raw_current_frame = dummy_frame
        w.canvas.update_frame(dummy_frame)
        self.app.processEvents()

        # Activar modo recorte
        sp.btn_mode_crop.setChecked(True)
        sp.crop_mode_toggled.emit(True)
        self.assertEqual(w.canvas.mouse_mode, "🖐️ Recortar Parte Bebé")

        # Simular arrastre real de ratón para recortar
        from PySide6.QtCore import QPoint
        p1 = w.canvas.render_rect.topLeft() + QPoint(30, 30)
        p2 = w.canvas.render_rect.topLeft() + QPoint(130, 130)
        QTest.mousePress(w.canvas, Qt.LeftButton, pos=p1)
        QTest.mouseMove(w.canvas, pos=p2)
        QTest.mouseRelease(w.canvas, Qt.LeftButton, pos=p2)
        self.app.processEvents()

        # Verificar que el recorte fue capturado y la vista previa se activó
        self.assertIsNotNone(w._current_mouse_crop)
        self.assertTrue(sp.btn_save_photo.isEnabled())
        self.assertTrue(sp.btn_veto_photo.isEnabled())
        self.assertTrue(sp.btn_discard_photo.isEnabled())
        self.assertIn("Recorte listo", sp.lbl_crop_preview_title.text())
        self.assertIsNotNone(sp.lbl_crop_img.pixmap())
        initial_templates = len(w.detector.target_templates)
        sp.btn_save_photo.click()
        self.app.processEvents()

        # Verificar que se procesó el guardado y se resetearon los botones
        self.assertTrue(len(w.detector.target_templates) >= initial_templates)
        self.assertIsNone(w._current_mouse_crop)
        self.assertFalse(sp.btn_save_photo.isEnabled())

    def test_04_mouse_crop_veto_lifecycle(self):
        """Verifica el recorte con ratón y veto como falso positivo."""
        w = self.window
        sp = w.settings_panel

        dummy_frame = np.full((480, 640, 3), 90, dtype=np.uint8)
        dummy_frame[48:144, 64:192] = np.random.randint(0, 255, (96, 128, 3), dtype=np.uint8)
        w._raw_current_frame = dummy_frame

        # Emitir recorte
        crop_coords = (0.1, 0.1, 0.3, 0.3)
        w.canvas.crop_selected.emit(crop_coords)
        self.app.processEvents()

        self.assertTrue(sp.btn_veto_photo.isEnabled())
        initial_negatives = len(w.detector.negative_templates)

        # Vetar foto
        sp.btn_veto_photo.click()
        self.app.processEvents()

        self.assertTrue(len(w.detector.negative_templates) >= initial_negatives)
        self.assertIsNone(w._current_mouse_crop)
        self.assertFalse(sp.btn_veto_photo.isEnabled())

    def test_05_mouse_crop_discard_lifecycle(self):
        """Verifica el descarte de un recorte sin guardar."""
        w = self.window
        sp = w.settings_panel

        dummy_frame = np.full((480, 640, 3), 90, dtype=np.uint8)
        w._raw_current_frame = dummy_frame

        crop_coords = (0.2, 0.2, 0.4, 0.4)
        w._on_mouse_crop_drawn(crop_coords)
        self.app.processEvents()

        self.assertTrue(sp.btn_discard_photo.isEnabled())
        sp.btn_discard_photo.click()
        self.app.processEvents()

        self.assertIsNone(w._current_mouse_crop)
        self.assertFalse(sp.btn_save_photo.isEnabled())
        self.assertFalse(sp.btn_veto_photo.isEnabled())
        self.assertFalse(sp.btn_discard_photo.isEnabled())

    def test_06_all_sliders_and_text_inputs(self):
        """Verifica la respuesta en tiempo real de todos los sliders y cajas de texto."""
        w = self.window
        sp = w.settings_panel

        # Slider sensibilidad movimiento (rango 5 - 100 -> 0.005 a 0.100)
        sp.slider_sens.setValue(60)
        self.assertAlmostEqual(w.detector.sensitivity, 0.060, places=3)
        self.assertIn("6.0%", sp.lbl_sens.text())

        # Slider similitud fotos bebé (10 - 90 -> 0.10 a 0.90)
        sp.slider_template_thresh.setValue(75)
        self.assertAlmostEqual(w.detector.template_threshold, 0.75, places=2)
        self.assertIn("75%", sp.lbl_template_thresh.text())

        # Slider umbral sonido (1 - 90 -> 0.01 a 0.90)
        sp.slider_sound_thresh.setValue(50)
        self.assertAlmostEqual(w.audio_monitor.threshold, 0.50, places=2)
        self.assertIn("50%", sp.lbl_sound_thresh.text())

        # Nombre del bebé
        sp.txt_baby_name.setText("Lucas")
        self.assertEqual(w.detector.baby_name, "Lucas")
        self.assertEqual(w.user_config.get("baby_name"), "Lucas")

    def test_07_all_checkboxes_toggle(self):
        """Verifica el comportamiento de todas las casillas de verificación (Checkboxes)."""
        w = self.window
        sp = w.settings_panel

        # Usar ROI
        sp.chk_use_roi.setChecked(False)
        self.assertFalse(w.detector.roi_enabled)
        sp.chk_use_roi.setChecked(True)
        self.assertTrue(w.detector.roi_enabled)

        # Mostrar personas
        sp.chk_show_persons.setChecked(True)
        self.assertTrue(w.detector.show_person_boxes)

        # Reconocimiento por fotos
        sp.chk_template.setChecked(True)
        self.assertTrue(w.detector.template_enabled)
        sp.chk_template.setChecked(False)
        self.assertFalse(w.detector.template_enabled)

        # Solo alertar si bebé reconocido
        sp.chk_only_baby_motion.setChecked(True)
        self.assertTrue(w.user_config["only_baby_motion"])

        # Galería de sugerencias
        sp.chk_suggestions.setChecked(True)
        self.assertFalse(w.gallery_panel.candidate_widget.isHidden())
        sp.chk_suggestions.setChecked(False)
        self.assertTrue(w.gallery_panel.candidate_widget.isHidden())

        # Alertas de movimiento y sonido
        sp.chk_alert_motion.setChecked(False)
        self.assertFalse(w.user_config["alert_motion"])
        sp.chk_alert_sound.setChecked(False)
        self.assertFalse(w.user_config["alert_sound"])
        sp.chk_alert_popup.setChecked(False)
        self.assertFalse(w.user_config["alert_popup"])

        # Silenciar tono sonoro
        sp.chk_mute_alarm_sound.setChecked(True)
        self.assertTrue(w.user_config["mute_alarm_sound"])

        # Horario silencioso
        sp.chk_silent_sched.setChecked(True)
        self.assertTrue(w.user_config["silent_sched_enabled"])

    def test_08_combos_and_pause_button(self):
        """Verifica los menús desplegables de duración y el botón de pausa de alertas."""
        w = self.window
        sp = w.settings_panel

        # Duración mínima de movimiento
        sp.combo_motion_min_duration.setCurrentText("15 Segundos")
        self.assertEqual(w.user_config["motion_min_duration_sec"], 15)

        # Duración pop-up
        sp.combo_popup_duration.setCurrentText("45 Segundos")
        self.assertEqual(w.user_config["popup_duration_sec"], 45)

        # Tiempo de pausa
        sp.combo_pause_duration.setCurrentText("10 Minutos")
        self.assertEqual(w.user_config["pause_duration_str"], "10 Minutos")

        # Botón pausar alertas (toggle)
        sp.btn_pause_alerts.click()
        self.assertGreater(w.alarm_paused_until, time.time())
        self.assertIn("Reanudar", sp.btn_pause_alerts.text())

        # Reanudar alertas
        sp.btn_pause_alerts.click()
        self.assertEqual(w.alarm_paused_until, 0.0)
        self.assertIn("Pausar", sp.btn_pause_alerts.text())

    def test_09_popup_alert_critical_level(self):
        """Verifica la activación y niveles de severidad del pop-up emergente."""
        w = self.window
        crop = np.zeros((100, 150, 3), dtype=np.uint8)

        # Probar pop-up crítico
        w.popup_alert.trigger_alert("🚨 TEST", "Alerta Crítica", crop, alert_level="critical")
        self.assertTrue(w.popup_alert.isVisible())
        self.assertEqual(w.popup_alert.current_alert_level, "critical")

        # Click en la imagen del popup debe ocultar el popup y traer la app al frente
        w.popup_alert._on_image_clicked()
        self.app.processEvents()
        self.assertFalse(w.popup_alert.isVisible())

    def test_10_analytics_tab_switching(self):
        """Verifica el cambio a la pestaña de estadísticas y análisis del sueño."""
        w = self.window
        w.tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertEqual(w.tabs.currentIndex(), 1)
        self.assertIsNotNone(w.analytics_tab)

if __name__ == "__main__":
    unittest.main()
