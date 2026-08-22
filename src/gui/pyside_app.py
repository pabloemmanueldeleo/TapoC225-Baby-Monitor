"""
Aplicación Principal PySide6 (Qt6 C++) para Tapo C225 - Monitor de Bebé de Alto Rendimiento.
Orquesta el lienzo interactivo, la barra lateral de controles, las galerías y el motor de IA.
"""
import sys
import os
import time
import logging
import cv2
import numpy as np
import threading
from typing import Optional, Tuple

from PySide6.QtCore import Qt, QTimer, QTime
from PySide6.QtGui import QImage, QPixmap, QColor, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFrame, QDialog, QMessageBox, QComboBox, QLineEdit, QScrollArea,
    QSystemTrayIcon, QMenu, QTabWidget
)

from src.services.video_stream import RTSPVideoStream
from src.services.audio_monitor import RTSPAudioMonitor
from src.services.analytics_service import BabyAnalyticsService
from src.services.sound_service import SoundService
from src.core.config_manager import ConfigManager
from src.core.detector import BabyDetector
from src.gui.analytics_tab import AnalyticsTabWidget
from src.gui.popup import CornerAlertWindow
from src.gui.canvas import VideoCanvas
from src.gui.gallery_panel import GalleryPanel
from src.gui.settings_panel import SettingsPanel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("PySide6App")

class PySideTapoApp(QMainWindow):
    """
    Ventana Principal y Controlador de la Aplicación Tapo C225 Baby Monitor.
    """
    def __init__(self, config_path: str = "config.json"):
        super().__init__()
        self.setWindowTitle("Tapo C225 - Monitor de Bebé (PySide6 C++ Engine)")
        self.resize(1180, 720)
        self.setStyleSheet("QMainWindow { background-color: #0F172A; } QLabel { color: #F8FAFC; }")

        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        icon_path = os.path.join(base_dir, "assets", "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 1. Configuración y Servicios
        self.config_manager = ConfigManager(config_path)
        self.user_config = self.config_manager.config
        self.sound_service = SoundService()

        # Cargar credenciales desde .env
        from dotenv import load_dotenv
        load_dotenv()
        tapo_ip = os.getenv("TAPO_IP", "").strip()
        stream_user = os.getenv("TAPO_STREAM_USER", "").strip()
        stream_pass = os.getenv("TAPO_STREAM_PASSWORD", "").strip()
        stream_quality = os.getenv("TAPO_STREAM_QUALITY", "stream1").strip()

        is_smoke = ("--smoke-test" in sys.argv or "--test-launch" in sys.argv or os.environ.get("SMOKE_TEST") == "1")
        if (not tapo_ip or not stream_user) and not is_smoke:
            tapo_ip, stream_user, stream_pass, stream_quality = self._prompt_camera_credentials_dialog(
                default_ip=tapo_ip, default_user=stream_user, default_pass=stream_pass
            )
        elif is_smoke and not tapo_ip:
            tapo_ip = "127.0.0.1"

        rtsp_url = f"rtsp://{stream_user}:{stream_pass}@{tapo_ip}:554/{stream_quality}"

        self.video_stream = RTSPVideoStream(rtsp_url)
        self.audio_monitor = RTSPAudioMonitor(rtsp_url)
        self.analytics_service = BabyAnalyticsService()

        # 2. Inicializar Detector
        self.detector = BabyDetector(
            sensitivity=self.user_config.get("sensitivity", 0.03),
            use_yolo=True
        )
        self.detector.template_enabled = self.user_config.get("template_enabled", True)
        self.detector.template_threshold = self.user_config.get("template_threshold", 0.60)
        saved_roi = self.user_config.get("roi")
        if saved_roi and len(saved_roi) == 4:
            self.detector.set_roi(*saved_roi)
        self.detector.baby_name = self.user_config.get("baby_name", "Bebé")
        self.detector.set_roi_enabled(self.user_config.get("use_roi", True))
        self.detector.show_person_boxes = self.user_config.get("show_persons", False)
        self.detector.suggestions_enabled = self.user_config.get("suggestions_enabled", False)
        self.audio_monitor.set_threshold(self.user_config.get("sound_threshold", 0.35))

        # 3. Pop-Up Emergente de Esquina
        self.popup_alert = CornerAlertWindow(self)
        self.popup_alert.pause_requested.connect(self._pause_alerts_1_min)
        self.popup_alert.image_clicked.connect(self._on_popup_image_clicked)

        # Estados de alarma
        self.alarm_paused_until = 0.0
        self._motion_active_start = None
        self._last_motion_active_time = 0.0
        self._last_popup_time = 0.0
        self._render_ticks = 0

        # 4. Construir Interfaz
        self._build_ui()
        self._init_tray_icon()

        # 5. Iniciar Streams y Detección
        self.video_stream.start()
        self.audio_monitor.running = True
        threading.Thread(target=self.audio_monitor._delayed_start, args=(4.0,), daemon=True).start()

        self._last_annotated: Optional[np.ndarray] = None
        self._last_crop: Optional[np.ndarray] = None
        self._last_motion: bool = False
        self._detect_lock = threading.Lock()
        self._detect_running = True
        threading.Thread(target=self._detect_loop, daemon=True).start()

        # Timer Qt para Render a 30 FPS
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._render_loop)
        self.timer.start(33)

        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    # --- Propiedades Proxy para compatibilidad total ---
    @property
    def slider_template_thresh(self):
        return self.settings_panel.slider_template_thresh

    @property
    def negatives_widget(self):
        return self.gallery_panel.negatives_widget

    @property
    def album_widget(self):
        return self.gallery_panel.album_widget

    def _init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        icon_path = os.path.join(base_dir, "assets", "app_icon.png")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            pix = QPixmap(32, 32)
            pix.fill(QColor("#0284C7"))
            self.tray_icon.setIcon(QIcon(pix))
        self.tray_icon.setToolTip("Tapo C225 - Monitor de Bebé")

        tray_menu = QMenu(self)
        action_show = tray_menu.addAction("🪟 Abrir / Mostrar Monitor")
        action_show.triggered.connect(self._show_and_activate)
        action_pause = tray_menu.addAction("⏸️ Pausar Alertas (1 Min)")
        action_pause.triggered.connect(self._pause_alerts_1_min)
        tray_menu.addSeparator()
        action_quit = tray_menu.addAction("❌ Cerrar Aplicación")
        action_quit.triggered.connect(self.close)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_and_activate()

    def _show_and_activate(self):
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _save_config(self):
        self.config_manager.save_config(self.user_config)

    def _build_ui(self):
        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #1E293B; background-color: #0F172A; }
            QTabBar::tab { background: #1E293B; color: #94A3B8; padding: 7px 18px; margin-right: 4px; border-top-left-radius: 6px; border-top-right-radius: 6px; font-weight: bold; font-size: 11px; }
            QTabBar::tab:selected { background: #0284C7; color: #FFFFFF; }
            QTabBar::tab:hover:!selected { background: #334155; color: #F8FAFC; }
        """)
        self.setCentralWidget(self.tabs)

        # PESTAÑA 1: MONITOREO EN VIVO
        tab_monitor = QWidget(self.tabs)
        main_layout = QHBoxLayout(tab_monitor)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # IZQUIERDA: TOOLBAR DE ACCESO RÁPIDO & CANVAS DE VIDEO
        left_box = QVBoxLayout()
        left_box.setSpacing(6)

        self.canvas = VideoCanvas(self)
        self.canvas.roi_changed.connect(self._on_roi_drawn)
        self.canvas.crop_selected.connect(self._on_mouse_crop_drawn)

        # BARRA DE ACCESO RÁPIDO SUPERIOR (Zero-scroll Quick Toolbar)
        self.toolbar = QFrame(self)
        self.toolbar.setStyleSheet("""
            QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; }
            QPushButton { background-color: #1E293B; color: #F8FAFC; border: 1px solid #334155; border-radius: 5px; padding: 5px 9px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background-color: #334155; }
            QPushButton:checked { background-color: #0284C7; color: white; border: 1px solid #38BDF8; }
        """)
        tb_layout = QHBoxLayout(self.toolbar)
        tb_layout.setContentsMargins(6, 4, 6, 4)
        tb_layout.setSpacing(6)

        self.tb_btn_roi = QPushButton("🎯 Zona Cuna", self.toolbar)
        self.tb_btn_roi.setCheckable(True)
        self.tb_btn_roi.clicked.connect(self._toggle_roi_mode_from_toolbar)
        tb_layout.addWidget(self.tb_btn_roi)

        self.tb_btn_crop = QPushButton("✂️ Recortar Bebé", self.toolbar)
        self.tb_btn_crop.setCheckable(True)
        self.tb_btn_crop.clicked.connect(self._toggle_crop_mode_from_toolbar)
        tb_layout.addWidget(self.tb_btn_crop)

        self.tb_btn_zoom = QPushButton("🔍 Zoom 1.0x", self.toolbar)
        self.tb_btn_zoom.clicked.connect(self.canvas.reset_zoom)
        tb_layout.addWidget(self.tb_btn_zoom)

        self.tb_btn_pause = QPushButton("⏸️ Pausar", self.toolbar)
        self.tb_btn_pause.setStyleSheet("background-color: #0369A1; color: white; font-weight: bold; font-size: 11px;")
        self.tb_btn_pause.clicked.connect(self._toggle_pause_alerts_button)
        tb_layout.addWidget(self.tb_btn_pause)

        self.tb_btn_snap = QPushButton("📸 Captura", self.toolbar)
        self.tb_btn_snap.setStyleSheet("background-color: #059669; color: white; font-weight: bold; font-size: 11px;")
        self.tb_btn_snap.clicked.connect(self._save_raw_clean_frame)
        tb_layout.addWidget(self.tb_btn_snap)

        self.tb_btn_test = QPushButton("🔔 Probar", self.toolbar)
        self.tb_btn_test.setStyleSheet("background-color: #D97706; color: white; font-weight: bold; font-size: 11px;")
        self.tb_btn_test.clicked.connect(self._test_popup)
        tb_layout.addWidget(self.tb_btn_test)

        self.tb_btn_config = QPushButton("⚙️ Conexión", self.toolbar)
        self.tb_btn_config.clicked.connect(self._reconfigure_camera_connection)
        tb_layout.addWidget(self.tb_btn_config)

        left_box.addWidget(self.toolbar)
        left_box.addWidget(self.canvas, stretch=1)

        self.lbl_status = QLabel("🟢 Estado: Monitoreando Cuna", self)
        self.lbl_status.setStyleSheet("font-weight: bold; font-size: 13px; color: #10B981; padding: 2px 4px;")
        left_box.addWidget(self.lbl_status)

        self.lbl_telemetry = QLabel("📊 Telemetría en Vivo: Conectando...", self)
        self.lbl_telemetry.setStyleSheet("font-size: 11px; color: #94A3B8; background-color: #0F172A; border-radius: 4px; padding: 4px 8px; border: 1px solid #1E293B;")
        left_box.addWidget(self.lbl_telemetry)
        main_layout.addLayout(left_box, stretch=3)

        # DERECHA: PANEL DE AJUSTES Y GALERÍAS ORGANIZADAS
        self.settings_panel = SettingsPanel(self.user_config, self.detector, self)
        self._connect_settings_panel()

        # Galerías integradas dentro de la pestaña Álbum & Vetos
        self.gallery_panel = GalleryPanel(
            self.detector, self.settings_panel.tab_album,
            on_status_msg=self._set_status_msg
        )
        self.settings_panel.tab_album_layout.addWidget(self.gallery_panel.candidate_widget)
        self.gallery_panel.candidate_widget.setVisible(self.user_config.get("suggestions_enabled", False))
        self.settings_panel.tab_album_layout.addWidget(self.gallery_panel.lbl_album_title)
        self.settings_panel.tab_album_layout.addWidget(self.gallery_panel.album_widget)
        self.settings_panel.tab_album_layout.addWidget(self.gallery_panel.lbl_negatives_title)
        self.settings_panel.tab_album_layout.addWidget(self.gallery_panel.negatives_widget)

        # Botones de Caché Binaria y Guía
        pkl_layout = QHBoxLayout()
        btn_rebuild_pkl = QPushButton("⚡ Optimizar Caché (.pkl)", self.settings_panel.tab_album)
        btn_rebuild_pkl.setStyleSheet("background-color: #0F766E; color: #CCFBF1; font-weight: bold; border-radius: 4px; padding: 5px; font-size: 10px;")
        btn_rebuild_pkl.clicked.connect(self._rebuild_pkl_cache)
        btn_help_guide = QPushButton("📖 Guía de Opciones", self.settings_panel.tab_album)
        btn_help_guide.setStyleSheet("background-color: #334155; color: #F8FAFC; font-weight: bold; border-radius: 4px; padding: 5px; font-size: 10px;")
        btn_help_guide.clicked.connect(self._show_help_guide_dialog)
        pkl_layout.addWidget(btn_rebuild_pkl)
        pkl_layout.addWidget(btn_help_guide)
        self.settings_panel.tab_album_layout.addLayout(pkl_layout)
        self.settings_panel.tab_album_layout.addStretch()

        self.gallery_panel.start_crop_requested.connect(self._trigger_start_first_crop)
        self.gallery_panel.update_album_ui()
        self.gallery_panel.update_negatives_ui()

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedWidth(380)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setWidget(self.settings_panel)
        main_layout.addWidget(scroll_area)

        self.tabs.addTab(tab_monitor, "📹 Monitoreo en Vivo")

        # PESTAÑA 2: ANALYTICS
        self.analytics_tab = AnalyticsTabWidget(self.analytics_service, self.user_config, self.tabs)
        self.tabs.addTab(self.analytics_tab, "📊 Salud y Análisis del Sueño")
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int):
        if hasattr(self, "analytics_tab"):
            self.analytics_tab.set_active_view(index == 1)

    def _connect_settings_panel(self):
        sp = self.settings_panel
        sp.roi_mode_toggled.connect(self._on_roi_mode_toggled)
        sp.crop_mode_toggled.connect(self._on_crop_mode_toggled)
        sp.reset_zoom_requested.connect(self.canvas.reset_zoom)
        sp.reconfigure_camera_requested.connect(self._reconfigure_camera_connection)
        sp.test_popup_requested.connect(self._test_popup)
        sp.save_raw_requested.connect(self._save_raw_clean_frame)
        sp.pause_alerts_requested.connect(self._toggle_pause_alerts_button)
        sp.close_app_requested.connect(self.close)

        sp.chk_use_roi.toggled.connect(self._toggle_roi)
        sp.chk_clean_osd.toggled.connect(self._toggle_clean_osd)
        self.canvas.set_clean_osd(self.user_config.get("clean_osd", True))

        sp.slider_sens.valueChanged.connect(self._on_sens_changed)
        sp.txt_baby_name.textChanged.connect(self._on_baby_name_changed)
        sp.chk_show_persons.toggled.connect(self._toggle_show_persons)
        sp.chk_template.toggled.connect(self._toggle_template)
        sp.chk_only_baby_motion.toggled.connect(self._toggle_only_baby_motion)
        sp.slider_template_thresh.valueChanged.connect(self._on_template_thresh_changed)
        sp.chk_suggestions.toggled.connect(self._toggle_suggestions)
        sp.slider_sound_thresh.valueChanged.connect(self._on_sound_thresh_changed)
        sp.chk_alert_motion.toggled.connect(self._toggle_motion_alert)
        sp.combo_motion_min_duration.currentTextChanged.connect(self._on_motion_min_duration_changed)
        sp.chk_alert_sound.toggled.connect(self._toggle_sound_alert)
        sp.chk_alert_popup.toggled.connect(self._toggle_popup_alert)
        sp.combo_popup_duration.currentTextChanged.connect(self._on_popup_duration_changed)
        sp.chk_mute_alarm_sound.toggled.connect(self._toggle_mute_alarm_sound)
        sp.chk_live_audio.toggled.connect(self._toggle_live_audio)
        sp.chk_silent_sched.toggled.connect(self._toggle_silent_sched)
        sp.time_start.timeChanged.connect(self._on_silent_time_changed)
        sp.time_end.timeChanged.connect(self._on_silent_time_changed)
        sp.combo_pause_duration.currentTextChanged.connect(self._on_pause_duration_changed)

        sp.btn_save_photo.clicked.connect(self._save_baby_crop)
        sp.btn_veto_photo.clicked.connect(self._veto_baby_crop)
        sp.btn_discard_photo.clicked.connect(self._discard_baby_crop)

    def _set_status_msg(self, msg: str, color: str = "#10B981"):
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {color}; padding: 4px;")

    def _on_tab_changed(self, index: int):
        if index == 1 and hasattr(self, "analytics_tab"):
            self.analytics_tab.refresh_charts()

    # --- Herramientas de Ratón, Toolbar & ROI ---
    def _toggle_roi_mode_from_toolbar(self):
        checked = self.tb_btn_roi.isChecked()
        self.settings_panel.btn_mode_roi.setChecked(checked)
        self._on_roi_mode_toggled(checked)

    def _toggle_crop_mode_from_toolbar(self):
        checked = self.tb_btn_crop.isChecked()
        self.settings_panel.btn_mode_crop.setChecked(checked)
        self._on_crop_mode_toggled(checked)

    def _on_roi_mode_toggled(self, checked: bool):
        if hasattr(self, "tb_btn_roi") and self.tb_btn_roi.isChecked() != checked:
            self.tb_btn_roi.setChecked(checked)
        if hasattr(self, "settings_panel") and self.settings_panel.btn_mode_roi.isChecked() != checked:
            self.settings_panel.btn_mode_roi.setChecked(checked)
        if checked:
            if hasattr(self, "tb_btn_crop"):
                self.tb_btn_crop.setChecked(False)
            self.settings_panel.btn_mode_crop.setChecked(False)
            self.canvas.set_mouse_mode("🎯 Ajustar Zona Cuna")
            self._set_status_msg("🎯 Arrastra con el Clic Izquierdo para recuadrar la cuna", "#38BDF8")
        else:
            self.canvas.set_mouse_mode("NONE")
            self._set_status_msg("🟢 Estado: Monitoreando Cuna")

    def _on_crop_mode_toggled(self, checked: bool):
        if hasattr(self, "tb_btn_crop") and self.tb_btn_crop.isChecked() != checked:
            self.tb_btn_crop.setChecked(checked)
        if hasattr(self, "settings_panel") and self.settings_panel.btn_mode_crop.isChecked() != checked:
            self.settings_panel.btn_mode_crop.setChecked(checked)
        if checked:
            if hasattr(self, "tb_btn_roi"):
                self.tb_btn_roi.setChecked(False)
            self.settings_panel.btn_mode_roi.setChecked(False)
            # Cambiar a pestaña Detección para ver el cuadro de vista previa de recorte
            if hasattr(self.settings_panel, "sub_tabs"):
                self.settings_panel.sub_tabs.setCurrentIndex(0)
            self.canvas.set_mouse_mode("🖐️ Recortar Parte Bebé")
            self._set_status_msg("🖐️ Arrastra con el Clic Izquierdo para recortar foto/ángulo del bebé", "#F59E0B")
        else:
            self.canvas.set_mouse_mode("NONE")
            self._set_status_msg("🟢 Estado: Monitoreando Cuna")

    def _trigger_start_first_crop(self):
        self.settings_panel.btn_mode_crop.setChecked(True)
        self._on_crop_mode_toggled(True)

    def _on_roi_drawn(self, roi_tuple: tuple):
        self.detector.set_roi(*roi_tuple)
        self.detector.set_roi_enabled(True)
        self.settings_panel.chk_use_roi.setChecked(True)
        self.settings_panel.btn_mode_roi.setChecked(False)
        if hasattr(self, "tb_btn_roi"):
            self.tb_btn_roi.setChecked(False)
        self.canvas.set_mouse_mode("NONE")
        self.user_config["roi"] = list(roi_tuple)
        self.user_config["use_roi"] = True
        self._save_config()
        self._set_status_msg("🎯 Zona Cuna definida y activada correctamente", "#10B981")

    def _toggle_roi(self, checked: bool):
        self.detector.set_roi_enabled(checked)
        self.user_config["use_roi"] = checked
        self._save_config()
        if checked:
            self._set_status_msg("🎯 Límite por Región Cuna Activado", "#38BDF8")
        else:
            self._set_status_msg("🌐 Monitoreo en Pantalla Completa Activado", "#10B981")

    def _toggle_clean_osd(self, checked: bool):
        self.user_config["clean_osd"] = checked
        self._save_config()
        self.canvas.set_clean_osd(checked)
        if checked:
            self._set_status_msg("🧹 Modo Visión Limpia Activado (Textos fuera del video)", "#38BDF8")
        else:
            self._set_status_msg("🏷️ Modo Etiquetas en Video Activado", "#10B981")

    def _on_sens_changed(self, val: int):
        sens = val / 1000.0
        self.detector.sensitivity = sens
        self.settings_panel.lbl_sens.setText(f"Sensibilidad Movimiento: {sens*100:.1f}%")
        self.user_config["sensitivity"] = sens
        self._save_config()

    def _on_baby_name_changed(self, text: str):
        name = text.strip() or "Bebé"
        self.detector.baby_name = name
        self.user_config["baby_name"] = name
        self._save_config()

    def _toggle_show_persons(self, checked: bool):
        self.detector.show_person_boxes = checked
        self.user_config["show_persons"] = checked
        self._save_config()

    def _toggle_template(self, checked: bool):
        self.detector.template_enabled = checked
        self.user_config["template_enabled"] = checked
        self._save_config()

    def _toggle_only_baby_motion(self, checked: bool):
        self.user_config["only_baby_motion"] = checked
        self._save_config()

    def _on_template_thresh_changed(self, val: int):
        th = val / 100.0
        self.detector.template_threshold = th
        self.settings_panel.lbl_template_thresh.setText(f"Similitud Fotos Bebé: {val}%")
        self.user_config["template_threshold"] = th
        self._save_config()

    def _toggle_suggestions(self, checked: bool):
        self.user_config["suggestions_enabled"] = checked
        self.detector.suggestions_enabled = checked
        self.gallery_panel.candidate_widget.setVisible(checked)
        if checked:
            self.gallery_panel.update_candidates_ui()
            if hasattr(self.settings_panel, "sub_tabs"):
                self.settings_panel.sub_tabs.setCurrentIndex(2)
        self._save_config()

    def _on_sound_thresh_changed(self, val: int):
        th = val / 100.0
        self.audio_monitor.set_threshold(th)
        self.settings_panel.lbl_sound_thresh.setText(f"Tolerancia Umbral Sonido: {val}%")
        self.settings_panel.progress_audio.set_threshold(th)
        self.user_config["sound_threshold"] = th
        self._save_config()

    def _toggle_motion_alert(self, checked: bool):
        self.user_config["alert_motion"] = checked
        self._save_config()

    def _on_motion_min_duration_changed(self, text: str):
        dur_map = {
            "Inmediato (0 seg)": 0, "1 Segundo": 1, "2 Segundos": 2, "3 Segundos": 3,
            "4 Segundos": 4, "5 Segundos": 5, "8 Segundos (Por defecto)": 8,
            "10 Segundos": 10, "15 Segundos": 15, "20 Segundos": 20,
            "25 Segundos": 25, "30 Segundos": 30
        }
        sec = dur_map.get(text, 8)
        self.user_config["motion_min_duration_sec"] = sec
        self._save_config()

    def _toggle_sound_alert(self, checked: bool):
        self.user_config["alert_sound"] = checked
        self._save_config()

    def _toggle_popup_alert(self, checked: bool):
        self.user_config["alert_popup"] = checked
        self._save_config()

    def _on_popup_duration_changed(self, text: str):
        cleaned = text.replace("s", "").replace("Segundos", "").strip()
        dur = int(cleaned.split()[0])
        self.user_config["popup_duration_sec"] = dur
        self._save_config()

    def _toggle_mute_alarm_sound(self, checked: bool):
        self.user_config["mute_alarm_sound"] = checked
        self._save_config()

    def _toggle_live_audio(self, checked: bool):
        self.user_config["live_audio"] = checked
        self._save_config()

    def _toggle_silent_sched(self, checked: bool):
        self.user_config["silent_sched_enabled"] = checked
        self.config_manager.set("silent_schedule_enabled", checked)
        self._save_config()

    def _on_silent_time_changed(self):
        s_time = self.settings_panel.time_start.time().toString("HH:mm")
        e_time = self.settings_panel.time_end.time().toString("HH:mm")
        self.user_config["silent_sched_start"] = s_time
        self.user_config["silent_sched_end"] = e_time
        self.config_manager.set("silent_start_hour", s_time)
        self.config_manager.set("silent_end_hour", e_time)
        self._save_config()

    def _on_pause_duration_changed(self, text: str):
        self.user_config["pause_duration_str"] = text
        self._save_config()

    def _is_in_silent_schedule(self) -> bool:
        return self.config_manager.is_in_silent_schedule()

    # --- Recortes con Ratón ---
    def _on_mouse_crop_drawn(self, crop_data):
        sp = self.settings_panel
        crop = None
        coords = None

        if isinstance(crop_data, (tuple, list)):
            coords = tuple(crop_data)
            frame = getattr(self, "_raw_current_frame", None)
            if frame is None and hasattr(self, "video_stream"):
                frame = self.video_stream.read()
            if frame is not None:
                fh, fw = frame.shape[:2]
                px1 = int(coords[0] * fw)
                py1 = int(coords[1] * fh)
                px2 = int(coords[2] * fw)
                py2 = int(coords[3] * fh)
                x1, x2 = max(0, min(px1, px2)), min(fw, max(px1, px2))
                y1, y2 = max(0, min(py1, py2)), min(fh, max(py1, py2))
                if (x2 - x1) > 5 and (y2 - y1) > 5:
                    crop = frame[y1:y2, x1:x2].copy()
        elif isinstance(crop_data, np.ndarray):
            crop = crop_data.copy()

        if crop is not None and crop.size > 0:
            self._current_mouse_crop = crop
            self._current_mouse_crop_coords = coords
            try:
                rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                ch, cw, _ = rgb.shape
                qimg = QImage(rgb.data, cw, ch, 3 * cw, QImage.Format_RGB888)
                sp.lbl_crop_img.setPixmap(QPixmap.fromImage(qimg).scaled(180, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                sp.lbl_crop_preview_title.setText(f"✂️ Recorte listo ({cw}x{ch} px): Elige 'Guardar Bebé' o 'Vetar'")
                sp.lbl_crop_preview_title.setStyleSheet("font-size: 10px; color: #10B981; font-weight: bold;")
                sp.btn_save_photo.setEnabled(True)
                sp.btn_veto_photo.setEnabled(True)
                sp.btn_discard_photo.setEnabled(True)
                self._set_status_msg("✂️ Recorte listo. Haz clic en 'Guardar Bebé', 'Vetar Falso Positivo' o 'Descartar'", "#10B981")
            except Exception as e:
                logger.error(f"Error procesando miniatura de recorte: {e}")

        sp.btn_mode_crop.setChecked(False)
        if hasattr(self, "tb_btn_crop"):
            self.tb_btn_crop.setChecked(False)
        if hasattr(self.settings_panel, "sub_tabs"):
            self.settings_panel.sub_tabs.setCurrentIndex(0)
        self.canvas.set_mouse_mode("NONE")

    def _save_baby_crop(self):
        sp = self.settings_panel
        if hasattr(self, "_current_mouse_crop") and self._current_mouse_crop is not None:
            coords = getattr(self, "_current_mouse_crop_coords", None)
            if self.detector.save_target_template_from_crop(self._current_mouse_crop, coords):
                self.gallery_panel.update_album_ui()
                self.gallery_panel.update_candidates_ui()
                self._set_status_msg("✨ ¡Nueva foto guardada exitosamente en el álbum del bebé!", "#38BDF8")
            self._discard_baby_crop()

    def _veto_baby_crop(self):
        sp = self.settings_panel
        if hasattr(self, "_current_mouse_crop") and self._current_mouse_crop is not None:
            coords = getattr(self, "_current_mouse_crop_coords", None)
            if self.detector.save_negative_template_from_crop(self._current_mouse_crop, coords):
                self.gallery_panel.update_negatives_ui()
                self.gallery_panel.update_candidates_ui()
                self._set_status_msg("🚫 ¡Falso positivo vetado añadido a la lista negra!", "#F87171")
            self._discard_baby_crop()

    def _discard_baby_crop(self):
        sp = self.settings_panel
        self._current_mouse_crop = None
        self._current_mouse_crop_coords = None
        self.canvas.clear_selected_crop()
        sp.lbl_crop_img.clear()
        sp.lbl_crop_preview_title.setText("✂️ Ningún recorte seleccionado")
        sp.lbl_crop_preview_title.setStyleSheet("font-size: 10px; color: #94A3B8; font-style: italic;")
        sp.btn_save_photo.setEnabled(False)
        sp.btn_veto_photo.setEnabled(False)
        sp.btn_discard_photo.setEnabled(False)
        self._set_status_msg("🟢 Estado: Monitoreando Cuna")

    def _rebuild_pkl_cache(self):
        t_pos, opt_pos, t_neg, opt_neg = self.detector.rebuild_all_caches()
        self.gallery_panel.update_album_ui()
        self.gallery_panel.update_negatives_ui()
        QMessageBox.information(
            self, "⚡ Caché Binaria Optimizada",
            f"✅ Se optimizaron las fotos:\n\n"
            f"• Fotos del Bebé: {opt_pos} maestras seleccionadas de {t_pos} analizadas.\n"
            f"• Falsos Positivos Vetados: {opt_neg} ejemplos guardados.\n\n"
            "El sistema ahora arranca instantáneamente a 30 FPS."
        )

    def _pause_alerts_1_min(self):
        self.alarm_paused_until = time.time() + 60.0
        if hasattr(self, "tb_btn_pause"):
            self.tb_btn_pause.setText("▶️ Reanudar (1m)")
            self.tb_btn_pause.setStyleSheet("background-color: #F59E0B; color: black; font-weight: bold; font-size: 11px;")
        self._set_status_msg("⏸️ Alertas silenciadas durante 1 minuto", "#38BDF8")

    def _toggle_pause_alerts_button(self):
        now = time.time()
        dur_map = {"1 Minuto": 60, "5 Minutos": 300, "10 Minutos": 600, "15 Minutos": 900, "30 Minutos": 1800}
        sel_text = self.settings_panel.combo_pause_duration.currentText()
        sec = dur_map.get(sel_text, 1800)

        if self.alarm_paused_until > now:
            self.alarm_paused_until = 0.0
            self.settings_panel.btn_pause_alerts.setText("⏸️ Pausar Alertas")
            self.settings_panel.btn_pause_alerts.setStyleSheet("background-color: #0284C7; color: white; font-weight: bold; border-radius: 5px; padding: 4px 8px;")
            if hasattr(self, "tb_btn_pause"):
                self.tb_btn_pause.setText("⏸️ Pausar")
                self.tb_btn_pause.setStyleSheet("background-color: #0369A1; color: white; font-weight: bold; font-size: 11px;")
            self._set_status_msg("▶️ Alertas reanudadas", "#10B981")
        else:
            self.alarm_paused_until = now + sec
            self.settings_panel.btn_pause_alerts.setText("▶️ Reanudar Alertas")
            self.settings_panel.btn_pause_alerts.setStyleSheet("background-color: #F59E0B; color: black; font-weight: bold; border-radius: 5px; padding: 4px 8px;")
            if hasattr(self, "tb_btn_pause"):
                self.tb_btn_pause.setText("▶️ Reanudar")
                self.tb_btn_pause.setStyleSheet("background-color: #F59E0B; color: black; font-weight: bold; font-size: 11px;")
            self._set_status_msg(f"⏸️ Alertas pausadas por {sel_text}", "#38BDF8")

    def _test_popup(self):
        crop = np.zeros((140, 240, 3), dtype=np.uint8)
        crop[:] = (35, 20, 50)
        cv2.putText(crop, "PRUEBA POP-UP", (30, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
        self.popup_alert.reset_manual_close()
        self.popup_alert.trigger_alert("PRUEBA DE ALERTA", "Demostración de ventana emergente", crop, alert_level="critical")

    def _on_popup_image_clicked(self):
        if hasattr(self, "popup_alert") and self.popup_alert is not None:
            self.popup_alert.hide()
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _save_raw_clean_frame(self):
        frame = self.video_stream.read()
        if frame is not None:
            os.makedirs("captures", exist_ok=True)
            fname = f"captures/raw_capture_{int(time.time())}.jpg"
            cv2.imwrite(fname, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            self._set_status_msg(f"📸 Captura limpia guardada en {fname}", "#10B981")

    # --- Hilo de Detección de Fondo ---
    def _detect_loop(self):
        while getattr(self, "_detect_running", True):
            t_start = time.time()
            frame = self.video_stream.read()
            if frame is None:
                time.sleep(0.05)
                continue

            motion_det, baby_det, annotated, info = self.detector.process_frame(frame)
            crop = None
            if self.detector.roi_enabled and self.detector.roi is not None:
                h, w = frame.shape[:2]
                rx1, ry1 = int(self.detector.roi[0] * w), int(self.detector.roi[1] * h)
                rx2, ry2 = int(self.detector.roi[2] * w), int(self.detector.roi[3] * h)
                if rx2 > rx1 and ry2 > ry1:
                    crop = frame[ry1:ry2, rx1:rx2]
            else:
                crop = frame

            with self._detect_lock:
                self._last_annotated = annotated
                self._last_crop = crop
                self._last_motion = motion_det
                self._last_baby = baby_det
                self._last_info = info

            # Registrar telemetría de sueño
            if getattr(self, "analytics_service", None):
                vol = self.audio_monitor.get_volume() if hasattr(self, "audio_monitor") else 0.0
                crying = self.audio_monitor.is_sound_alert() if hasattr(self, "audio_monitor") else False
                self.analytics_service.log_sample(
                    baby_present=baby_det,
                    motion_ratio=info.get("motion_ratio", 0.0),
                    audio_volume=vol,
                    is_crying=crying
                )

            # Control adaptativo de tasa de inferencia (5 FPS = 200 ms) para liberar GIL y CPU a la interfaz
            compute_elapsed = time.time() - t_start
            sleep_time = max(0.04, 0.20 - compute_elapsed)
            time.sleep(sleep_time)

    # --- Render Loop a 30 FPS ---
    def _render_loop(self):
        live_frame = self.video_stream.read()
        if live_frame is not None:
            self._raw_current_frame = live_frame
            overlay_info = self.detector.get_vector_overlay_info(live_frame.shape)
            self.canvas.update_frame(live_frame, overlay_info)

        # Actualizar medidor de audio
        current_vol = self.audio_monitor.get_volume()
        sound_thresh = self.audio_monitor.threshold
        self.settings_panel.progress_audio.set_value_and_threshold(current_vol, sound_thresh)
        self.settings_panel.lbl_audio_vol.setText(
            f"Nivel Audio: {int(current_vol*100)}%  (Umbral Disparo: {int(sound_thresh*100)}%)"
        )

        with self._detect_lock:
            crop = self._last_crop
            baby_det = getattr(self, "_last_baby", False)
            info = getattr(self, "_last_info", {})

        now = time.time()
        effective_motion = float(self.detector.last_motion_ratio)
        sensitivity = float(self.detector.sensitivity)
        is_motion_active = (effective_motion >= sensitivity)

        # Actualizar telemetría fuera del frame de video
        b_name = self.detector.baby_name
        b_score = info.get("score", 0.0) if isinstance(info, dict) else 0.0
        c_status = "🎯 Cuna: Activa" if (self.detector.roi_enabled and self.detector.roi is not None) else "🌐 Pantalla Completa"
        b_txt = f"👶 {b_name} ({b_score*100:.0f}% Similitud)" if baby_det else "👶 Bebé: No Visualizado"
        m_icon = "🏃" if is_motion_active else "💤"
        if hasattr(self, "lbl_telemetry"):
            self.lbl_telemetry.setText(
                f"📊 {b_txt}   |   {m_icon} Movimiento: {effective_motion*100:.1f}% (Umbral: {sensitivity*100:.1f}%)   |   {c_status}"
            )

        min_motion_duration = float(self.user_config.get("motion_min_duration_sec", 8.0))
        if is_motion_active:
            if self._motion_active_start is None or (now - self._last_motion_active_time > 1.2):
                self._motion_active_start = now
            self._last_motion_active_time = now
            motion_elapsed = now - self._motion_active_start
        else:
            if now - self._last_motion_active_time > 1.2:
                self._motion_active_start = None
                motion_elapsed = 0.0
            else:
                motion_elapsed = (self._last_motion_active_time - self._motion_active_start) if self._motion_active_start else 0.0

        is_motion_sustained = (motion_elapsed >= min_motion_duration and is_motion_active) if min_motion_duration > 0 else is_motion_active
        motion_alert = is_motion_sustained and self.user_config.get("alert_motion", True)
        if self.user_config.get("only_baby_motion", False) and not baby_det:
            motion_alert = False

        sound_alert = self.audio_monitor.is_sound_alert() and self.user_config.get("alert_sound", True)
        is_paused = self.alarm_paused_until > now

        # Actualizar galería de sugerencias periódicamente
        self._render_ticks += 1
        if self._render_ticks % 30 == 0 and self.user_config.get("suggestions_enabled", False):
            self.gallery_panel.update_candidates_ui()

        if is_paused:
            remaining = int(self.alarm_paused_until - now)
            self._set_status_msg(f"⏸️ Alertas silenciadas temporalmente ({remaining}s restantes)", "#38BDF8")
        else:
            if motion_alert or sound_alert:
                if motion_alert and sound_alert:
                    alert_title = "🚨 ¡ALERTA COMBINADA MÁXIMA!"
                    msg = "🏃 Movimiento detectado + 🔊 Llanto/Audio elevado simultáneo"
                    alert_level = "critical"
                elif sound_alert:
                    alert_title = "🔊 ALERTA AUDITIVA"
                    msg = "🔊 Llanto o Ruido Fuerte detectado en la habitación"
                    alert_level = "sound"
                else:
                    alert_title = "🏃 ALERTA DE MOVIMIENTO"
                    msg = f"⚠️ Movimiento continuo del bebé detectado ({motion_elapsed:.1f}s)"
                    alert_level = "motion"

                silent_tag = " 🔇[Horario Trabajo Silencioso]" if self._is_in_silent_schedule() else ""
                self._set_status_msg(f"{alert_title}: {msg}{silent_tag}", "#EF4444")

                if not self.user_config.get("mute_alarm_sound", False) and not self._is_in_silent_schedule():
                    if now - getattr(self, "_last_sound_time", 0.0) > 6.0:
                        self._last_sound_time = now
                        self.sound_service.play_beep()

                if self.user_config.get("alert_popup", True) and crop is not None and not getattr(self.canvas, "is_drawing", False):
                    self.popup_alert.trigger_alert(alert_title, msg, crop, alert_level=alert_level)
                    self._last_popup_time = now
            else:
                silent_tag = " 🔇[Horario Trabajo]" if self._is_in_silent_schedule() else ""
                if is_motion_active and min_motion_duration > 0 and motion_elapsed < min_motion_duration:
                    self._set_status_msg(f"⏳ Evaluando micro-movimiento ({motion_elapsed:.1f}s / {min_motion_duration:.0f}s)...{silent_tag}", "#F59E0B")
                elif baby_det:
                    self._set_status_msg(f"👶 Bebé Visualizado ({self.detector.baby_name}) — Cuna Segura{silent_tag}", "#10B981")
                else:
                    self._set_status_msg(f"👁️ Bebé No Visualizado en Cámara — Atento a Alertas{silent_tag}", "#F59E0B")

                popup_dur_sec = float(self.user_config.get("popup_duration_sec", 30))
                if hasattr(self, "popup_alert") and self.popup_alert.isVisible():
                    if now - getattr(self, "_last_popup_time", 0.0) >= popup_dur_sec:
                        self.popup_alert.reset_manual_close()
                        self.popup_alert.hide()

    def _show_help_guide_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("📖 Guía de Opciones y Buenas Prácticas")
        dlg.resize(600, 500)
        dlg.setStyleSheet("background-color: #0F172A; color: #F8FAFC;")
        d_layout = QVBoxLayout(dlg)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        content = QWidget()
        c_layout = QVBoxLayout(content)

        guides = [
            ("🎯 Zona Cuna con Ratón", "Permite dibujar un rectángulo directamente sobre la cuna. La IA ignorará movimientos fuera de este límite."),
            ("✂️ Recorte del Bebé con Ratón", "Permite capturar un recorte del bebé para que la IA aprenda su silueta única."),
            ("🚫 Vetar Falso Positivo", "Añade un recorte a la lista negra de falsos positivos para que la IA nunca lo confunda con el bebé."),
            ("⏱️ Movimiento Continuo", "Filtra micro-movimientos involuntarios mientras el bebé duerme antes de disparar alarmas."),
            ("🔇 Horario Silencioso", "Silencia alertas sonoras durante horarios de trabajo o reuniones.")
        ]

        for title, desc in guides:
            box = QFrame(content)
            box.setStyleSheet("background-color: #1E293B; border-radius: 6px; padding: 6px; margin-bottom: 4px;")
            b_layout = QVBoxLayout(box)
            lbl_t = QLabel(title, box)
            lbl_t.setStyleSheet("font-weight: bold; color: #38BDF8; font-size: 11px;")
            lbl_d = QLabel(desc, box)
            lbl_d.setWordWrap(True)
            lbl_d.setStyleSheet("color: #CBD5E1; font-size: 10px;")
            b_layout.addWidget(lbl_t)
            b_layout.addWidget(lbl_d)
            c_layout.addWidget(box)

        scroll.setWidget(content)
        d_layout.addWidget(scroll)

        btn_ok = QPushButton("Entendido", dlg)
        btn_ok.setStyleSheet("background-color: #0284C7; color: white; font-weight: bold; border-radius: 4px; padding: 6px;")
        btn_ok.clicked.connect(dlg.accept)
        d_layout.addWidget(btn_ok)
        dlg.exec()

    def _prompt_camera_credentials_dialog(self, default_ip="", default_user="", default_pass=""):
        dlg = QDialog(self)
        dlg.setWindowTitle("Configuración de Cámara Tapo C225")
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        dlg.setModal(True)
        dlg.setStyleSheet("background-color: #0F172A; color: #F8FAFC;")
        d_layout = QVBoxLayout(dlg)

        lbl_ip = QLabel("IP de la Cámara:", dlg)
        txt_ip = QLineEdit(default_ip or "192.168.1.100", dlg)
        txt_ip.setStyleSheet("background-color: #1E293B; color: white; padding: 4px;")

        lbl_user = QLabel("Usuario de Cuenta de Cámara:", dlg)
        txt_user = QLineEdit(default_user, dlg)
        txt_user.setStyleSheet("background-color: #1E293B; color: white; padding: 4px;")

        lbl_pass = QLabel("Contraseña:", dlg)
        txt_pass = QLineEdit(default_pass, dlg)
        txt_pass.setEchoMode(QLineEdit.Password)
        txt_pass.setStyleSheet("background-color: #1E293B; color: white; padding: 4px;")

        lbl_quality = QLabel("Calidad de Stream:", dlg)
        combo_quality = QComboBox(dlg)
        combo_quality.addItems(["stream1 (2K / Alta Definición)", "stream2 (720p / Fluido)"])
        combo_quality.setStyleSheet("background-color: #1E293B; color: white; padding: 4px;")

        d_layout.addWidget(lbl_ip)
        d_layout.addWidget(txt_ip)
        d_layout.addWidget(lbl_user)
        d_layout.addWidget(txt_user)
        d_layout.addWidget(lbl_pass)
        d_layout.addWidget(txt_pass)
        d_layout.addWidget(lbl_quality)
        d_layout.addWidget(combo_quality)

        btn_box = QHBoxLayout()
        btn_save = QPushButton("Guardar y Conectar", dlg)
        btn_save.setStyleSheet("background-color: #0284C7; color: white; font-weight: bold; padding: 6px;")
        btn_save.clicked.connect(dlg.accept)
        btn_box.addWidget(btn_save)
        d_layout.addLayout(btn_box)

        if dlg.exec() == QDialog.Accepted:
            qual = "stream1" if "stream1" in combo_quality.currentText() else "stream2"
            return txt_ip.text().strip(), txt_user.text().strip(), txt_pass.text().strip(), qual
        return default_ip, default_user, default_pass, "stream1"

    def _reconfigure_camera_connection(self):
        from dotenv import load_dotenv
        load_dotenv()
        ip = os.getenv("TAPO_IP", "")
        user = os.getenv("TAPO_STREAM_USER", "")
        pwd = os.getenv("TAPO_STREAM_PASSWORD", "")
        nip, nuser, npwd, nqual = self._prompt_camera_credentials_dialog(ip, user, pwd)

        with open(".env", "w", encoding="utf-8") as f:
            f.write(f"TAPO_IP={nip}\nTAPO_STREAM_USER={nuser}\nTAPO_STREAM_PASSWORD={npwd}\nTAPO_STREAM_QUALITY={nqual}\n")

        QMessageBox.information(self, "Configuración Guardada", "Credenciales actualizadas en .env. Reinicia la aplicación para aplicar los cambios.")

    def closeEvent(self, event):
        self._detect_running = False
        if hasattr(self, "timer") and self.timer.isActive():
            self.timer.stop()
        if hasattr(self, "tray_icon") and self.tray_icon is not None:
            try:
                self.tray_icon.hide()
            except Exception:
                pass
        if hasattr(self, "popup_alert") and self.popup_alert is not None:
            self.popup_alert.close()
        if hasattr(self, "video_stream"):
            self.video_stream.stop()
        if hasattr(self, "audio_monitor"):
            self.audio_monitor.stop()
        if hasattr(self, "sound_service") and getattr(self.sound_service, "initialized", False):
            try:
                import pygame
                pygame.mixer.stop()
            except Exception:
                pass
        event.accept()
